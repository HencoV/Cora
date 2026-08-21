import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import aiohttp
import datetime
import os
import re
from dotenv import load_dotenv
from cogs.settings_helper import settings

load_dotenv()

class MovieRateModal(discord.ui.Modal):
    def __init__(self, cog, movie_id, title):
        super().__init__(title=f"Rate: {title[:35]}...")
        self.cog = cog
        self.movie_id = movie_id
        self.title = title
        
        self.score = discord.ui.TextInput(
            label="Score (0-10)", 
            placeholder="e.g. 8.5", 
            min_length=1, 
            max_length=4
        )
        self.review = discord.ui.TextInput(
            label="Review (Optional)", 
            style=discord.TextStyle.paragraph, 
            required=False, 
            max_length=200,
            placeholder="What did you think?"
        )
        self.add_item(self.score)
        self.add_item(self.review)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.score.value)
            if val < 0 or val > 10:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Score must be a number between 0 and 10.", ephemeral=True)

        # 1. Save to DB
        self.cog.cursor.execute("""
            INSERT OR REPLACE INTO movie_reviews (movie_id, user_id, user_name, score, comment)
            VALUES (?, ?, ?, ?, ?)
        """, (self.movie_id, interaction.user.id, interaction.user.display_name, val, self.review.value))
        self.cog.conn.commit()

        # 2. Fetch all voters to update the live panel
        self.cog.cursor.execute("SELECT user_name FROM movie_reviews WHERE movie_id = ?", (self.movie_id,))
        voters = [row[0] for row in self.cog.cursor.fetchall()]
        
        # 3. Rebuild the description of the voting panel
        original_embed = interaction.message.embeds[0]
        voter_list = "\n".join([f"✅ {name}" for name in voters])
        
        original_embed.description = (
            f"**Now Rating:** {self.title}\n\n"
            f"**Voters so far ({len(voters)}):**\n"
            f"{voter_list}\n\n"
            "Click below to cast your vote!"
        )
        
        # Edit the message with the new embed list, then confirm to the user
        await interaction.message.edit(embed=original_embed)
        await interaction.response.send_message(f"✅ Voted **{val}/10** for *{self.title}*!", ephemeral=True)

class MovieVoteView(discord.ui.View):
    def __init__(self, cog, movie_id, title, poster_url):
        super().__init__(timeout=None)
        self.cog = cog
        self.movie_id = movie_id
        self.title = title
        self.poster_url = poster_url

    @discord.ui.button(label="⭐ Rate Movie", style=discord.ButtonStyle.success, custom_id="rate_movie_btn")
    async def rate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MovieRateModal(self.cog, self.movie_id, self.title))

    @discord.ui.button(label="🏁 Finish & Pin", style=discord.ButtonStyle.danger, custom_id="finish_movie_btn")
    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # 1. Fetch All Reviews
        self.cog.cursor.execute("SELECT score, comment, user_name FROM movie_reviews WHERE movie_id = ?", (self.movie_id,))
        reviews = self.cog.cursor.fetchall() 

        if not reviews:
            return await interaction.followup.send("❌ No votes recorded! Cannot finish.")

        scores = [r[0] for r in reviews]
        avg_score = sum(scores) / len(scores)
        count = len(scores)

        # 2. Get History Channel
        history_channel_id = await settings.get(interaction.guild.id, 'ratings', 'history_channel_id', default=None)
        hist_channel = interaction.guild.get_channel(int(history_channel_id)) if history_channel_id else None

        if not hist_channel:
            return await interaction.followup.send("⚠️ **No History Channel Set!** Use `/movie_setup` first.")

        # 3. Build The Official Card (Now with ALL reviews)
        embed = discord.Embed(title=f"🎬 {self.title}", color=discord.Color.gold())
        if self.poster_url: embed.set_thumbnail(url=self.poster_url)
        embed.add_field(name="Final Rating", value=f"⭐ **{avg_score:.1f} / 10**", inline=True)
        embed.add_field(name="Total Votes", value=f"👤 {count}", inline=True)
        
        # Add everyone's review as a separate field
        for score, comment, name in reviews:
            review_text = f"💬 \"{comment}\"" if comment and comment.strip() else "*No written review.*"
            embed.add_field(name=f"{name} (⭐ {score}/10)", value=review_text, inline=False)
        
        embed.set_footer(text=f"Watched on {datetime.date.today()}")

        # 4. Post & Pin
        try:
            msg = await hist_channel.send(embed=embed)
            await msg.pin()
        except Exception as e:
            print(f"Pin Error: {e}")

        # 5. Update Database
        self.cog.cursor.execute("UPDATE movies SET final_score = ?, is_active = 0 WHERE id = ?", (avg_score, self.movie_id))
        self.cog.conn.commit()

        # 6. Close Voting Panel
        self.clear_items()
        await interaction.message.edit(content=f"✅ **Voting Closed!**\n📈 Final Score: **{avg_score:.1f}**\n📌 Posted in: {hist_channel.mention}", view=self)

