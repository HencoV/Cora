import discord
from discord.ext import commands, tasks
from itertools import cycle

class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # List of statuses to cycle through
        self.status_messages = cycle([
            "Bitches, hoes and money",
            "Rawr xD",
            "Fuck FlaviBot 🖕",
            "Jk do it fatty",
            "Stop looking at my status I'm shy .,.",
            "FlaviBot is run by a terrorist organization",
        ])
        
    # This event runs when the Cog is loaded
    @commands.Cog.listener()
    async def on_ready(self):
        # Start the loop if you want rotating statuses
        if not self.status_loop.is_running():
            self.status_loop.start()
        print("✅ Status Cog loaded and loop started.")

    # --- AUTOMATIC STATUS ROTATION ---
    # Changes status every 10 minutes
    @tasks.loop(minutes=10)
    async def status_loop(self):
        current_status = next(self.status_messages)
        # You can change ActivityType to watching/listening/etc. here if you want
        await self.bot.change_presence(activity=discord.Game(name=current_status))

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_ready()

    # --- MANUAL COMMANDS ---
    
    @commands.command(name="setstatus")
    @commands.is_owner()
    async def set_status(self, ctx, type: str, *, text: str):
        """
        Usage: !setstatus <play/watch/listen> <text>
        Example: !setstatus watch The Matrix
        """
        # Stop the loop so it doesn't overwrite your manual setting
        if self.status_loop.is_running():
            self.status_loop.cancel()

        try:
            if type.lower() == "play":
                activity = discord.Game(name=text)
            elif type.lower() == "watch":
                activity = discord.Activity(type=discord.ActivityType.watching, name=text)
            elif type.lower() == "listen":
                activity = discord.Activity(type=discord.ActivityType.listening, name=text)
            elif type.lower() == "compete":
                activity = discord.Activity(type=discord.ActivityType.competing, name=text)
            else:
                return await ctx.send("❌ Invalid type. Use: play, watch, listen, or compete.")

            await self.bot.change_presence(activity=activity)
            await ctx.send(f"✅ Status changed to: **{type.capitalize()}ing {text}**")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="resetstatus")
    @commands.is_owner()
    async def reset_status(self, ctx):
        """Restarts the automatic rotation loop"""
        if not self.status_loop.is_running():
            self.status_loop.start()
            await ctx.send("✅ **Status rotation restarted!**")
        else:
            await ctx.send("⚠️ Rotation is already running.")

async def setup(bot):
    await bot.add_cog(Status(bot))