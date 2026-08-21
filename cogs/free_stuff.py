import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import sqlite3
import datetime
from cogs.settings_helper import settings

# API Source for Free Games
GP_API = "https://www.gamerpower.com/api/giveaways?type=game&platform=pc"

# Visual configuration for different platforms
PLATFORMS = {
    "steam": {"name": "Steam", "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/512px-Steam_icon_logo.svg.png"},
    "epic": {"name": "Epic Games", "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/512px-Epic_Games_logo.svg.png"},
    "itch": {"name": "Itch.io", "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/79/Itch.io_logo.svg/512px-Itch.io_logo.svg.png"},
    "gog": {"name": "GOG.com", "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/GOG.com_logo.svg/512px-GOG.com_logo.svg.png"},
    "xbox": {"name": "Xbox", "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/Xbox_one_logo.svg/512px-Xbox_one_logo.svg.png"},
    "default": {"name": "PC", "icon": "https://cdn-icons-png.flaticon.com/512/860/860085.png"}
}

class FreeStuff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect('bugsbot.db')
        self.cursor = self.conn.cursor()
        self.setup_db()
        self.free_game_loop.start()

    def setup_db(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS free_history (
                promo_id INTEGER PRIMARY KEY,
                title TEXT,
                date_added INTEGER
            )
        """)
        self.conn.commit()

    def cog_unload(self):
        self.free_game_loop.cancel()
        self.conn.close()

    def get_platform_info(self, platform_str):
        platform_str = str(platform_str).lower()
        for key, data in PLATFORMS.items():
            if key in platform_str:
                return data
        return PLATFORMS["default"]

    # --- AUTOMATED FREE GAMES ---

    @tasks.loop(minutes=60)
    async def free_game_loop(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(GP_API) as resp:
                    if resp.status != 200:
                        print(f"⚠️ GamerPower API Error: {resp.status}")
                        return
                    data = await resp.json()
            except Exception as e:
                print(f"⚠️ Free Game Fetch Error: {e}")
                return
        
        for item in data:
            promo_id = int(item.get("id"))
            title = item.get("title")
            url = item.get("open_giveaway_url")
            image = item.get("image")
            platform = item.get("platforms")
            end_date = item.get("end_date") 
            worth = item.get("worth", "N/A")
            
            self.cursor.execute("SELECT 1 FROM free_history WHERE promo_id = ?", (promo_id,))
            if self.cursor.fetchone():
                continue 

            try:
                self.cursor.execute("INSERT INTO free_history (promo_id, title, date_added) VALUES (?, ?, ?)", 
                                    (promo_id, title, int(datetime.datetime.now().timestamp())))
                self.conn.commit()
            except:
                continue

            print(f"🎁 Found new free game: {title}")
            await self.broadcast_game(title, url, image, platform, end_date, worth)

    async def broadcast_game(self, title, url, image, platform, end_date, worth):
        raw_settings = await settings.all_for_cog('free_stuff')
        guild_configs = {}
        for guild_id, key, value in raw_settings:
            guild_configs.setdefault(guild_id, {})[key] = value

        if not guild_configs:
            return

        style = self.get_platform_info(platform)
        
        end_str = "Unknown"
        if end_date and end_date != "N/A":
            try:
                dt = datetime.datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=datetime.timezone.utc)
                end_str = f"<t:{int(dt.timestamp())}:d>"
            except ValueError:
                end_str = end_date

        worth_str = ""
        if worth and worth != "N/A" and worth != "Free":
            worth_str = f"~~{worth}~~ "

        description = f"{worth_str}**Free** until {end_str}\n\n[**Open in browser** ↗]({url})"

        embed = discord.Embed(
            title=title, 
            description=description, 
            color=0x2B2D31
        )
        embed.set_thumbnail(url=style["icon"])
        
        if image: 
            embed.set_image(url=image)
            
        embed.set_footer(text="via GamerPower API")

        for guild_id, config in guild_configs.items():
            guild = self.bot.get_guild(guild_id)
            if not guild: continue

            channel_id = config.get('notify_channel_id')
            role_id = config.get('mention_role_id')
            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if not channel: continue

            ping = f"<@&{role_id}>" if role_id else None

            try:
                await channel.send(content=ping, embed=embed)
            except discord.Forbidden:
                print(f"❌ Missing permissions in guild {guild_id}")
            except Exception as e:
                print(f"❌ Error sending to {guild_id}: {e}")

    @free_game_loop.before_loop
    async def before_free_game_loop(self):
        await self.bot.wait_until_ready()

    # --- COMMANDS ---

    @app_commands.command(name="free_setup", description="Configure where to post free games.")
    @app_commands.describe(channel="The channel for notifications", role="Optional role to ping")
    @app_commands.checks.has_permissions(administrator=True)
    async def free_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
        role_id = role.id if role else None
        await settings.set(interaction.guild.id, 'free_stuff', 'notify_channel_id', int(channel.id))
        await settings.set(interaction.guild.id, 'free_stuff', 'mention_role_id', int(role_id) if role_id else None)
        
        msg = f"✅ Free games will be posted in {channel.mention}."
        if role:
            msg += f" I will ping {role.mention}."
            
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="free_test", description="Force test the embed for free games (Admin Only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def free_test(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔍 Grabbing a sample game to test the embed... check the channel!", ephemeral=True)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(GP_API) as resp:
                    if resp.status != 200:
                        print("Test API Error")
                        return
                    data = await resp.json()
            except Exception as e:
                print(f"Test Fetch Error: {e}")
                return

        if not data:
            return
            
        item = data[0]
        title = item.get("title")
        url = item.get("open_giveaway_url")
        image = item.get("image")
        platform = item.get("platforms")
        end_date = item.get("end_date")
        worth = item.get("worth", "N/A")

        await self.broadcast_game(f"[TEST] {title}", url, image, platform, end_date, worth)

    # --- MANUAL QUEST ANNOUNCER ---
    
    @app_commands.command(name="quest_alert", description="Manually announce a Discord Quest/Orb.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        game_name="Name of the game (e.g. 'Genshin Impact')",
        reward="What do they get? (e.g. 'Wing Glider Skin')",
        instructions="How to do it? (e.g. 'Stream for 15 mins')",
        image_url="Link to an image of the reward"
    )
    async def quest_alert(self, interaction: discord.Interaction, game_name: str, reward: str, instructions: str, image_url: str = None):
        channel_id = await settings.get(interaction.guild.id, 'free_stuff', 'notify_channel_id', default=None)
        role_id = await settings.get(interaction.guild.id, 'free_stuff', 'mention_role_id', default=None)
        
        if not channel_id:
            return await interaction.response.send_message("❌ Setup not found! Use `/free_setup` first.", ephemeral=True)
            
        channel_id = int(channel_id)
        channel = interaction.guild.get_channel(channel_id)
        role_id = int(role_id) if role_id else None
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel:
            return await interaction.response.send_message("❌ Configured channel no longer exists.", ephemeral=True)

        embed = discord.Embed(
            title=f"💎 New Discord Quest: {game_name}",
            description=f"**Reward:** {reward}\n\n**How to claim:**\n{instructions}",
            color=0x2B2D31 
        )
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(text="Check User Settings > Gift Inventory to claim!")

        # Create the ping string, or None if no role is set
        ping = f"<@&{role_id}>" if role_id else None
        
        await channel.send(content=ping, embed=embed)
        await interaction.response.send_message("✅ Quest announced!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(FreeStuff(bot))