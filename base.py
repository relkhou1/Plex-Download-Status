import discord
import os
from dotenv import load_dotenv
import requests
from discord.ext import commands
import random

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

async def display_transfers(embeds, ctx):
	await ctx.send(embeds=embeds)

def embed(name, status, message, progress):
    title = name
    e = discord.Embed(title=f"{title}", color=0x98FFE4 if status == "finished" else 0xF7F4A6)
    e.add_field(name="Status", value=status, inline=True)
    e.add_field(name="Progress", value=f"{progress}*100:.1f%", inline=True)
    if message:
        e.set_footer(text=message)
    return e

async def handle_transfers(transfers, ctx):
	transfers = is_data(transfers)
	if not transfers:
		return
	# Get name, status, message
	embeds = []
	for t in transfers:
		name = t['name']
		status = t['status']
		message = t['message']
		progress = t['progress']
		embeds.append(embed(name, status, message, progress))
	
	await display_transfers(embeds, ctx)

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

@bot.command()
async def status(ctx):
    # Call the sonarr api
    # If downloading, return the percentage and what it's downloading
    ### if "totalRecords" > 0, then return how long it'll take to download everyhting
#	transfers = call_api(transfer_url)
#	downloads = call_api(download_url)

	transfers = {"data":
			  [
	{"id":"jf0a3CaGkY2vNLqo3C12wQ","name":"Monsoon Wedding 2001 Criterion 1080p BluRay HEVC x265 5.1 BONE.mkv","message":"","status":"finished","progress":0,"src":"https://www.premiumize.me/api/job/src?id=jf0a3CaGkY2vNLqo3C12wQ","folder_id":"","file_id":"2O4R9DVP6LYTiPmQkl6Efg"},
	{"id":"w0yHQIzBFu_dFw1yjo1kbQ","name":"Monsoon Wedding (2001) Criterion (1080p BluRay x265 HEVC 10bit AAC 5.1 Tigole) [QxR]","message":"Loading...","status":"running","progress":0,"src":"https://www.premiumize.me/api/job/src?id=w0yHQIzBFu_dFw1yjo1kbQ","folder_id":"","file_id":""},
	{"id":"HxRjjVcpqe2Bx-Abq8OqHw","name":"Lolita.(1962).ITA-ENG.Ac3.2.0.multisub.BDRip.1080p.X264-BaMax71-iDN_CreW","message":"2,024.00 KB/s from 4 peers, 263.1 MB of 4.9 GB, 39 mins left","status":"running","progress":0.052692342549562454,"src":"https://www.premiumize.me/api/job/src?id=HxRjjVcpqe2Bx-Abq8OqHw","folder_id":"","file_id":""}
	],
	"status":""
	}
	await handle_transfers(transfers, ctx)
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