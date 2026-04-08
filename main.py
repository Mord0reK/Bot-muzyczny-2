import os
import time
import logging
import asyncio
import aiohttp

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config.settings import LOG_LEVEL, DATA_FOLDER

load_dotenv()

os.makedirs(DATA_FOLDER, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logging.info(f"Zalogowano jako {bot.user}")
    try:
        synced = await bot.tree.sync()
        logging.info(f"Zsynchronizowano {len(synced)} komend")
    except Exception as e:
        logging.error(f"Błąd synchronizacji komend: {e}")

async def load_cogs():
    cogs_folder = "cogs"
    for folder in os.listdir(cogs_folder):
        folder_path = os.path.join(cogs_folder, folder)
        if os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if file.endswith(".py") and not file.startswith("_"):
                    cog_path = f"{cogs_folder}.{folder}.{file[:-3]}"
                    try:
                        await bot.load_extension(cog_path)
                        logging.info(f"Załadowano cog: {cog_path}")
                    except Exception as e:
                        logging.error(f"Błąd ładowania cog {cog_path}: {e}")

bot.setup_hook = load_cogs

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token or token == "twoj_token_bota_tutaj":
        logging.error("Ustaw DISCORD_TOKEN w pliku .env")
        return

    bot.run(token)


if __name__ == "__main__":
    main()
