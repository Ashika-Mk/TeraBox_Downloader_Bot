import asyncio
from aiohttp import web
from flask import Flask
from threading import Thread
import os
import pyromod.listen
from pyrogram import Client
from pyrogram.enums import ParseMode
import sys
from datetime import datetime
import pytz  # For Indian Standard Time (IST)
import aria2p
from config import *
from dotenv import load_dotenv
from database.db_premium import remove_expired_users
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv(".env")

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("CodeXBotz")

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

# Rename Flask app instance to avoid conflict
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3413)))

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

def get_indian_time():
    """Returns the current time in IST."""
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
            plugins={
                "root": "plugins"
            },
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN
        )
        self.LOGGER = LOGGER
        self.scheduler = AsyncIOScheduler()

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = get_indian_time()

        try:
            db_channel = await self.get_chat(CHANNEL_ID)
            self.db_channel = db_channel
        except Exception as e:
            self.LOGGER(__name__).warning(e)
            self.LOGGER(__name__).warning(
                f"Make Sure bot is Admin in DB Channel, and Double check the CHANNEL_ID Value, Current Value {CHANNEL_ID}"
            )
            self.LOGGER(__name__).info("\nBot Stopped. @Zenotty for support")
            sys.exit()

        self.set_parse_mode(ParseMode.HTML)
        self.username = usr_bot_me.username
        self.LOGGER(__name__).info(f"Bot Running..! Made by @Zenotty")   

        # Start Web Server
        app = web.AppRunner(await web_server())
        await app.setup()
        await web.TCPSite(app, "0.0.0.0", PORT).start()

        try:
            await self.send_message(OWNER_ID, text=f"<b><blockquote>🤖 Bᴏᴛ Rᴇsᴛᴀʀᴛᴇᴅ by @rohit_1888</blockquote></b>")
        except:
            pass

    

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")

    def run(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.start())
        self.LOGGER(__name__).info("Bot is now running. Thanks to @Rohit_1888")
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            self.LOGGER(__name__).info("Shutting down...")
        finally:
            loop.run_until_complete(self.stop())

if __name__ == "__main__":
    keep_alive()
    Bot().run()