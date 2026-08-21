import discord
from discord.ext import commands
from discord.ui import View, Select, Button, RoleSelect, ChannelSelect
from typing import Optional
from cogs.settings_helper import settings


class CogSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Twitch", value="twitch", description="Twitch notifications and options"),
            discord.SelectOption(label="Voting", value="voting", description="Voting cog settings"),
            discord.SelectOption(label="Free Stuff", value="free_stuff", description="free_stuff cog settings"),
            discord.SelectOption(label="Ratings", value="ratings", description="ratings cog settings"),
            discord.SelectOption(label="Voice", value="voice", description="voice cog settings"),
        ]
        super().__init__(placeholder="Select a cog to configure...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        cog = self.values[0]
        guild_id = interaction.guild.id if interaction.guild else 0
        items = await settings.all_for_guild(guild_id)
        filtered = [(k, v) for (c, k, v) in items if c == cog]

        embed = discord.Embed(title=f"Settings: {cog}", color=discord.Color.blurple())
        if filtered:
            for k, v in filtered:
                embed.add_field(name=k, value=str(v), inline=False)
        else:
            embed.description = "No configured settings for this cog. Use the buttons below to add settings."

        if cog == 'twitch':
            view = TwitchSettingsView(guild_id)
        else:
            view = CogSettingsView(cog, guild_id)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CogSettingsView(View):
    def __init__(self, cog_name: str, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog_name
        self.guild_id = guild_id

    async def _build_embed(self) -> discord.Embed:
        items = await settings.all_for_guild(self.guild_id)
        filtered = [(k, v) for (c, k, v) in items if c == self.cog]
        embed = discord.Embed(title=f"Settings: {self.cog}", color=discord.Color.blurple())
        if filtered:
            for k, v in filtered:
                embed.add_field(name=k, value=str(v), inline=False)
        else:
            embed.description = "No configured settings for this cog. Use the buttons below to add settings."
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to change settings.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Show Current Settings", style=discord.ButtonStyle.secondary)
    async def show_current(self, interaction: discord.Interaction, button: Button):
        embed = await self._build_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Get Setting", style=discord.ButtonStyle.secondary)
    async def ui_get_setting(self, interaction: discord.Interaction, button: Button):
        modal = GetSettingModal(self.cog, self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Set Setting", style=discord.ButtonStyle.primary)
    async def ui_set_setting(self, interaction: discord.Interaction, button: Button):
        modal = SetSettingModal(self.cog, self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="List All Settings", style=discord.ButtonStyle.secondary)
    async def ui_list_all(self, interaction: discord.Interaction, button: Button):
        items = await settings.all_for_guild(self.guild_id)
        if not items:
            return await interaction.response.send_message("No settings configured for this guild.", ephemeral=True)
        lines = [f"{c}.{k} = {v}" for (c, k, v) in items]
        text = "\n".join(lines)
        await interaction.response.send_message(f"Settings:\n```\n{text}\n```", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Settings menu closed.", embed=None, view=None)


class TwitchSettingsView(CogSettingsView):
    def __init__(self, guild_id: int):
        super().__init__('twitch', guild_id)

    @discord.ui.button(label="Set Auto-delete", style=discord.ButtonStyle.primary)
    async def set_auto(self, interaction: discord.Interaction, button: Button):
        view = AutoDeleteView(self.cog, self.guild_id)
        await interaction.response.edit_message(embed=view.embed, view=view)

    @discord.ui.button(label="Set Mention Type", style=discord.ButtonStyle.primary)
    async def set_mention_type(self, interaction: discord.Interaction, button: Button):
        view = MentionTypeView(self.cog, self.guild_id)
        await interaction.response.edit_message(embed=view.embed, view=view)

    @discord.ui.button(label="Set Mention Role", style=discord.ButtonStyle.primary)
    async def set_mention_role(self, interaction: discord.Interaction, button: Button):
        view = MentionRoleView(self.cog, self.guild_id)
        await interaction.response.edit_message(embed=view.embed, view=view)

    @discord.ui.button(label="Set Notify Channel", style=discord.ButtonStyle.primary)
    async def set_notify_channel(self, interaction: discord.Interaction, button: Button):
        view = NotifyChannelView(self.cog, self.guild_id)
        await interaction.response.edit_message(embed=view.embed, view=view)

    @discord.ui.button(label="Delete After Stream Ends", style=discord.ButtonStyle.primary)
    async def set_delete_on_end(self, interaction: discord.Interaction, button: Button):
        view = DeleteOnEndView(self.cog, self.guild_id)
        await interaction.response.edit_message(embed=view.embed, view=view)


# --- MODALS ---

class GetSettingModal(discord.ui.Modal, title="Get Setting"):
    key = discord.ui.TextInput(label="Setting Key", placeholder="e.g. notify_channel_id", required=True)

    def __init__(self, cog_name: str, guild_id: int):
        super().__init__()
        self.cog_name = cog_name
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key.value.strip()
        val = await settings.get(self.guild_id, self.cog_name, key, default=None)
        await interaction.response.send_message(f"`{self.cog_name}.{key}` = {val}", ephemeral=True)


class SetSettingModal(discord.ui.Modal, title="Set Setting"):
    key = discord.ui.TextInput(label="Setting Key", placeholder="e.g. notify_channel_id", required=True)
    value = discord.ui.TextInput(label="Value (JSON if possible)", style=discord.TextStyle.long, required=True)

    def __init__(self, cog_name: str, guild_id: int):
        super().__init__()
        self.cog_name = cog_name
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        import json
        key = self.key.value.strip()
        raw = self.value.value.strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        await settings.set(self.guild_id, self.cog_name, key, parsed)
        await interaction.response.send_message(f"✅ Set `{self.cog_name}.{key}` = {parsed}", ephemeral=True)


# --- SUB-SETTING VIEWS ---

class AutoDeleteView(View):
    def __init__(self, cog_name: str, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog_name
        self.guild_id = guild_id
        self.embed = discord.Embed(title=f"{cog_name} Auto-delete", description="Choose the delay before notifications are deleted.", color=discord.Color.blurple())

        options = [
            discord.SelectOption(label="Disabled", value="0", description="Keep the message permanently."),
            discord.SelectOption(label="10 seconds", value="10"),
            discord.SelectOption(label="30 seconds", value="30"),
            discord.SelectOption(label="60 seconds", value="60"),
            discord.SelectOption(label="120 seconds", value="120"),
            discord.SelectOption(label="300 seconds", value="300"),
        ]
        self.select = Select(placeholder="Select auto-delete delay...", min_values=1, max_values=1, options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        value = int(self.select.values[0])
        await settings.set(self.guild_id, self.cog, 'auto_delete_seconds', value)
        await interaction.response.edit_message(content=f"✅ Auto-delete set to {value} seconds.", embed=None, view=None)


class MentionTypeView(View):
    def __init__(self, cog_name: str, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog_name
        self.guild_id = guild_id
        self.embed = discord.Embed(title=f"{cog_name} Mention Type", description="Choose how live notifications should mention members.", color=discord.Color.blurple())

        options = [
            discord.SelectOption(label="None", value="none", description="No mention."),
            discord.SelectOption(label="Role", value="role", description="Mention a configured role."),
            discord.SelectOption(label="Here", value="here", description="Mention @here."),
            discord.SelectOption(label="Everyone", value="everyone", description="Mention @everyone."),
        ]
        self.select = Select(placeholder="Select a mention type...", min_values=1, max_values=1, options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        value = self.select.values[0]
        await settings.set(self.guild_id, self.cog, 'mention_type', value)
        await interaction.response.edit_message(content=f"✅ mention_type set to {value}.", embed=None, view=None)


class MentionRoleView(View):
    def __init__(self, cog_name: str, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog_name
        self.guild_id = guild_id
        self.embed = discord.Embed(title=f"{cog_name} Mention Role", description="Select the role to mention when mention type is Role.", color=discord.Color.blurple())
        self.role_select = RoleSelect(placeholder="Select a role...", min_values=1, max_values=1)
        self.role_select.callback = self.on_role_select
        self.add_item(self.role_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to change settings.", ephemeral=True)
            return False
        return True

    async def on_role_select(self, interaction: discord.Interaction):
        role = self.role_select.values[0]
        await settings.set(self.guild_id, self.cog, 'mention_role_id', int(role.id))
        await interaction.response.edit_message(content=f"✅ mention_role set to {role.mention}.", embed=None, view=None)


class NotifyChannelView(View):
    def __init__(self, cog_name: str, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog_name
        self.guild_id = guild_id
        self.embed = discord.Embed(title=f"{cog_name} Notify Channel", description="Select the channel to send notifications into.", color=discord.Color.blurple())
        self.channel_select = ChannelSelect(placeholder="Select a channel...", min_values=1, max_values=1)
        self.channel_select.callback = self.on_channel_select
        self.add_item(self.channel_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to change settings.", ephemeral=True)
            return False
        return True

    async def on_channel_select(self, interaction: discord.Interaction):
        channel = self.channel_select.values[0]
        await settings.set(self.guild_id, self.cog, 'notify_channel_id', int(channel.id))
        await interaction.response.edit_message(content=f"✅ notify_channel set to <#{channel.id}>.", embed=None, view=None)


class DeleteOnEndView(View):
    def __init__(self, cog_name: str, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog_name
        self.guild_id = guild_id
        self.embed = discord.Embed(
            title=f"{cog_name} Delete After Stream Ends",
            description="Choose whether the live notification should be deleted when the stream ends.",
            color=discord.Color.blurple()
        )

        options = [
            discord.SelectOption(label="Keep live notification", value="0", description="The message stays after stream end."),
            discord.SelectOption(label="Delete when stream ends", value="1", description="Remove the go-live notification when the stream finishes."),
        ]
        self.select = Select(placeholder="Select delete-on-end behavior...", min_values=1, max_values=1, options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        value = int(self.select.values[0])
        await settings.set(self.guild_id, self.cog, 'delete_on_stream_end', value)
        description = "will be deleted when the stream ends" if value else "will remain after stream end"
        await interaction.response.edit_message(content=f"✅ Live notifications {description}.", embed=None, view=None)


class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="settings", invoke_without_command=True, with_app_command=True)
    async def settings_group(self, ctx):
        """Open the settings UI or use subcommands."""
        if ctx.invoked_subcommand is None:
            view = View()
            view.add_item(CogSelect())
            interaction = getattr(ctx, 'interaction', None)
            if interaction:
                try:
                    await interaction.response.send_message("Open settings menu:", view=view, ephemeral=True)
                except Exception:
                    await ctx.reply("Open settings menu:", view=view)
            else:
                await ctx.reply("Open settings menu:", view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))