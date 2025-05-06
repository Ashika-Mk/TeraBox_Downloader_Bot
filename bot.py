import asyncio
from aiohttp import web
from plugins import web_server
from flask import Flask
from threading import Thread
import os
import pyromod.listen
from pyrogram import Client
from pyrogram.enums import ParseMode
import sys
from datetime import datetime
import pytz
import aria2p
from config import *
from dotenv import load_dotenv
from database.db_premium import remove_expired_users
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pyrogram.utils

pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

load_dotenv(".env")

# Rename Flask app instance to avoid conflict
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7867)))

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

def get_indian_time():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist)

aria2 = aria2p.API(
    aria2p.Client(
        host="http://localhost",
        port=6800,
        secret=""
    )
)

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN
        )
        self.LOGGER = LOGGER

    async def on_start(self):
        usr_bot_me = await self.get_me()
        self.uptime = get_indian_time()

        try:
            db_channel = await self.get_chat(CHANNEL_ID)
            self.db_channel = db_channel
        except Exception as e:
            self.LOGGER(__name__).warning(e)
            self.LOGGER(__name__).warning(
                f"Make sure the bot is admin in DB Channel, and double-check CHANNEL_ID value: {CHANNEL_ID}"
            )
            self.LOGGER(__name__).info("\nBot Stopped. @rohit_1888 for support")
            return await self.stop()

        self.set_parse_mode(ParseMode.HTML)
        self.username = usr_bot_me.username
        self.LOGGER(__name__).info(f"Bot Running..! Made by @rohit_1888")

        app = web.AppRunner(await web_server())
        await app.setup()
        await web.TCPSite(app, "0.0.0.0", PORT).start()

        try:
            await self.send_message(OWNER_ID, text="<b><blockquote>🤖 Bᴏᴛ Rᴇsᴛᴀʀᴛᴇᴅ by @rohit_1888</blockquote></b>")
        except:
            pass

    async def on_stop(self):
        self.LOGGER(__name__).info("Bot stopped.")

if __name__ == "__main__":
    keep_alive()
    Bot().run()