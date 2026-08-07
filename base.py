import discord
import os
from dotenv import load_dotenv
import aiohttp
from discord import app_commands
from discord.ext import commands, tasks
import re
import asyncio

import arr

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
try:
	STATUS_CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
except (TypeError, ValueError):
	STATUS_CHANNEL_ID = None


description = """An example bot to showcase the discord.ext.commands extension
module.

There are a number of utility commands being showcased here."""


"""
1. Use one function to query both sonarr and radarr api keys
2. When user types !status, bot calls both applications and checks if either is downloading
--> 1. if one of them is downloading, return the percentage and any related information

3. Write a function to check for most recently downloaded stuff
4. Write function to check if something exists in the plex library
5. Request list (Takes care of Raj asking us to download something)

"""


"""
Use percentage to calculate the total size and estimate how long it'll get done

"""


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='./', description=description, intents=intents)
download_url = "http://localhost:8182/api/downloads"

async def fetch_downloads(session):
	try:
		async with session.get(download_url, timeout=aiohttp.ClientTimeout(total=10)) as r:
			if r.status != 200:
				print(f"Download fetch failed: HTTP {r.status}")
				return []
			data = await r.json(content_type=None)
			return data.get("data") or []
	except (aiohttp.ClientError, TimeoutError) as e:
		print(f"Download fetch failed: {e}")
		return []

@bot.event
async def on_ready():
    # Tell the type checker that User is filled up at this point
    assert bot.user is not None

    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    await bot.tree.sync()

    if STATUS_CHANNEL_ID:
        if not poll_downloads.is_running():
            poll_downloads.start()
    else:
        print('CHANNEL_ID not set — automatic download status updates disabled.')

REFRESH_INTERVAL_SECONDS = 2

SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}

def progress_bar(percent, length=20):
	percent = max(0.0, min(1.0, percent))
	filled = round(length * percent)
	bar = "█" * filled + "░" * (length - filled)
	return f"`{bar}` {percent * 100:.1f}%"

async def display_transfers(embeds, ctx):
	return await ctx.send(embeds=embeds)

# "83% Complete (1.7 GB)"
PROGRESS_PATTERN = re.compile(r"^(?P<percent>[\d.]+)%\s*Complete\s*\((?P<size>[\d.]+)\s*(?P<unit>[A-Za-z]+)\)$")
# "12.2MB / Second"
SPEED_PATTERN = re.compile(r"^(?P<value>[\d.,]+)(?P<unit>[A-Za-z]+)\s*/\s*Second[s]?$", re.IGNORECASE)

def format_eta(seconds):
	if seconds is None:
		return "—"
	minutes = seconds / 60
	if minutes < 1:
		return "<1 min left"
	hours, minutes = divmod(round(minutes), 60)
	if hours:
		return f"{hours}h {minutes}m left"
	return f"{minutes} mins left"

def parse_download(d):
	progress = (d.get("progress") or "").strip()
	speed = (d.get("speed") or "").strip()

	match = PROGRESS_PATTERN.match(progress)
	if not match:
		return {"state": "unknown", "raw": progress or "No progress info"}

	percent = float(match.group("percent")) / 100
	size_completed = float(match.group("size")) * SIZE_UNITS[match.group("unit").upper()]

	if percent >= 1.0:
		return {"state": "finished"}
	if percent <= 0:
		return {"state": "starting"}

	# total size = amount downloaded / (percent complete / 100)
	total_size = size_completed / percent
	# what's left = total size - amount downloaded
	remaining = max(0.0, total_size - size_completed)

	speed_match = SPEED_PATTERN.match(speed)
	speed_bytes = None
	if speed_match:
		speed_bytes = float(speed_match.group("value").replace(",", "")) * SIZE_UNITS[speed_match.group("unit").upper()]

	# estimated finish time = space left / download speed
	eta_seconds = remaining / speed_bytes if speed_bytes else None

	return {
		"state": "downloading",
		"percent": percent,
		"size_completed": size_completed,
		"total_size": total_size,
		"speed_text": speed if speed_match else None,
		"eta_seconds": eta_seconds,
	}

