import os
import os.path
from dotenv import load_dotenv
import discord
from discord import Embed
from discord import app_commands
from discord.ext import commands
import datetime
import requests

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive


load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_TOKEN = os.getenv('API_TOKEN')
BUILD_TOKEN = os.getenv('BUILD_TOKEN')
DEFAULT_BUILD_NAME = os.getenv('DEFAULT_BUILD_NAME')
DEFAULT_BUILD_LOG_FOLDER_ID = os.getenv('DEFAULT_BUILD_LOG_FOLDER_ID')

JENKINS_PATH = "localhost:8080"
BUILD_LOG_PATH = "build_log.txt"
DEFAULT_BUILD_PATH = f"{JENKINS_PATH}/job/{DEFAULT_BUILD_NAME}"
DEFAULT_BUILD_LOG_FOLDER_URL = f"https://drive.google.com/drive/folders/{DEFAULT_BUILD_LOG_FOLDER_ID}"

BLURPLE = 0x5865F2
GREEN = 0x43b581
RED = 0xf04747
GRAY = 0x4f545c

DISCORD_EMBED_LIMIT = 5800 # left 200 for fields that are not changelogs
DISCORD_EMBED_VALUE_LIMIT = 1024 # the maximum length that an embed field can be

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly',
          'https://www.googleapis.com/auth/drive.file']

GAUTH = GoogleAuth()
GAUTH.LoadCredentialsFile("mycreds.txt")
if GAUTH.credentials is None:
    # Authenticate if they're not there
    GAUTH.LocalWebserverAuth()
elif GAUTH.access_token_expired:
    # Refresh them if expired
    GAUTH.Refresh()
else:
    # Initialize the saved creds
    GAUTH.Authorize()
# Save the current credentials to a file
GAUTH.SaveCredentialsFile("mycreds.txt")
DRIVE = GoogleDrive(GAUTH)

BOT = commands.Bot(command_prefix="/", intents=discord.Intents.all())

# class AbortButton(discord.ui.View):
#     def __init__(self):
#         super().__init__(timeout=None)
#     @discord.ui.button(label="ABORT", style=discord.ButtonStyle.red)
#     async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
#         button.disabled = True
#         await interaction.response.edit_message(view=self)
#         try:
#             response = requests.post(f"http://jenkins_as:{API_TOKEN}@saleblazerspc:8080/job/Saleblazers%20Default%20Build/lastBuild/stop")
#             if response.status_code == 200:
#                 await interaction.followup.send("Build aborted successfully.")
#             else:
#                 await interaction.followup.send(f"Failed to abort the build. Error: {response.text}")
#         except Exception as e:
#             await interaction.followup.send(f"An error occurred: {str(e)}")


def upload_log(id):
    dt = datetime.datetime.now()
    dt = dt.replace(microsecond=0)
    dt = datetime.datetime.strptime(str(dt), '%Y-%m-%d %H:%M:%S')
    dt = dt.strftime('%Y-%m-%d %I:%M %p')

    gfile = DRIVE.CreateFile({'title': f"build_log_{id} {dt}",
                              'parents': [{'id': DEFAULT_BUILD_LOG_FOLDER_ID}]})
    gfile.SetContentFile(BUILD_LOG_PATH)
    gfile.Upload()


def get_datetime(sec):
    dt = datetime.datetime.fromtimestamp(sec / 1e3)
    dt = dt.replace(microsecond=0)
    dt = datetime.datetime.strptime(str(dt), '%Y-%m-%d %H:%M:%S')
    dt = dt.strftime('%Y-%m-%d %I:%M %p')
    return dt

def get_time_hh_mm_ss(sec):
    td_str = str(datetime.timedelta(seconds=sec/1e3))
    x = td_str.split(':')
    return (x[0] + ' Hours ' + x[1] + ' Minutes')


@BOT.event
async def on_ready():
    print(f'{BOT.user} connected to Discord')
    try:
        synced = await BOT.tree.sync()
        print(f"Synced {len(synced)} commands)")
    except Exception as e:
        print(e)


