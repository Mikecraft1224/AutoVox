import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import asyncio
import os
import sys	
import subprocess

import log_helper
from log_helper import LogTypes

import database

import config

# Initialize bot with all intents
bot = commands.Bot(intents=discord.Intents.all())
logger = log_helper.Logger("Main")

# Bot event handlers
@bot.event
async def on_ready():
    # Set bot's presence
    await bot.change_presence(activity=discord.Game(name="AutoVox"), status=discord.Status.online)
    logger.log("Bot is Online!", LogTypes.SUCCESS)


@bot.event
async def on_command_error(ctx, error):
    # Global error handler for commands
    embed = discord.Embed(title="An error occurred", description=f"```{error}```", color=discord.Color.red())
    embed.add_field(name="Report", value="Please report this error to the AutoVox team. You can join the support server [here](https://discord.gg/8HbjJBGWBd)")
    embed.set_footer(text="Made with ❤ by the AutoVox team")
    ctx.response.send_message(f"An error occurred: {error}", LogTypes.ERROR)

    logger.log(f"An error occurred: {error}", LogTypes.ERROR)


@bot.event
async def on_guild_join(guild):
    # When the bot joins a guild
    logger.log(f"Joined guild: {guild.name}, {guild.id}", LogTypes.INFO)

@bot.event
async def on_guild_remove(guild):
    # When the bot leaves a guild
    logger.log(f"Left guild: {guild.name}, {guild.id}", LogTypes.INFO)


@bot.event
async def on_interaction(interaction):
    # When an interaction is invoked
    data = interaction.data
    name = data["name"]+" "+(data["options"][0]["name"]if "options" in data else "")
    logger.log(f"Interaction invoked: {name}", LogTypes.INFO)

    # Add the user to the database if they don't exist
    if not database.execute_read_query(f"SELECT * FROM users WHERE id = {interaction.user.id}"):
        database.execute_query(f"INSERT INTO users (id) VALUES ({interaction.user.id})")
        logger.log(f"Added user {interaction.user.name}({interaction.user.id}) to the database", LogTypes.INFO)

    # Process the interaction
    await bot.process_application_commands(interaction)

    


@bot.event
async def restart(ctx): # can be triggered in a cog by self.bot.dispatch("restart")
    # Restart the bot
    logger.log("Restarting...", LogTypes.SYSTEM)
    await ctx.send("Restarting...")
    await bot.close()
    os.execv(sys.executable, ['python'] + sys.argv)



# Load extensions (cogs) from the 'cogs' directory
async def load_extensions():
    logger.log("Loading Cogs...", LogTypes.SYSTEM)
    for filename in os.listdir("cogs"):
        if filename.endswith(".py"):
            cog_name = f"cogs.{filename[:-3]}"
            try:
                bot.load_extension(cog_name)
                logger.log(f"Loaded {cog_name}", LogTypes.SUCCESS)
            except Exception as e:
                logger.log(f"Failed to load {cog_name}: {e}", LogTypes.ERROR)



# Check for updates on GitHub
@tasks.loop(minutes=30)
async def check_for_updates():
    logger.log("Checking for updates...", LogTypes.SYSTEM)
    result = subprocess.run(["git", "fetch", config.load_value("repo_url")], capture_output=True, text=True)
    if result.returncode != 0:
        logger.log(f"Failed to fetch updates: {result.stderr}", LogTypes.ERROR)
        return

    result = subprocess.run(["git", "status", "-uno"], capture_output=True, text=True)
    if "Your branch is behind" in result.stdout:
        logger.log("Updates found. Updating...", LogTypes.SYSTEM)
        await update_and_restart()

async def update_and_restart():
    logger.log("Shutting down for update...", LogTypes.SYSTEM)
    await bot.close()

    result = subprocess.run(["git", "pull", config.load_value("repo_url")], capture_output=True, text=True)
    if result.returncode != 0:
        logger.log(f"Failed to pull updates: {result.stderr}", LogTypes.ERROR)
        return

    logger.log("Restarting with updates...", LogTypes.SYSTEM)
    os.execv(sys.executable, ['python'] + sys.argv)

async def create_database():
    # Create the database if it doesn't exist
    logger.log("Creating Database...", LogTypes.SYSTEM)
    database.execute_query("CREATE TABLE IF NOT EXISTS standard_roles (guild_id BIGINT, role_id BIGINT)")
    database.execute_query("CREATE TABLE IF NOT EXISTS settings (guild_id BIGINT, setting_name TEXT, setting_value TEXT)")
    database.execute_query("CREATE TABLE IF NOT EXISTS users (id BIGINT, language_code TEXT DEFAULT 'en')")
    logger.log("Database is ready", LogTypes.SUCCESS)

# Main entry point
if __name__ == "__main__":
    logger.log("Starting AutoVox...", LogTypes.SYSTEM)
    logger.log("Checking database connection...", LogTypes.SYSTEM)
    if not database.check_database():
        logger.log("Failed to connect to the database. Exiting...", LogTypes.ERROR)
        sys.exit(1)
    logger.log("Database connection successful", LogTypes.SUCCESS)
    load_dotenv()
    try:
        asyncio.run(create_database())
        asyncio.run(load_extensions())
        logger.log("Starting Bot...", LogTypes.SYSTEM)
        TOKEN = os.getenv('TOKEN')  # Ensure that the TOKEN is loaded from the environment variables
        asyncio.run(bot.start(TOKEN))
        logger.log("Bot has started", LogTypes.SUCCESS)
    except KeyboardInterrupt:
        logger.log("Shutdown signal received", LogTypes.SYSTEM)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(bot.close())  # Gracefully close the bot
        logger.log("Bot has been gracefully shutdown.", LogTypes.SUCCESS)
    except Exception as e:
        logger.log(f"An error occurred: {e}", LogTypes.ERROR)
    finally:
        loop.close()  # Close the asyncio loop