# Strip file extensions and quality/codec tags so a raw torrent/nzb name
# matches Radarr/Sonarr's lookup search reasonably well.
FILE_EXT_PATTERN = re.compile(r"\.(mkv|mp4|avi|nfo|nzb|torrent)$", re.IGNORECASE)
QUALITY_TAG_PATTERN = re.compile(
	r"[.\s](2160p|1080p|1080i|720p|480p|BluRay|BDRip|BRRip|WEB[-.]?DL|WEBRip|HDTV|"
	r"x264|x265|HEVC|H\.?264|H\.?265|AVC|AAC|DTS|AC3|FLAC|Atmos|TrueHD|HDR|SDR|"
	r"REMUX|AMZN|NF|DSNP|HMAX|PROPER|REPACK|EXTENDED).*",
	re.IGNORECASE,
)

def clean_download_name(name):
	name = FILE_EXT_PATTERN.sub("", name)
	name = QUALITY_TAG_PATTERN.sub("", name)
	return name.replace(".", " ").strip()

_download_poster_cache = {}

async def find_download_poster(session, name):
	clean = clean_download_name(name)
	if not clean:
		return None
	if clean in _download_poster_cache:
		return _download_poster_cache[clean]

	poster = None
	movies = await arr.lookup_movie(session, clean)
	if movies:
		poster = arr.poster_url(movies[0])
	if not poster:
		shows = await arr.lookup_series(session, clean)
		if shows:
			poster = arr.poster_url(shows[0])

	_download_poster_cache[clean] = poster
	return poster

async def download_embed(session, d):
	name = d.get("name", "Unknown")
	parsed = parse_download(d)
	finished = parsed["state"] == "finished"

	e = discord.Embed(title=f"{name}", color=0x98FFE4 if finished else 0xF7F4A6)
	e.add_field(name="Status", value="finished" if finished else parsed["state"], inline=True)

	if parsed["state"] == "downloading":
		if parsed["speed_text"]:
			e.add_field(name="Speed", value=parsed["speed_text"], inline=True)
		e.add_field(name="Time Left", value=format_eta(parsed["eta_seconds"]), inline=True)
		e.add_field(
			name="Progress",
			value=f"{progress_bar(parsed['percent'])}\n{format_size(parsed['size_completed'])} of {format_size(parsed['total_size'])}",
			inline=False,
		)
	elif parsed["state"] == "unknown":
		e.set_footer(text=parsed["raw"])

	poster = await find_download_poster(session, name)
	if poster:
		e.set_thumbnail(url=poster)

	return e

async def build_download_embeds(session, downloads_data):
	downloading = [d for d in downloads_data if parse_download(d)["state"] == "downloading"]
	return [await download_embed(session, d) for d in downloading]

def downloads_active(downloads_data):
	return any(parse_download(d)["state"] != "finished" for d in downloads_data)

async def run_status(ctx, session):
	downloads_data = await fetch_downloads(session)
	embeds = await build_download_embeds(session, downloads_data)
	if not embeds:
		await ctx.send("There is nothing in queue")
		return

	sent = await display_transfers(embeds, ctx)

	while downloads_active(downloads_data):
		await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
		downloads_data = await fetch_downloads(session)
		embeds = await build_download_embeds(session, downloads_data)
		if not embeds:
			break
		await sent.edit(embeds=embeds)

auto_status_message = None

@tasks.loop(seconds=REFRESH_INTERVAL_SECONDS)
async def poll_downloads():
	global auto_status_message

	channel = bot.get_channel(STATUS_CHANNEL_ID)
	if channel is None:
		return

	async with aiohttp.ClientSession() as session:
		downloads_data = await fetch_downloads(session)
		embeds = await build_download_embeds(session, downloads_data)

	if not embeds:
		if auto_status_message:
			try:
				await auto_status_message.delete()
			except discord.NotFound:
				pass
			auto_status_message = None
		return

	if auto_status_message:
		try:
			await auto_status_message.edit(embeds=embeds)
			return
		except discord.NotFound:
			auto_status_message = None

	auto_status_message = await channel.send(embeds=embeds)

@poll_downloads.before_loop
async def before_poll_downloads():
	await bot.wait_until_ready()

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
CANCEL_EMOJI = "❌"

def candidate_embed(item, is_movie, index):
	icon = "🎬" if is_movie else "📺"
	year = item.get("year", "")
	title = item.get("title", "Unknown")
	label = f"{title} ({year})" if year else title

	e = discord.Embed(
		title=f"{NUMBER_EMOJIS[index]} {icon} {label}",
		description=(item.get("overview") or "")[:200],
		color=0x3498db,
	)
	poster = arr.poster_url(item)
	if poster:
		e.set_thumbnail(url=poster)
	return e

