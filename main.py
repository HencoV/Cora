import discord
from discord.ext import commands
import os
import asyncio
import traceback 
from dotenv import load_dotenv

load_dotenv()

class cora(commands.Bot):
    def __init__(self):
        # --- INTENTS ---
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.members = True        # Needed to see member lists
        intents.voice_states = True   # Needed to see Voice Channels
        
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("--- STARTING COG LOADER ---")
        cogs_dir = './cogs'
        
        if not os.path.exists(cogs_dir):
            print("⚠️ 'cogs' folder not found. No extensions loaded.")
            return

        for item in os.listdir(cogs_dir):
            item_path = os.path.join(cogs_dir, item)
            
            # 1. Load flat files (e.g., cogs/status.py)
            if os.path.isfile(item_path) and item.endswith('.py') and item not in ('settings_helper.py',):
                ext = f'cogs.{item[:-3]}'
                try:
                    await self.load_extension(ext)
                    print(f"✅ Loaded flat cog: {ext}")
                except Exception as e:
                    print(f"❌ Failed to load {ext}")
                    traceback.print_exc()
                    
            # 2. Load subfolders (e.g., cogs/music/music.py)
            elif os.path.isdir(item_path):
                folder_name = item
                found_main_file = False
                
                # Look at every file inside the folder
                for sub_item in os.listdir(item_path):
                    # Check if the file name matches the folder name (ignoring capitals)
                    if sub_item.lower() == f"{folder_name.lower()}.py":
                        found_main_file = True
                        ext = f'cogs.{folder_name}.{sub_item[:-3]}'
                        try:
                            await self.load_extension(ext)
                            print(f"✅ Loaded folder cog: {ext}")
                        except Exception as e:
                            print(f"❌ Failed to load {ext}")
                            traceback.print_exc()
                
                # If it looked through the folder and didn't find a matching file
                if not found_main_file:
                    print(f"⏩ Skipped folder '{folder_name}/' (Could not find a main '{folder_name}.py' file inside)")
                    
        print("--- COG LOADER FINISHED ---")

bot = cora()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    # Status is now handled by cogs/status.py, so we removed the change_presence here

# --- IMPROVED SYNC COMMAND ---
@bot.command(name="sync")
@commands.is_owner()
async def sync(ctx, spec: str = None):
    """
    !sync -> Syncs globally (takes up to 1h to update everywhere)
    !sync . -> Syncs to CURRENT server only (Instant)
    !sync ^ -> Clears local guild commands (Fixes doubles)
    """
    msg = await ctx.send(f"🔄 Syncing... (Spec: {spec})")
    
    try:
        if spec == ".":
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            await msg.edit(content=f"✅ **Synced {len(synced)} commands to this guild!**")
        
        elif spec == "^":
            bot.tree.clear_commands(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
            await msg.edit(content="🧹 **Local guild commands cleared!**")
            
        else:
            synced = await bot.tree.sync()
            await msg.edit(content=f"🌍 **Globally Synced {len(synced)} commands!**")

    except Exception as e:
        await msg.edit(content=f"❌ Sync failed: {e}")
        traceback.print_exc()

bot.run(os.environ["DISCORD_TOKEN"])