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

load_dotenv(".env")

flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return "Bot is running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7870)))

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
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

    async def start_bot(self):
        await super().start()
        self.uptime = get_indian_time()

        for attempt in range(5):
            try:
                self.user = await self.get_me()
                self.set_parse_mode(ParseMode.HTML)
                self.username = self.user.username
                db_channel = await self.get_chat(CHANNEL_ID)
                self.db_channel = db_channel
                break
            except Exception as e:
                self.LOGGER(__name__).warning(f"Startup retry {attempt + 1}/5 failed: {e}")
                await asyncio.sleep(5)
        else:
            self.LOGGER(__name__).error("Failed to start after retries. Shutting down.")
            sys.exit()

        self.LOGGER(__name__).info(f"Bot Running..! Made by @rohit_1888")

        try:
            await self.send_message(OWNER_ID, text=f"<b><blockquote>🤖 Bot Restarted by @rohit_1888</blockquote></b>")
        except:
            pass

        asyncio.create_task(self.run_web_server())

    async def run_web_server(self):
        try:
            app = web.AppRunner(await web_server())
            await app.setup()
            await web.TCPSite(app, "0.0.0.0", PORT).start()
            self.LOGGER(__name__).info("Web server started.")
        except Exception as e:
            self.LOGGER(__name__).error(f"Web server failed: {e}")

    async def stop_bot(self):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")

async def main():
    keep_alive()
    bot = Bot()
    await bot.start_bot()

    try:
        while True:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, SystemExit):
        await bot.stop_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        LOGGER(__name__).error(f"Fatal error: {e}")