async def pick_candidate(interaction, candidates):
	embeds = [candidate_embed(item, is_movie, i) for i, (item, is_movie) in enumerate(candidates)]
	message = await interaction.followup.send(content="Which one did you mean? React ❌ to cancel.", embeds=embeds)

	for i in range(len(candidates)):
		await message.add_reaction(NUMBER_EMOJIS[i])
	await message.add_reaction(CANCEL_EMOJI)

	valid_emojis = NUMBER_EMOJIS[:len(candidates)] + [CANCEL_EMOJI]

	def check(reaction, user):
		return (
			user.id == interaction.user.id
			and reaction.message.id == message.id
			and str(reaction.emoji) in valid_emojis
		)

	try:
		reaction, _ = await bot.wait_for("reaction_add", timeout=60, check=check)
	except asyncio.TimeoutError:
		return "timeout"

	if str(reaction.emoji) == CANCEL_EMOJI:
		return "cancelled"

	return candidates[NUMBER_EMOJIS.index(str(reaction.emoji))]

MAX_RELEASE_BYTES = 30 * SIZE_UNITS["GB"]
RELEASES_PER_PAGE = 4

def release_line(release, index):
	title = release.get("title", "Unknown")[:250]
	size = format_size(release.get("size") or 0)
	quality = ((release.get("quality") or {}).get("quality") or {}).get("name", "")
	seeders = release.get("seeders")
	indexer = release.get("indexer", "")

	stats = f"{quality}  •  {size}"
	if seeders is not None:
		stats += f"  •  {seeders} seeders"

	return f"**{index + 1}. {title}**\n{stats}  •  {indexer}"

class ReleaseVote(discord.ui.View):
	def __init__(self, releases, item_title, vote_seconds, requester_id):
		super().__init__(timeout=vote_seconds)
		self.releases = releases
		self.item_title = item_title
		self.vote_seconds = vote_seconds
		self.requester_id = requester_id
		self.votes = {}
		self.message = None
		self.cancelled = False
		self.page = 0
		self.total_pages = -(-len(releases) // RELEASES_PER_PAGE)

		self.select = discord.ui.Select(row=0)
		self.select.callback = self._on_select
		self.add_item(self.select)

		self.prev_button = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=1)
		self.prev_button.callback = self._on_prev
		self.add_item(self.prev_button)

		self.next_button = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
		self.next_button.callback = self._on_next
		self.add_item(self.next_button)

		self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
		self.cancel_button.callback = self._on_cancel
		self.add_item(self.cancel_button)

		self._refresh()

	def _page_slice(self):
		start = self.page * RELEASES_PER_PAGE
		return list(enumerate(self.releases))[start:start + RELEASES_PER_PAGE]

	def _refresh(self):
		self.select.options = [
			discord.SelectOption(
				label=f"{index + 1}. {r.get('title', 'Unknown')}"[:100],
				description=f"{((r.get('quality') or {}).get('quality') or {}).get('name', '')}  •  {format_size(r.get('size') or 0)}"[:100],
				value=str(index),
			)
			for index, r in self._page_slice()
		]
		self.select.placeholder = "Choose a release to vote for…"
		self.prev_button.disabled = self.page <= 0
		self.next_button.disabled = self.page >= self.total_pages - 1

	def render_embed(self):
		description = "\n\n".join(release_line(r, i) for i, r in self._page_slice())
		e = discord.Embed(
			title=f"Vote for a release — {self.item_title}",
			description=description,
			color=0xF7F4A6,
		)
		footer = f"Voting closes in {self.vote_seconds}s"
		if self.total_pages > 1:
			footer = f"Page {self.page + 1}/{self.total_pages} • {footer}"
		e.set_footer(text=footer)
		return e

	async def _on_select(self, interaction: discord.Interaction):
		index = int(interaction.data["values"][0])
		self.votes[interaction.user.id] = index
		title = self.releases[index].get("title", "Unknown")[:200]
		await interaction.response.send_message(f"Vote recorded: **{title}**", ephemeral=True)

	async def _on_prev(self, interaction: discord.Interaction):
		self.page = max(0, self.page - 1)
		self._refresh()
		await interaction.response.edit_message(embed=self.render_embed(), view=self)

	async def _on_next(self, interaction: discord.Interaction):
		self.page = min(self.total_pages - 1, self.page + 1)
		self._refresh()
		await interaction.response.edit_message(embed=self.render_embed(), view=self)

	async def _on_cancel(self, interaction: discord.Interaction):
		if interaction.user.id != self.requester_id:
			await interaction.response.send_message("Only the requester can cancel this.", ephemeral=True)
			return
		self.cancelled = True
		for child in self.children:
			child.disabled = True
		await interaction.response.edit_message(view=self)
		self.stop()

	async def on_timeout(self):
		for child in self.children:
			child.disabled = True
		if self.message:
			await self.message.edit(view=self)

	def winner(self):
		if self.cancelled or not self.votes:
			return None
		tally = {}
		for index in self.votes.values():
			tally[index] = tally.get(index, 0) + 1
		best_index = max(tally, key=tally.get)
		return self.releases[best_index]

