import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import time
import random
from cogs.settings_helper import settings

DB_FILE = "bugsbot.db"
MIN_LIFETIME = 10 
CLEANUP_INTERVAL = 30

# ─────────────────────────────────────────────
# CONSTANTS & ASSETS
# ─────────────────────────────────────────────
DENY_GIFS = [
    "https://tenor.com/view/agathe-emil-south-park-im-gonna-click-on-decline-decline-gif-20596371",
    "https://tenor.com/view/decline-denied-no-nope-not-happening-gif-16014268",
    "https://tenor.com/view/brexby-gif-24077625",
    "https://tenor.com/view/thinking-issa-rae-bustle-hmm-uhm-gif-4132357844606813462",
    "https://tenor.com/view/decline-denied-awkward-gif-22072497"
]

# ─────────────────────────────────────────────
# CONTROL PANEL VIEW
# ─────────────────────────────────────────────
class VoiceControlView(discord.ui.View):
    def __init__(self, cog, vc_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.vc_id = vc_id

    async def get_owner_id(self):
        try:
            self.cog.cursor.execute("SELECT owner_id FROM active_vcs WHERE channel_id = ?", (self.vc_id,))
            row = self.cog.cursor.fetchone()
            return row[0] if row else None
        except: return None

    def get_vc(self, guild):
        return guild.get_channel(self.vc_id)

    async def build_embed(self, vc):
        """Generates a premium, seamless embed for the control panel."""
        owner_id = await self.get_owner_id()
        owner = vc.guild.get_member(owner_id) if owner_id else None
        
        perms = vc.permissions_for(vc.guild.default_role)
        is_locked = perms.connect is False

        # 1. The Seamless Trick: Match Discord's dark background
        embed = discord.Embed(
            color=discord.Color.from_str("#2B2D31") 
        )
        
        # 2. Cleaner Header
        embed.set_author(name="VOICE CONTROL DASHBOARD", icon_url=self.cog.bot.user.display_avatar.url if self.cog.bot.user else None)
        
        if owner:
            embed.set_thumbnail(url=owner.display_avatar.url)
            
        clean_name = vc.name.replace("🔴 ", "").replace("🟢 ", "").replace("🔴", "").replace("🟢", "").strip()
        
        # 3. Blockquotes for formatting
        status_text = "> 🔴 **Locked**\n> Visitors must knock." if is_locked else "> 🟢 **Open**\n> Publicly accessible."
        
        embed.add_field(name="Channel", value=f"> 🔊 **{clean_name}**", inline=True)
        embed.add_field(name="Status", value=status_text, inline=True)
        
        owner_mention = owner.mention if owner else "Unknown"
        embed.add_field(name="👑 Owner", value=f"> {owner_mention}", inline=False)
        
        # 4. Animated GIF Banner
        embed.set_image(url="https://i.pinimg.com/originals/ce/c3/e9/cec3e9a8a1fd05b7d82c263a2188f8db.gif")
        
        return embed

    async def update_buttons(self, vc):
        """Updates the button style/label based on channel permissions"""
        perms = vc.permissions_for(vc.guild.default_role)
        button = [x for x in self.children if hasattr(x, "custom_id") and x.custom_id == "vc_toggle"][0]

        if perms.connect is False:
            button.label = "Unlock Channel"
            button.emoji = "🔓"
            button.style = discord.ButtonStyle.success 
        else:
            button.label = "Lock Channel"
            button.emoji = "🔒"
            button.style = discord.ButtonStyle.secondary 

    # --- ROW 0: SETTINGS ---
    @discord.ui.button(label="Lock/Unlock", style=discord.ButtonStyle.secondary, custom_id="vc_toggle", row=0)
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_owner = await self.get_owner_id()
        if not current_owner or interaction.user.id != current_owner:
            return await interaction.response.send_message("❌ Owner only.", ephemeral=True)

        vc = self.get_vc(interaction.guild)
        if not vc: return await interaction.response.send_message("❌ VC missing.", ephemeral=True)

        perms = vc.permissions_for(interaction.guild.default_role)
        clean_name = vc.name.replace("🔴 ", "").replace("🟢 ", "").replace("🔴", "").replace("🟢", "").strip()

        if perms.connect is False:
            await vc.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 **Unlocked:** Everyone can join.", ephemeral=True)
            new_name = f"🟢 {clean_name}"
        else:
            await vc.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 **Locked:** Visitors must Knock.", ephemeral=True)
            new_name = f"🔴 {clean_name}"

        try:
            await vc.edit(name=new_name)
        except discord.errors.HTTPException:
            pass # Rate limited, permissions are still updated

        await self.update_buttons(vc)
        new_embed = await self.build_embed(vc)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Rename", emoji="📝", style=discord.ButtonStyle.secondary, custom_id="vc_rename", row=0)
    async def rename_vc(self, interaction: discord.Interaction, _):
        current_owner = await self.get_owner_id()
        if interaction.user.id != current_owner: return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        
        modal = discord.ui.Modal(title="Rename Channel")
        name_input = discord.ui.TextInput(label="New Name", min_length=1, max_length=50)
        modal.add_item(name_input)
        
        async def modal_callback(i: discord.Interaction):
            vc = self.get_vc(i.guild)
            if vc:
                perms = vc.permissions_for(i.guild.default_role)
                dot = "🔴 " if perms.connect is False else "🟢 "
                
                clean_new_name = name_input.value.replace("🔴 ", "").replace("🟢 ", "").replace("🔴", "").replace("🟢", "").strip()
                new_full_name = f"{dot}{clean_new_name}"

                try:
                    await vc.edit(name=new_full_name)
                except discord.errors.HTTPException:
                    pass # Rate limited

                await self.update_buttons(vc)
                new_embed = await self.build_embed(vc)
                await i.message.edit(embed=new_embed, view=self)
                await i.response.send_message(f"✅ Renamed to **{new_full_name}**", ephemeral=True)
        
        modal.on_submit = modal_callback
        await interaction.response.send_modal(modal)

    # --- ROW 1: MODERATION & ACCESS ---
    @discord.ui.button(label="Kick/Ban", emoji="👋", style=discord.ButtonStyle.danger, custom_id="vc_kick", row=1)
    async def kick_menu(self, interaction: discord.Interaction, _):
        current_owner = await self.get_owner_id()
        if interaction.user.id != current_owner: return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        vc = self.get_vc(interaction.guild)
        if not vc: return 
        
        options = []
        for member in vc.members:
            if member.id != interaction.user.id and not member.bot:
                options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        
        if not options: return await interaction.response.send_message("⚠️ No one to kick!", ephemeral=True)

        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select user to kick...", options=options[:25])
        
        async def callback(i: discord.Interaction):
            target_id = int(select.values[0])
            target = i.guild.get_member(target_id)
            vc_channel = self.get_vc(i.guild)
            
            if target and vc_channel:
                await vc_channel.set_permissions(target, connect=False)
                try:
                    await target.move_to(None)
                    await i.response.send_message(f"👋 **Kicked & Blocked** {target.mention}.", ephemeral=True)
                except:
                    await i.response.send_message(f"⚠️ Permissions revoked for {target.mention}, but could not disconnect them.", ephemeral=True)
            else:
                await i.response.send_message("❌ User not found.", ephemeral=True)
        
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select user to kick & block:", view=view, ephemeral=True)

    @discord.ui.button(label="Knock", emoji="✊", style=discord.ButtonStyle.primary, custom_id="vc_knock", row=1)
    async def knock(self, interaction: discord.Interaction, _):
        current_owner = await self.get_owner_id()
        if interaction.user.id == current_owner:
            return await interaction.response.send_message("⚠️ You own this channel!", ephemeral=True)
        
        vc = self.get_vc(interaction.guild)
        if not vc: return
        
        # ANTI-SPAM CHECK
        self.cog.cursor.execute("SELECT 1 FROM pending_requests WHERE user_id = ? AND channel_id = ?", (interaction.user.id, vc.id))
        if self.cog.cursor.fetchone():
            return await interaction.response.send_message("⏳ **Please Wait:** You already have a pending request.", ephemeral=True)

        await interaction.response.send_message("✊ Knock sent!", ephemeral=True)
        
        # PING THE OWNER WITH AN EMBED
        embed = discord.Embed(
            title="🔔 Access Request",
            description=f"{interaction.user.mention} is knocking and wants to join **{vc.name}**!",
            color=discord.Color.from_str("#2B2D31") # Match the seamless aesthetic
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        msg = await interaction.channel.send(
            content=f"<@{current_owner}>", # Ghost ping outside the embed
            embed=embed,
            view=JoinRequestView(self.cog, vc, interaction.user, current_owner)
        )
        
        try:
            self.cog.cursor.execute("INSERT INTO pending_requests VALUES (?, ?, ?)", (interaction.user.id, vc.id, msg.id))
            self.cog.conn.commit()
        except: pass


# ─────────────────────────────────────────────
# JOIN REQUEST VIEW
# ─────────────────────────────────────────────
class JoinRequestView(discord.ui.View):
    def __init__(self, cog, vc, requester, owner_id):
        super().__init__(timeout=None) 
        self.cog = cog 
        self.vc = vc
        self.requester = requester
        self.owner_id = owner_id

    async def clear_pending_status(self):
        try:
            self.cog.cursor.execute("DELETE FROM pending_requests WHERE user_id = ? AND channel_id = ?", (self.requester.id, self.vc.id))
            self.cog.conn.commit()
        except: pass

    @discord.ui.button(label="Allow ✅", style=discord.ButtonStyle.success)
    async def allow(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.owner_id: return
        
        await self.clear_pending_status()
        await self.vc.set_permissions(self.requester, connect=True)
        
        # Edit the original request embed
        try:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "✅ Access Granted"
            embed.description = f"{self.requester.mention} has been allowed into the channel."
            await interaction.message.edit(content=None, embed=embed, view=None)
            
            self.cog.cursor.execute("INSERT INTO access_grants VALUES (?, ?, ?)", (self.requester.id, self.vc.id, interaction.message.id))
        except Exception as e: print(f"DB Error 1: {e}")

        # Send a styled public response
        response_embed = discord.Embed(
            description=f"> ✅ **Access Granted!**\n> {self.requester.mention} has been invited in.",
            color=discord.Color.from_str("#2B2D31")
        )
        await interaction.response.send_message(embed=response_embed, ephemeral=False)
        msg = await interaction.original_response()
        
        try:
            self.cog.cursor.execute("INSERT INTO access_grants VALUES (?, ?, ?)", (self.requester.id, self.vc.id, msg.id))
            self.cog.conn.commit()
        except Exception as e: print(f"DB Error 2: {e}")

        self.stop()

    @discord.ui.button(label="Deny 🛑", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.owner_id: return
        
        await self.clear_pending_status()
        
        # Edit the original request embed
        try: 
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "🚫 Access Denied"
            embed.description = f"{self.requester.mention}'s request was denied."
            await interaction.message.edit(content=None, embed=embed, view=None)
        except: pass
        
        # Send a styled public response with the random Tenor GIF
        response_embed = discord.Embed(
            description=f"> 🚫 **Access Denied.**\n> Sorry {self.requester.mention}, not this time.",
            color=discord.Color.from_str("#2B2D31")
        )
        
        await interaction.response.send_message(
            content=random.choice(DENY_GIFS), 
            embed=response_embed, 
            ephemeral=False
        )
        self.stop()


# ─────────────────────────────────────────────
# MAIN COG
# ─────────────────────────────────────────────
class Voice(commands.GroupCog, name="voice"):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        self.setup_db()
        self.cleanup_task.start()

    def setup_db(self):
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS active_vcs (channel_id INTEGER PRIMARY KEY, owner_id INTEGER, created_at INTEGER, panel_msg_id INTEGER, thread_id INTEGER)""")
        
        try:
            self.cursor.execute("ALTER TABLE active_vcs ADD COLUMN thread_id INTEGER")
            self.conn.commit()
        except: pass 

        # Add creator_id for ownership restoration
        try:
            self.cursor.execute("ALTER TABLE active_vcs ADD COLUMN creator_id INTEGER")
            self.cursor.execute("UPDATE active_vcs SET creator_id = owner_id WHERE creator_id IS NULL")
            self.conn.commit()
        except: pass

        self.cursor.execute("""CREATE TABLE IF NOT EXISTS vc_titles (user_id INTEGER PRIMARY KEY, default_title TEXT)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS access_grants (user_id INTEGER, channel_id INTEGER, message_id INTEGER)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS pending_requests (user_id INTEGER, channel_id INTEGER, message_id INTEGER)""")
        self.conn.commit()

    def cog_unload(self):
        self.cleanup_task.cancel()
        self.conn.close()

    # ───────────────── HELPERS ─────────────────
    async def get_hub(self, guild):
        try:
            channel_id = await settings.get(guild.id, 'voice', 'hub_text_id', default=None)
            return guild.get_channel(int(channel_id)) if channel_id else None
        except: return None

    async def get_join_vc(self, guild):
        try:
            channel_id = await settings.get(guild.id, 'voice', 'join_vc_id', default=None)
            return guild.get_channel(int(channel_id)) if channel_id else None
        except: return None

    def get_default_title(self, user_id):
        try:
            self.cursor.execute("SELECT default_title FROM vc_titles WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            return row[0] if row else None
        except: return None

    # ───────────────── DB SAFE DELETION ─────────────────
    async def delete_channel_data(self, channel_id, guild):
        panel_msg_id = None
        thread_id = None
        
        try:
            self.cursor.execute("SELECT panel_msg_id, thread_id FROM active_vcs WHERE channel_id = ?", (channel_id,))
            row = self.cursor.fetchone()
            if row: 
                panel_msg_id = row[0]
                thread_id = row[1]
            self.conn.commit() 
        except Exception: return

        if thread_id:
            try:
                thread = guild.get_thread(thread_id) or await guild.fetch_channel(thread_id)
                if thread: await thread.delete()
            except: pass

        hub = await self.get_hub(guild)
        if hub and panel_msg_id:
            try:
                msg = await hub.fetch_message(panel_msg_id)
                await msg.delete()
            except: pass

        vc = guild.get_channel(channel_id)
        if vc:
            try: await vc.delete()
            except: pass
        
        try:
            self.cursor.execute("DELETE FROM active_vcs WHERE channel_id = ?", (channel_id,))
            self.cursor.execute("DELETE FROM access_grants WHERE channel_id = ?", (channel_id,))
            self.cursor.execute("DELETE FROM pending_requests WHERE channel_id = ?", (channel_id,))
            self.conn.commit()
        except: pass

    # ───────────────── CLEANUP TASK ─────────────────
    @tasks.loop(seconds=CLEANUP_INTERVAL)
    async def cleanup_task(self):
        now = int(time.time())
        try:
            self.cursor.execute("SELECT channel_id, created_at FROM active_vcs")
            rows = self.cursor.fetchall()
            self.conn.commit() 
        except: return

        for channel_id, created_at in rows:
            vc_exists = False
            for guild in self.bot.guilds:
                vc = guild.get_channel(channel_id)
                if vc:
                    vc_exists = True
                    if len([m for m in vc.members if not m.bot]) == 0 and (now - created_at > MIN_LIFETIME):
                        await self.delete_channel_data(channel_id, guild)
            if not vc_exists:
                try:
                    self.cursor.execute("DELETE FROM active_vcs WHERE channel_id = ?", (channel_id,))
                    self.conn.commit()
                except: pass

    # ───────────────── COMMANDS ─────────────────
    @app_commands.command(name="setup")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_voice(self, interaction: discord.Interaction, channel: discord.VoiceChannel, interface: discord.TextChannel):
        await settings.set(interaction.guild.id, 'voice', 'join_vc_id', int(channel.id))
        await settings.set(interaction.guild.id, 'voice', 'hub_text_id', int(interface.id))
        await interaction.response.send_message(f"✅ Setup Complete!\nJoin: {channel.mention}\nInterface: {interface.mention}", ephemeral=True)

    @app_commands.command(name="name")
    async def set_name(self, interaction: discord.Interaction, name: str):
        self.cursor.execute("INSERT OR REPLACE INTO vc_titles (user_id, default_title) VALUES (?, ?)", (interaction.user.id, name))
        self.conn.commit()
        await interaction.response.send_message(f"✅ Default Name Set: **{name}**", ephemeral=True)

    @app_commands.command(name="force_name", description="Admin: Change a user's default VC name")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_name(self, interaction: discord.Interaction, target: discord.Member, name: str):
        self.cursor.execute("INSERT OR REPLACE INTO vc_titles (user_id, default_title) VALUES (?, ?)", (target.id, name))
        self.conn.commit()
        
        self.cursor.execute("SELECT channel_id FROM active_vcs WHERE owner_id = ?", (target.id,))
        row = self.cursor.fetchone()
        
        msg_extra = ""
        if row:
            active_vc = interaction.guild.get_channel(row[0])
            if active_vc:
                try:
                    await active_vc.edit(name=name)
                    msg_extra = " (and renamed their active channel)"
                except:
                    msg_extra = " (but failed to rename active channel)"

        await interaction.response.send_message(f"✅ Set **{target.display_name}'s** default VC name to: **{name}**{msg_extra}", ephemeral=True)

    @app_commands.command(name="invite", description="Invite a user to your private voice channel.")
    @app_commands.describe(member="The user you want to invite")
    async def invite(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ You must be in your voice channel to invite someone!", ephemeral=True)
        
        user_vc = interaction.user.voice.channel

        self.cursor.execute("SELECT thread_id FROM active_vcs WHERE channel_id = ? AND owner_id = ?", 
                           (user_vc.id, interaction.user.id))
        result = self.cursor.fetchone()

        if not result:
            return await interaction.response.send_message("❌ You can only invite people to a voice channel that you own!", ephemeral=True)
        
        thread_id = result[0]

        await user_vc.set_permissions(member, connect=True, reason=f"Invited by {interaction.user}")
        await interaction.response.send_message(f"✅ {member.display_name} has been invited and granted access.", ephemeral=True)

        thread = interaction.guild.get_thread(thread_id)
        if not thread:
            try:
                thread = await interaction.guild.fetch_channel(thread_id)
            except: pass

        if thread:
            await thread.send(f"🎉 Hey {member.mention}! {interaction.user.mention} has invited you to join their voice channel: {user_vc.mention}")

    # ───────────────── EVENTS ─────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        if before.channel and after.channel and before.channel.id == after.channel.id: return

        # 1. JOINING A CUSTOM VC
        if after.channel:
            try:
                self.cursor.execute("SELECT owner_id, thread_id, creator_id FROM active_vcs WHERE channel_id = ?", (after.channel.id,))
                vc_row = self.cursor.fetchone()
                
                if vc_row:
                    owner_id = vc_row[0]
                    thread_id = vc_row[1]
                    creator_id = vc_row[2] if len(vc_row) > 2 else None

                    # --- AUTO-RESTORE OWNERSHIP FOR ORIGINAL CREATOR ---
                    if creator_id and member.id == creator_id and member.id != owner_id:
                        try:
                            self.cursor.execute("UPDATE active_vcs SET owner_id = ? WHERE channel_id = ?", (member.id, after.channel.id))
                            self.conn.commit()
                        except: pass

                        old_owner = after.channel.guild.get_member(owner_id)
                        if old_owner:
                            await after.channel.set_permissions(old_owner, overwrite=None)
                            await after.channel.set_permissions(old_owner, connect=True)
                            
                        await after.channel.set_permissions(member, connect=True, move_members=True, manage_channels=True)

                        if thread_id:
                            try:
                                thread = member.guild.get_thread(thread_id) or await member.guild.fetch_channel(thread_id)
                                if thread:
                                    await thread.send(f"👑 **Ownership Restored**\nThe original creator has rejoined. {member.mention} is now the owner again.")
                            except: pass

                    # --- AUTO-WHITELIST DRAGGED/JOINING USERS ---
                    elif member.id != owner_id:
                        overwrite = after.channel.overwrites_for(member)
                        if overwrite.connect is not True:
                            overwrite.connect = True
                            try:
                                await after.channel.set_permissions(member, overwrite=overwrite)
                            except: pass

                    # Cleanup Access Msgs
                    self.cursor.execute("SELECT message_id FROM access_grants WHERE user_id = ? AND channel_id = ?", (member.id, after.channel.id))
                    grant_rows = self.cursor.fetchall()
                    
                    if grant_rows and thread_id:
                        try:
                            thread = member.guild.get_thread(thread_id) or await member.guild.fetch_channel(thread_id)
                            if thread:
                                for (msg_id,) in grant_rows:
                                    try:
                                        msg = await thread.fetch_message(msg_id)
                                        await msg.delete()
                                    except: pass
                        except Exception as e: print(f"Clean error: {e}")
                    
                    self.cursor.execute("DELETE FROM access_grants WHERE user_id = ? AND channel_id = ?", (member.id, after.channel.id))
                    self.conn.commit()
            except Exception as e: 
                print(f"Error checking joining logic: {e}")

        # 2. LEAVING
        if before.channel:
            try:
                self.cursor.execute("SELECT owner_id, panel_msg_id, thread_id FROM active_vcs WHERE channel_id = ?", (before.channel.id,))
                row = self.cursor.fetchone()
                self.conn.commit()
            except: row = None
            
            if row:
                current_owner_id, panel_msg_id, thread_id = row
                vc = before.channel
                remaining_members = [m for m in vc.members if not m.bot]

                if len(remaining_members) == 0:
                    await self.delete_channel_data(vc.id, member.guild)
                
                elif member.id == current_owner_id:
                    new_owner = remaining_members[0]
                    try:
                        self.cursor.execute("UPDATE active_vcs SET owner_id = ? WHERE channel_id = ?", (new_owner.id, vc.id))
                        self.conn.commit()
                    except: pass

                    await vc.set_permissions(member, overwrite=None)
                    await vc.set_permissions(new_owner, connect=True, move_members=True, manage_channels=True)

                    if thread_id:
                        try:
                            thread = member.guild.get_thread(thread_id) or await member.guild.fetch_channel(thread_id)
                            if thread:
                                await thread.send(f"👑 **Ownership Transfer**\nPrevious owner left. {new_owner.mention} is now the owner.")
                        except: pass

        # 3. CREATING
        join_vc = await self.get_join_vc(member.guild)
        hub = await self.get_hub(member.guild)

        if not join_vc or not hub: return

        if after.channel and after.channel.id == join_vc.id:
            try:
                user_title = self.get_default_title(member.id)
                base_title = user_title if user_title else f"{member.name}'s VC"
                
                clean_title = base_title.replace("🔴 ", "").replace("🟢 ", "").replace("🔴", "").replace("🟢", "").strip()
                title = f"🔴 {clean_title}"

                vc = await member.guild.create_voice_channel(title, category=join_vc.category)
                
                await vc.set_permissions(member.guild.default_role, connect=False)
                await vc.set_permissions(member, connect=True, move_members=True, manage_channels=True)
                await member.move_to(vc)

                # --- NEW SEAMLESS HUB EMBED ---
                hub_embed = discord.Embed(
                    description=f"> 🔊 **{title}** is currently active.\n> ⬇️ Open the thread below to request access or manage settings.",
                    color=discord.Color.from_str("#2B2D31")
                )
                hub_embed.set_author(name=f"{member.display_name}'s Voice Channel", icon_url=member.display_avatar.url)
                
                directory_msg = await hub.send(embed=hub_embed)
                thread = await directory_msg.create_thread(name=f"🔒 Join Request - {member.name}")
                
                # --- NEW CONTROL PANEL EMBED ---
                view = VoiceControlView(self, vc.id)
                await view.update_buttons(vc) # Initialize button state
                panel_embed = await view.build_embed(vc)
                
                await thread.send(embed=panel_embed, view=view)

                try:
                    self.cursor.execute("INSERT INTO active_vcs (channel_id, owner_id, created_at, panel_msg_id, thread_id, creator_id) VALUES (?, ?, ?, ?, ?, ?)", (vc.id, member.id, int(time.time()), directory_msg.id, thread.id, member.id))
                    self.conn.commit()
                except Exception as e: 
                    try:
                        self.cursor.execute("INSERT INTO active_vcs VALUES (?, ?, ?, ?, ?)", (vc.id, member.id, int(time.time()), directory_msg.id, thread.id))
                        self.conn.commit()
                    except Exception as e2:
                        print(f"DB Insert Error: {e} | {e2}")
                
                refetched_vc = member.guild.get_channel(vc.id)
                if refetched_vc and len([m for m in refetched_vc.members if not m.bot]) == 0:
                    await self.delete_channel_data(refetched_vc.id, member.guild)

            except Exception as e:
                print(f"Voice Error: {e}")

async def setup(bot):
    await bot.add_cog(Voice(bot))