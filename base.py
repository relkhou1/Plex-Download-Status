import discord
import os
from dotenv import load_dotenv
import requests
from discord.ext import commands
import random
import re
import asyncio

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")


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
transfer_url = "http://janet:8182/api/transfers"
download_url = "http://janet:8182/api/downloads"

def call_api(url):
	# Define the endpoint URL
	try:
		# Send the GET request
		response = requests.get(url)
		
		# Check if the request was successful (Status Code 200)
		if response.status_code == 200:
			# Parse JSON data if the endpoint returns JSON
			data = response.json()
			print("Success!", data)
			return data

		else:
			print(f"Failed with status code: {response.status_code}")
			
	except requests.exceptions.RequestException as e:
		print(f"An error occurred: {e}")

def is_data(data):
	return data['data']

@bot.event
async def on_ready():
    # Tell the type checker that User is filled up at this point
    assert bot.user is not None

    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

REFRESH_INTERVAL_SECONDS = 10

# "2,024.00 KB/s from 4 peers, 263.1 MB of 4.9 GB, 39 mins left"
MESSAGE_PATTERN = re.compile(
	r"^(?P<speed>[\d.,]+\s*[A-Za-z]+/s) from (?P<peers>\d+) peers?, "
	r"(?P<downloaded>[\d.]+\s*[A-Za-z]+) of (?P<total>[\d.]+\s*[A-Za-z]+), "
	r"(?P<time_left>.+)$"
)

def parse_message(status, message):
	if status == "finished" or not message:
		return {"state": "finished"}
	if message.strip() == "Loading...":
		return {"state": "starting"}

	match = MESSAGE_PATTERN.match(message)
	if not match:
		return {"state": "unknown", "raw": message}

	fields = match.groupdict()
	fields["state"] = "downloading"
	fields["percent"] = size_to_bytes(fields["downloaded"]) / size_to_bytes(fields["total"])
	return fields

SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}

def size_to_bytes(size_str):
	value, unit = size_str.split()
	return float(value) * SIZE_UNITS[unit.upper()]

def progress_bar(percent, length=20):
	percent = max(0.0, min(1.0, percent))
	filled = round(length * percent)
	bar = "█" * filled + "░" * (length - filled)
	return f"`{bar}` {percent * 100:.1f}%"

async def display_transfers(embeds, ctx):
	return await ctx.send(embeds=embeds)

def embed(name, status, message):
    e = discord.Embed(title=f"{name}", color=0x98FFE4 if status == "finished" else 0xF7F4A6)
    e.add_field(name="Status", value=status, inline=True)

    parsed = parse_message(status, message)
    if parsed["state"] == "starting":
        e.add_field(name="Network", value="Connecting...", inline=True)
    elif parsed["state"] == "downloading":
        e.add_field(name="Network", value=f"{parsed['peers']} peers", inline=True)
        e.add_field(name="Peak", value=parsed['speed'], inline=True)
        e.add_field(name="Time Left", value=parsed['time_left'], inline=True)
        e.add_field(
            name="Progress",
            value=f"{progress_bar(parsed['percent'])}\n{parsed['downloaded']} of {parsed['total']}",
            inline=False,
        )
    elif parsed["state"] == "unknown":
        e.set_footer(text=parsed["raw"])

    return e

def build_embeds(transfers_data):
	return [embed(t['name'], t['status'], t['message']) for t in transfers_data]

async def handle_transfers(transfers, ctx, fetch=None):
	data = is_data(transfers)
	if not data:
		return

	sent = await display_transfers(build_embeds(data), ctx)

	if fetch is None:
		return

	while any(t['status'] != "finished" for t in data):
		await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
		transfers = fetch()
		data = is_data(transfers)
		if not data:
			break
		await sent.edit(embeds=build_embeds(data))

def speed_cleaned(speed, total_size):
	pass


def calculate_estimated_finish(size_completed, unit):
	return	

def calculate_total_size(size_completed, percentage_completed, unit):

	return size_completed / percentage_completed
#	return str(size_completed / percentage_completed) + " " + unit
	

# "progress":"83% Complete (1.7 GB)"
def progress_cleaned(progress):
	fields = progress.split()

	percentage_completed = float(progress[0].strip('%')) / 100
	size_temp = (fields[-1].strip('()')).split()

	size_completed = float(size_temp[0])
	unit = size_temp[1]

	return calculate_total_size(size_completed, percentage_completed)

	