async def vote_release(interaction, item, releases, vote_seconds=60):
	releases = [
		r for r in releases
		if (r.get("size") or 0) <= MAX_RELEASE_BYTES
		and r.get("seeders") != 0
	]
	if not releases:
		return "none"

	view = ReleaseVote(releases, item.get("title", "Unknown"), vote_seconds, interaction.user.id)
	view.message = await interaction.followup.send(embed=view.render_embed(), view=view)

	await view.wait()
	if view.cancelled:
		return "cancelled"
	return view.winner()

@bot.tree.command(name="request", description="Search Radarr/Sonarr and request a download")
@app_commands.describe(title="Movie or show title to search for", season="Season number (TV shows only)")
async def request(interaction: discord.Interaction, title: str, season: int = 1):
	await interaction.response.defer()

	async with aiohttp.ClientSession() as session:
		movies = await arr.lookup_movie(session, title)
		shows = await arr.lookup_series(session, title)
		candidates = [(m, True) for m in movies[:4]] + [(s, False) for s in shows[:4]]

		if not candidates:
			await interaction.followup.send(f"No matches found for **{title}**.")
			return

		picked = await pick_candidate(interaction, candidates)
		if picked == "cancelled":
			await interaction.followup.send("Request cancelled.")
			return
		if picked == "timeout":
			await interaction.followup.send("No selection made — request timed out.")
			return
		item, is_movie = picked
		searching = await interaction.followup.send(
			f"🔎 Searching indexers for **{item.get('title')}**… this can take up to a minute."
		)

		if is_movie:
			media_id = item.get("id") or 0
			if not media_id:
				added = await arr.add_movie(session, item)
				if not added:
					await searching.edit(content=f"Failed to add **{item.get('title')}** to Radarr.")
					return
				media_id = added["id"]
			releases = await arr.interactive_search_movie(session, media_id)
		else:
			media_id = item.get("id") or 0
			if not media_id:
				added = await arr.add_series(session, item)
				if not added:
					await searching.edit(content=f"Failed to add **{item.get('title')}** to Sonarr.")
					return
				media_id = added["id"]
			releases = await arr.interactive_search_season(session, media_id, season)

		await searching.delete()

		if not releases:
			await interaction.followup.send(f"No releases found for **{item.get('title')}**.")
			return

		winner = await vote_release(interaction, item, releases)
		if winner == "cancelled":
			await interaction.followup.send("Request cancelled.")
			return
		if winner == "none":
			await interaction.followup.send(f"All releases for **{item.get('title')}** were over 30 GB — nothing to vote on.")
			return
		if winner is None:
			await interaction.followup.send("No votes received — nothing was grabbed.")
			return

		result = await arr.grab_release(session, is_movie, winner)
		if result is not None:
			await interaction.followup.send(f"✅ Grabbed **{winner.get('title')}**")
		else:
			await interaction.followup.send(f"❌ Failed to grab **{winner.get('title')}**")

def format_size(num_bytes):
	if num_bytes >= SIZE_UNITS["GB"]:
		return f"{num_bytes / SIZE_UNITS['GB']:.1f} GB"
	return f"{num_bytes / SIZE_UNITS['MB']:.1f} MB"

@bot.command()
async def status(ctx):
	async with aiohttp.ClientSession() as session:
		await run_status(ctx, session)

@bot.group()
async def cool(ctx):
    """Says if a user is cool.

    In reality this just checks if a subcommand is being invoked.
    """
    if ctx.invoked_subcommand is None:
        await ctx.send(f'No, {ctx.subcommand_passed} is not cool')


@cool.command(name='bot')
async def _bot(ctx):
    """Is the bot cool?"""
    await ctx.send('Yes, the bot is cool.')

# intents = discord.Intents.default()
# intents.message_content = True

# client = MyClient(intents=intents)
bot.run(TOKEN)