class Movies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Pointing to the new shared stats database!
        self.conn = sqlite3.connect('stats.db')
        self.cursor = self.conn.cursor()
        self.setup_db()

    def setup_db(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                title TEXT,
                poster_url TEXT,
                final_score REAL,
                is_active INTEGER,
                date TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS movie_reviews (
                movie_id INTEGER,
                user_id INTEGER,
                user_name TEXT,
                score REAL,
                comment TEXT,
                PRIMARY KEY (movie_id, user_id)
            )
        """)
        self.conn.commit()

    async def search_tmdb(self, query):
        api_key = os.environ.get("TMDB_API_KEY")
        if not api_key:
            print("❌ TMDB_API_KEY not found in .env")
            return None

        # Check if the user pasted a TMDB link or just an ID number
        movie_id = None
        url_match = re.search(r'themoviedb\.org/movie/(\d+)', query)
        
        if url_match:
            movie_id = url_match.group(1)
        elif query.strip().isdigit():
            movie_id = query.strip()

        async with aiohttp.ClientSession() as session:
            if movie_id:
                # Direct lookup by ID (Bypasses search inaccuracy)
                url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={api_key}"
                async with session.get(url) as resp:
                    if resp.status != 200: return None
                    movie = await resp.json()
            else:
                # Standard Text Search
                url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query}&include_adult=false"
                async with session.get(url) as resp:
                    if resp.status != 200: return None
                    data = await resp.json()
                    if not data.get('results'): return None
                    movie = data['results'][0]
            
            # Format and return the movie data
            return {
                'title': f"{movie.get('title')} ({movie.get('release_date', '????')[:4]})",
                'poster': f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None,
                'overview': movie.get('overview', 'No overview available.'),
                'id': movie.get('id')
            }

    @app_commands.command(name="movie_setup", description="Set the channel where Movie History pins go.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_history(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await settings.set(interaction.guild.id, 'ratings', 'history_channel_id', int(channel.id))
        await interaction.response.send_message(f"✅ Movie History will be pinned in {channel.mention}", ephemeral=True)

    @app_commands.command(name="movie_start", description="Start a voting session for a movie.")
    @app_commands.describe(query="Movie name, TMDB ID, or TMDB Link (e.g. 'Interstellar' or https://...)")
    async def movie_start(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)

        data = await self.search_tmdb(query)
        
        if not data:
            await interaction.followup.send(f"❌ Couldn't find **'{query}'** on TMDB or missing API Key.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Is this the movie?", description=f"**{data['title']}**\n{data['overview'][:100]}...", color=discord.Color.blue())
        if data['poster']: embed.set_image(url=data['poster'])
        
        view = discord.ui.View()
        confirm_btn = discord.ui.Button(label="✅ Yes, Start Voting", style=discord.ButtonStyle.success)
        
        async def confirm_callback(i: discord.Interaction):
            self.cursor.execute("INSERT INTO movies (guild_id, title, poster_url, is_active, date) VALUES (?, ?, ?, 1, ?)", 
                            (i.guild.id, data['title'], data['poster'], datetime.date.today()))
            movie_db_id = self.cursor.lastrowid
            self.conn.commit()

            public_view = MovieVoteView(self, movie_db_id, data['title'], data['poster'])
            
            # Initializing the embed with the 'Voters so far' section
            public_embed = discord.Embed(
                title="🎬 Movie Night Rating", 
                description=f"**Now Rating:** {data['title']}\n\n**Voters so far (0):**\n*Nobody yet!*\n\nClick below to cast your vote!", 
                color=discord.Color.green()
            )
            if data['poster']: public_embed.set_thumbnail(url=data['poster'])
            
            await i.channel.send(embed=public_embed, view=public_view)
            await i.response.send_message("✅ Session Started!", ephemeral=True)

        confirm_btn.callback = confirm_callback
        view.add_item(confirm_btn)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Movies(bot))