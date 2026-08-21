import discord
from discord import app_commands
from discord.ext import commands
from cogs.settings_helper import settings

# --- UI MODALS (POPUPS) ---

class PowerModal(discord.ui.Modal):
    power_input = discord.ui.TextInput(
        label='Enter Voting Power (Numbers Only)',
        placeholder='e.g., 5',
        required=True,
        max_length=4,
        style=discord.TextStyle.short
    )

    def __init__(self, role: discord.Role, cog):
        super().__init__(title=f"Boost Power: {role.name}"[:45])
        self.role = role
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            power_val = int(self.power_input.value)
            await self.cog.set_active_role(interaction.guild.id, self.role.id, power_val)

            embed = await self.cog.get_dashboard_embed(interaction.guild.id)
            await interaction.response.edit_message(
                content=f"✅ **{self.role.name}** set to **{power_val}** power!",
                embed=embed,
                view=VotingDashboard(self.cog)
            )
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)


class SaveLoadoutModal(discord.ui.Modal, title='Save Current Setup'):
    name_input = discord.ui.TextInput(
        label='Loadout Name',
        placeholder='e.g., High Stakes, Staff Only...',
        required=True,
        max_length=30,
        style=discord.TextStyle.short
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value
        current_roles = await self.cog.get_active_roles_dict(interaction.guild.id)

        if not current_roles:
            await interaction.response.send_message("⚠️ No active roles to save!", ephemeral=True)
            return

        await self.cog.save_loadout(interaction.guild.id, name, current_roles)

        embed = await self.cog.get_dashboard_embed(interaction.guild.id)
        await interaction.response.edit_message(
            content=f"💾 **Loadout '{name}' saved!**",
            embed=embed,
            view=VotingDashboard(self.cog)
        )


# --- UI SELECT MENUS (DROPDOWNS) ---

class RoleSelectMenu(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to configure...", min_values=1, max_values=1)
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0]
        await interaction.response.send_modal(PowerModal(role, self.cog))

    @discord.ui.button(label="🔙 Back to Dashboard", style=discord.ButtonStyle.grey, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.get_dashboard_embed(interaction.guild.id)
        await interaction.response.edit_message(content="🛠️ **Voting Dashboard**", embed=embed, view=VotingDashboard(self.cog))


class ActionSelect(discord.ui.Select):
    def __init__(self, action_type, loadouts_dict, guild, cog):
        self.action_type = action_type
        self.cog = cog
        options = []

        for name, roles in list(loadouts_dict.items())[:25]:
            preview = " | ".join([
                f"{guild.get_role(r_id).name if guild.get_role(r_id) else 'Deleted'}: {pwr}"
                for r_id, pwr in roles
            ])
            desc = preview[:97] + "..." if len(preview) > 100 else preview
            emoji = "📦" if action_type == 'load' else "🗑️"
            options.append(discord.SelectOption(label=name, description=desc, value=name, emoji=emoji))

        placeholder = "Choose a setup to load..." if action_type == 'load' else "Choose a setup to DELETE..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]

        if self.action_type == 'load':
            await self.cog.load_loadout(interaction.guild.id, selected_name)
            msg = f"✅ **Loaded setup '{selected_name}'!**"
        else:
            await self.cog.delete_loadout(interaction.guild.id, selected_name)
            msg = f"🗑️ **Deleted setup '{selected_name}' permanently!**"

        embed = await self.cog.get_dashboard_embed(interaction.guild.id)
        await interaction.response.edit_message(content=msg, embed=embed, view=VotingDashboard(self.cog))


class LoadoutActionMenu(discord.ui.View):
    def __init__(self, action_type, loadouts_dict, guild, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(ActionSelect(action_type, loadouts_dict, guild, cog))

    @discord.ui.button(label="🔙 Cancel & Go Back", style=discord.ButtonStyle.grey, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.get_dashboard_embed(interaction.guild.id)
        await interaction.response.edit_message(content="🛠️ **Voting Dashboard**", embed=embed, view=VotingDashboard(self.cog))


# --- MAIN DASHBOARD VIEW ---

class VotingDashboard(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="➕ Add/Edit Role", style=discord.ButtonStyle.primary, row=0)
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Select a role below to change its voting power:**", view=RoleSelectMenu(self.cog))

    @discord.ui.button(label="💾 Save Loadout", style=discord.ButtonStyle.success, row=0)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SaveLoadoutModal(self.cog))

    @discord.ui.button(label="📦 Load Setup", style=discord.ButtonStyle.secondary, row=1)
    async def btn_load(self, interaction: discord.Interaction, button: discord.ui.Button):
        loadouts = await self.cog.get_loadouts_dict(interaction.guild.id)
        if not loadouts:
            await interaction.response.send_message("❌ No loadouts saved yet!", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="**Select a setup to overwrite your active roles:**",
            view=LoadoutActionMenu('load', loadouts, interaction.guild, self.cog)
        )

    @discord.ui.button(label="🗑️ Delete Setup", style=discord.ButtonStyle.danger, row=1)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        loadouts = await self.cog.get_loadouts_dict(interaction.guild.id)
        if not loadouts:
            await interaction.response.send_message("❌ No loadouts saved yet!", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="**⚠️ Select a setup to PERMANENTLY DELETE:**",
            view=LoadoutActionMenu('delete', loadouts, interaction.guild, self.cog)
        )

    @discord.ui.button(label="🧹 Clear Active", style=discord.ButtonStyle.danger, row=2)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clear_active_roles(interaction.guild.id)
        embed = await self.cog.get_dashboard_embed(interaction.guild.id)
        await interaction.response.edit_message(content="🧹 **Active setup cleared!**", embed=embed, view=self)


# --- THE MAIN COG ---

class Voting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- SETTINGS HELPERS ---
    async def get_active_roles_dict(self, guild_id):
        active = await settings.get(guild_id, 'voting', 'active_roles', default=[])
        return {int(role_id): int(power) for role_id, power in active} if active else {}

    async def set_active_roles(self, guild_id, roles_dict):
        payload = [[int(role_id), int(power)] for role_id, power in roles_dict.items()]
        await settings.set(guild_id, 'voting', 'active_roles', payload)

    async def set_active_role(self, guild_id, role_id, power):
        active = await self.get_active_roles_dict(guild_id)
        active[int(role_id)] = int(power)
        await self.set_active_roles(guild_id, active)

    async def clear_active_roles(self, guild_id):
        await settings.set(guild_id, 'voting', 'active_roles', [])

    async def get_loadouts_dict(self, guild_id):
        loadouts = await settings.get(guild_id, 'voting', 'loadouts', default={})
        return {name: [[int(role_id), int(power)] for role_id, power in values] for name, values in loadouts.items()} if loadouts else {}

    async def save_loadout(self, guild_id, name, roles_dict):
        loadouts = await self.get_loadouts_dict(guild_id)
        loadouts[name] = [[int(role_id), int(power)] for role_id, power in roles_dict.items()]
        await settings.set(guild_id, 'voting', 'loadouts', loadouts)

    async def delete_loadout(self, guild_id, name):
        loadouts = await self.get_loadouts_dict(guild_id)
        if name in loadouts:
            del loadouts[name]
            await settings.set(guild_id, 'voting', 'loadouts', loadouts)

    async def load_loadout(self, guild_id, name):
        loadouts = await self.get_loadouts_dict(guild_id)
        if name not in loadouts:
            return False
        roles = {role_id: power for role_id, power in loadouts[name]}
        await self.set_active_roles(guild_id, roles)
        return True

    async def get_dashboard_embed(self, guild_id):
        active = await self.get_active_roles_dict(guild_id)
        loadouts = await self.get_loadouts_dict(guild_id)

        embed = discord.Embed(title="⚙️ Voting Configuration Hub", color=discord.Color.blurple())

        if active:
            active_text = "".join([f"<@&{role_id}> : **{power}** power\n" for role_id, power in active.items()])
        else:
            active_text = "No custom powers active. Everyone has 1 vote."

        embed.add_field(name="🟢 Currently Active Setup", value=active_text, inline=False)

        if loadouts:
            loadout_text = "\n".join([f"• `{name}`" for name in loadouts.keys()])
        else:
            loadout_text = "No loadouts saved yet."

        embed.add_field(name="📦 Saved Loadouts", value=loadout_text, inline=False)
        return embed

    # --- COMMANDS ---
    @app_commands.command(name="voting_config", description="Open the main Voting Setup Dashboard")
    @app_commands.checks.has_permissions(administrator=True)
    async def voting_config(self, interaction: discord.Interaction):
        embed = await self.get_dashboard_embed(interaction.guild.id)
        await interaction.response.send_message(content="🛠️ **Voting Dashboard**", embed=embed, view=VotingDashboard(self), ephemeral=True)

    @app_commands.command(name="tally", description="Count votes with weighted power.")
    @app_commands.describe(
        poll_links="The message link(s) to the poll. Separate multiple links with spaces.",
        strict_mode="True = Disqualify over-voters. False (Default) = Dilute their vote power."
    )
    async def tally(self, interaction: discord.Interaction, poll_links: str, strict_mode: bool = False):
        await interaction.response.defer()

        target_locations = []
        for link in poll_links.split():
            try:
                parts = link.split('/')
                if 'discord.com' in link and len(parts) >= 3:
                    target_locations.append((int(parts[-2]), int(parts[-1])))
                else:
                    target_locations.append((interaction.channel.id, int(parts[-1])))
            except ValueError:
                await interaction.followup.send(f"⚠️ Invalid link format: `{link}`.")
                return

        if not target_locations:
            await interaction.followup.send("❌ No valid poll IDs found.")
            return

        user_votes_map, found_count = {}, 0

        for chan_id, msg_id in target_locations:
            try:
                target_channel = interaction.guild.get_channel(chan_id)
                if not target_channel:
                    continue
                target_msg = await target_channel.fetch_message(msg_id)
            except discord.HTTPException:
                continue

            if not target_msg.poll:
                continue

            found_count += 1
            for answer in target_msg.poll.answers:
                async for voter in answer.voters():
                    if voter.id not in user_votes_map:
                        user_votes_map[voter.id] = []
                    user_votes_map[voter.id].append(answer.text)

        if found_count == 0:
            await interaction.followup.send("❌ No polls could be read. Check permissions or links.")
            return

        role_configs = await self.get_active_roles_dict(interaction.guild.id)
        final_scores, disqualified_count, total_valid_voters = {}, 0, 0

        for user_id, choices in user_votes_map.items():
            member = interaction.guild.get_member(user_id)
            if not member:
                continue

            user_power, allowed_limit = 1, 1
            user_role_ids = [r.id for r in member.roles]
            for role_id, vote_power in role_configs.items():
                if role_id in user_role_ids and vote_power > user_power:
                    user_power = vote_power
                    allowed_limit = vote_power

            if len(choices) > allowed_limit:
                if strict_mode:
                    disqualified_count += 1
                    continue

            points_per_vote = user_power / len(choices)
            for choice in choices:
                final_scores[choice] = final_scores.get(choice, 0) + points_per_vote
            total_valid_voters += 1

        sorted_scores = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
        top_score = sorted_scores[0][1] if sorted_scores else 1

        desc = f"**Mode:** {'Strict ⛔' if strict_mode else 'Soft 🍦'}\n**Total Valid Voters:** {total_valid_voters}\n"
        if len(target_locations) > 1:
            desc += f"🔗 **Combined Polls:** {len(target_locations)}\n"
        if disqualified_count > 0:
            desc += f"🚫 **Disqualified:** {disqualified_count} users\n"
        desc += "───────────────────\n"

        for option, score in sorted_scores:
            fill = int((score / top_score) * 10) if top_score > 0 else 0
            desc += f"**{option}**\n{'▓' * fill}{'░' * (10 - fill)} **{score:.2f}**\n"

        embed = discord.Embed(title="📊 Combined Weighted Results", description=desc, color=discord.Color.gold())
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Voting(bot))