@BOT.tree.command(name="windows_status", description="Get the build status")
@app_commands.describe(build="Build number (-1 for latest build)")
async def status(interaction, build:int = -1):

    build_number = str(build)
    if (build == -1):
        build_number = "lastBuild"

    try:
        response = requests.get(f"http://jenkins_as:{API_TOKEN}@{DEFAULT_BUILD_PATH}/{build_number}/api/json")
        if response.status_code == 200:
            result = response.json()
            name = result["fullDisplayName"]
            status = result["result"]
            duration = result["duration"]
            building = result["building"]
            timestamp = result["timestamp"]
            change_log = result["changeSet"]["items"]

            if (building):
                status = "BUILDING"
            match status:
                case "SUCCESS":
                    color=GREEN
                case "FAILURE":
                    color=RED
                case "ABORTED":
                    color=GRAY
                case _:
                    color=BLURPLE

            change_description_list = [] # Used to separate descriptions to different embed fields
            change_description = ""
            for i in range(len(change_log)):
                change = change_log[i]
                change_number = change["changeNumber"]
                change_msg = change["msg"]
                change_author = change["author"]["fullName"]
                change_item_description = f"- `{change_number}` {change_msg} -_{change_author}_"
                change_item_description = change_item_description.replace("\n", " ") + "\n"

                if (len(change_description + change_item_description) > DISCORD_EMBED_VALUE_LIMIT):
                    change_description_list.append(change_description)
                    change_description = change_item_description
                else:
                    change_description += change_item_description

                if (i == len(change_log) - 1):
                    change_description_list.append(change_description)


            embed = Embed(title=name, color=color)
            embed.add_field(name="Status", value=status, inline=False)
            embed.add_field(name="Timestamp", value=get_datetime(timestamp), inline=True)
            if (not building):
                embed.add_field(name="Duration", value=get_time_hh_mm_ss(duration), inline=True)

            for i in range(len(change_description_list)):
                if (len("".join(change_description_list[:i])) > DISCORD_EMBED_LIMIT):
                    embed.add_field(name="", value="(Changelog too long, omitted)", inline=False)
                    break
                embed.add_field(name="", value=change_description_list[i], inline=False)

            await interaction.response.send_message(embed=embed)
        else:
            embed = Embed(description="Failed to get status.", color=RED)
            await interaction.response.send_message(embed=embed)
            print(f"Error: {response.text}")
    except Exception as e:
        embed = Embed(description="An error occurred.", color=RED)
        await interaction.response.send_message(embed=embed)
        print(e)


@BOT.tree.command(name="windows_log", description="Get the build console log")
@app_commands.describe(build="Build number (-1 for latest build)")
async def log(interaction, build:int = -1):

    build_number = str(build)
    if (build == -1):
        build_number = "lastBuild"

    try:
        await interaction.response.defer()
        response = requests.get(f"http://jenkins_as:{API_TOKEN}@{DEFAULT_BUILD_PATH}/{build_number}/consoleText")
        if response.status_code == 200:
            text_content = response.text
            with open(BUILD_LOG_PATH, "w") as file:
                file.write(text_content)
            upload_log(build_number)
            embed = Embed(title="File Folder", url=DEFAULT_BUILD_LOG_FOLDER_URL, color=GREEN)
            await interaction.followup.send(embed=embed)
            
        else:
            embed = Embed(description="Failed to get logs.", color=RED)
            await interaction.followup.send(embed=embed)
            print(f"Error: {response.text}")
    except Exception as e:
        embed = Embed(description="An error occurred.", color=RED)
        await interaction.followup.send(embed=embed)
        print(e)


@BOT.tree.command(name="windows_start_build", description="Build the latest Saleblazers Default Build")
@app_commands.describe(BuildBranch="Choose from 'Dev' or 'Merge', default is 'Dev'")
async def start_build(interaction, BuildBranch: str = "Dev"):
    try:
        BuildBranchOnJenkins = "BudgetHero"
        if BuildBranch == "Merge":
            BuildBranchOnJenkins = "BudgetHeroMerge"

        response = requests.post(f"http://jenkins_as:{API_TOKEN}@{DEFAULT_BUILD_PATH}/build?token={BUILD_TOKEN}&BuildBranch={BuildBranchOnJenkins}")
        if response.status_code == 201:
            embed = Embed(description="Build request sent.", color=GREEN)
            await interaction.response.send_message(embed=embed)
        else:
            embed = Embed(description="Failed to request the build.", color=RED)
            await interaction.response.send_message(embed=embed)
            print(f"Error: {response.text}")
    except Exception as e:
        embed = Embed(description="An error occurred.", color=RED)
        await interaction.response.send_message(embed=embed)
        print(e)


@BOT.tree.command(name="windows_abort_build", description="Abort the latest Saleblazers Default Build")
async def abort_build(interaction):
    try:
        response = requests.post(f"http://jenkins_as:{API_TOKEN}@{DEFAULT_BUILD_PATH}/lastBuild/stop")
        if response.status_code == 200:
            embed = Embed(description="Abort request sent.", color=GREEN)
            await interaction.response.send_message(embed=embed)
        else:
            embed = Embed(description="Failed to request abort.", color=RED)
            await interaction.response.send_message(embed=embed)
            print(f"Error: {response.text}")
    except Exception as e:
        embed = Embed(description="An error occurred.", color=RED)
        await interaction.response.send_message(embed=embed)
        print(e)



BOT.run(DISCORD_TOKEN)