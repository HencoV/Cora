import os
import traceback

import discord
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()


# Cogs used by Cora
COGS = [
    "cogs.free_stuff",
    "cogs.ratings",
    "cogs.status",
    "cogs.voice",
    "cogs.voting",
]


class Cora(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()

        # Required for !sync, !setstatus, etc.
        intents.message_content = True

        # Used by voice/member-related features.
        intents.members = True
        intents.voice_states = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self):
        print("----- LOADING COGS -----")

        for extension in COGS:
            try:
                await self.load_extension(extension)
                print(f"✅ Loaded {extension}")
            except Exception:
                print(f"❌ Failed to load {extension}")
                traceback.print_exc()

        print("----- COG LOADING FINISHED -----")


bot = Cora()


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    print(f"✅ Connected to {len(bot.guilds)} server(s)")


@bot.command(name="sync")
@commands.is_owner()
async def sync(ctx, spec: str = None):
    """
    !sync     - Sync commands globally
    !sync .   - Sync commands to the current server immediately
    !sync ^   - Clear current server's local commands
    """

    message = await ctx.send("🔄 Syncing commands...")

    try:
        if spec == ".":
            # Copy global commands into this guild and sync them.
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)

            await message.edit(
                content=f"✅ Synced **{len(synced)}** commands to this server."
            )

        elif spec == "^":
            bot.tree.clear_commands(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)

            await message.edit(
                content="🧹 Cleared this server's local commands."
            )

        else:
            synced = await bot.tree.sync()

            await message.edit(
                content=f"🌍 Globally synced **{len(synced)}** commands."
            )

    except Exception as error:
        await message.edit(
            content=f"❌ Sync failed: `{error}`"
        )
        traceback.print_exc()


token = os.getenv("DISCORD_TOKEN")

if not token:
    raise RuntimeError(
        "DISCORD_TOKEN environment variable is missing."
    )


bot.run(token)