async def handle_downloads(downloads, ctx):
	if not is_data(downloads):
		return

	embeds = []
	for d in downloads:
		name = d['name']
		progress = d['progress']
		speed = d['speed']
		total_size = progress_cleaned(progress) 
		estimated_finish_time = speed_cleaned(speed, total_size)
		embeds.append(embed(name, progress, speed))
	
	await display_transfers(embeds, ctx)

	return downloads

def format_size(num_bytes):
	if num_bytes >= SIZE_UNITS["GB"]:
		return f"{num_bytes / SIZE_UNITS['GB']:.1f} GB"
	return f"{num_bytes / SIZE_UNITS['MB']:.1f} MB"

# Two synthetic in-progress downloads, each with its own size/speed, so
# repeated get_transfers() calls show their progress bars climbing to 100%.
SIM_JOBS = [
	{
		"id": "w0yHQIzBFu_dFw1yjo1kbQ",
		"name": "Monsoon Wedding (2001) Criterion (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole) [QxR]",
		"total_bytes": 7.3 * SIZE_UNITS["GB"],
		"downloaded_bytes": 0,
		"speed_kbps": (2800, 3600),
		"peers": (3, 6),
	},
	{
		"id": "HxRjjVcpqe2Bx-Abq8OqHw",
		"name": "Lolita.(1962).ITA-ENG.Ac3.2.0.multisub.BDRip.1080p.X264-BaMax71-iDN_CreW",
		"total_bytes": 4.9 * SIZE_UNITS["GB"],
		"downloaded_bytes": 263.1 * SIZE_UNITS["MB"],
		"speed_kbps": (1800, 2200),
		"peers": (2, 5),
	},
]

def get_transfers():
	# TODO: swap for call_api(transfer_url) once the API is reachable for testing
	jobs = [{
		"id": "jf0a3CaGkY2vNLqo3C12wQ",
		"name": "Monsoon Wedding 2001 Criterion 1080p BluRay HEVC x265 5.1 BONE.mkv",
		"message": "",
		"status": "finished",
		"progress": 0,
		"src": "https://www.premiumize.me/api/job/src?id=jf0a3CaGkY2vNLqo3C12wQ",
		"folder_id": "",
		"file_id": "2O4R9DVP6LYTiPmQkl6Efg",
	}]

	for job in SIM_JOBS:
		if job["downloaded_bytes"] <= 0:
			# First poll after the job appears: still connecting to peers.
			job["downloaded_bytes"] = 1
			message = "Loading..."
		elif job["downloaded_bytes"] >= job["total_bytes"]:
			message = ""
		else:
			speed_kbps = random.uniform(*job["speed_kbps"])
			job["downloaded_bytes"] = min(
				job["total_bytes"],
				job["downloaded_bytes"] + speed_kbps * 1024 * REFRESH_INTERVAL_SECONDS,
			)
			remaining_bytes = job["total_bytes"] - job["downloaded_bytes"]
			minutes_left = max(1, round(remaining_bytes / (speed_kbps * 1024) / 60))
			peers = random.randint(*job["peers"])
			message = (
				f"{speed_kbps:,.2f} KB/s from {peers} peers, "
				f"{format_size(job['downloaded_bytes'])} of {format_size(job['total_bytes'])}, "
				f"{minutes_left} mins left"
			)

		finished = job["downloaded_bytes"] >= job["total_bytes"]
		jobs.append({
			"id": job["id"],
			"name": job["name"],
			"message": message,
			"status": "finished" if finished else "running",
			# The real API reports 0 once a job is finished, matching the sample payload.
			"progress": 0 if finished else job["downloaded_bytes"] / job["total_bytes"],
			"src": f"https://www.premiumize.me/api/job/src?id={job['id']}",
			"folder_id": "",
			"file_id": "",
		})

	return {"data": jobs, "status": ""}

@bot.command()
async def status(ctx):
    # Call the sonarr api
    # If downloading, return the percentage and what it's downloading
    ### if "totalRecords" > 0, then return how long it'll take to download everyhting
#	downloads = call_api(download_url)

	await handle_transfers(get_transfers(), ctx, fetch=get_transfers)
#	handle_downloads(downloads, ctx)


    # Call the radarr api
    # If downloading, return the percentage and what it's downloading

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