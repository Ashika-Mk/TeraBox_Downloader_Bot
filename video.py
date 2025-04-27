# imports
import requests
import aria2p
import asyncio
import base64
import logging
import os
import random
import re
import string
import time
from datetime import datetime, timedelta
from collections import defaultdict
import aiohttp
import aiofiles
import subprocess
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode, ChatAction
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from plugins.autoDelete import auto_del_notification, delete_message
from bot import Bot
from config import *
from helper_func import *
from database.database import db
from database.db_premium import *
from plugins.FORMATS import *

# Constants
TERABOX_API_URL = "https://terabox.web.id"
TERABOX_API_TOKEN = "85ebfdd8-77d5-4725-a3b6-3a03ba188a5c_7328629001"

downloads_manager = {}
uploads_manager = {}
user_semaphores = defaultdict(lambda: asyncio.Semaphore(4))  # Max 4 tasks per user

# ------------------------------ Helpers ------------------------------

async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def download_thumbnail(url: str) -> str:
    filename = "thumbnail.jpg"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download thumbnail: HTTP {resp.status}")
            async with aiofiles.open(filename, 'wb') as f:
                await f.write(await resp.read())
    return os.path.abspath(filename)

def generate_thumbnail(video_path: str, output_path: str, time_position: int = 10) -> str:
    try:
        subprocess.run([
            "ffmpeg", "-ss", str(time_position), "-i", video_path,
            "-vframes", "1", "-q:v", "2", "-vf", "scale=320:-1",
            output_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_path if os.path.exists(output_path) else None
    except Exception as e:
        logging.warning(f"Thumbnail generation failed: {e}")
        return None

def get_video_duration(file_path: str) -> int:
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return int(float(result.stdout.strip()))
    except Exception as e:
        logging.warning(f"Failed to get duration: {e}")
        return 0

# ------------------------------ Main Functions ------------------------------

async def download(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int) -> str:
    sanitized_filename = filename.replace("/", "_").replace("\\", "_")
    file_path = os.path.join(os.getcwd(), sanitized_filename)

    cookies = await fetch_json(f"{TERABOX_API_URL}/gc?token={TERABOX_API_TOKEN}")
    download_key = f"{user_id}-{sanitized_filename}"
    downloads_manager[download_key] = {"downloaded": 0}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=900), cookies=cookies) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch video: HTTP {resp.status}")

            total_size = int(resp.headers.get("Content-Length", 0)) or file_size
            start_time = datetime.now()
            last_update_time = time.time()

            async def progress(current, total):
                nonlocal last_update_time
                if time.time() - last_update_time > 2:
                    percentage = (current / total) * 100
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0
                    progress_text = format_progress_bar(
                        filename=filename, percentage=percentage, done=current, total_size=total,
                        status="Downloading", eta=eta, speed=speed, elapsed=elapsed,
                        user_mention=user_mention, user_id=user_id, aria2p_gid=""
                    )
                    try:
                        await reply_msg.edit_text(progress_text)
                        last_update_time = time.time()
                    except Exception as e:
                        logging.warning(f"Progress update failed: {e}")

            async with aiofiles.open(file_path, 'wb') as f:
                while True:
                    chunk = await resp.content.read(10 * 1024 * 1024)  # 10 MB
                    if not chunk:
                        break
                    await f.write(chunk)
                    downloads_manager[download_key]["downloaded"] += len(chunk)
                    await progress(downloads_manager[download_key]["downloaded"], total_size)

    downloads_manager.pop(download_key, None)
    return file_path

async def download_video(url, reply_msg, user_mention, user_id, max_retries=3):
    try:
        data = await fetch_json(f"{TERABOX_API_URL}/url?url={url}&token={TERABOX_API_TOKEN}")
        if not data or not isinstance(data, list) or "filename" not in data[0]:
            raise Exception("Invalid API response.")

        item = data[0]
        download_link = item["link"] + f"&random={random.randint(1, 10)}"
        video_title = item["filename"]
        file_size = int(item.get("size", 0))
        thumb_url = item.get("thumbnail")

        for attempt in range(1, max_retries + 1):
            try:
                file_path = await download(download_link, user_id, video_title, reply_msg, user_mention, file_size)
                break
            except Exception as e:
                if attempt == max_retries:
                    raise
                await asyncio.sleep(3)

        await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")
        return file_path, thumb_url, video_title, None
    except Exception as e:
        logging.error(f"Download error: {e}")
        return None, None, None, None

async def upload_video(client, file_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message):
    async with user_semaphores[user_id]:
        try:
            uploads_manager[user_id] = file_path
            file_size = os.path.getsize(file_path)
            start_time = datetime.now()
            last_update_time = time.time()

            AUTO_DEL, DEL_TIMER, HIDE_CAPTION, CHNL_BTN, PROTECT_MODE = await asyncio.gather(
                db.get_auto_delete(), db.get_del_timer(), db.get_hide_caption(),
                db.get_channel_button(), db.get_protect_content()
            )
            button_name, button_link = await db.get_channel_button_link() if CHNL_BTN else (None, None)

            thumbnail_path = f"{file_path}.jpg"
            thumbnail_path = generate_thumbnail(file_path, thumbnail_path)
            duration = get_video_duration(file_path)

            async def progress(current, total):
                nonlocal last_update_time
                if time.time() - last_update_time > 2:
                    percentage = (current / total) * 100
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0
                    progress_text = format_progress_bar(
                        filename=video_title, percentage=percentage, done=current, total_size=total,
                        status="Uploading", eta=eta, speed=speed, elapsed=elapsed,
                        user_mention=user_mention, user_id=user_id, aria2p_gid=""
                    )
                    try:
                        await reply_msg.edit_text(progress_text)
                        last_update_time = time.time()
                    except Exception as e:
                        logging.warning(f"Progress update failed: {e}")

            sent = await client.send_video(
                chat_id=db_channel_id,
                video=file_path,
                thumb=thumbnail_path if thumbnail_path else None,
                caption=f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>",
                duration=duration,
                supports_streaming=True,
                progress=progress
            )

            copied = await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=db_channel_id,
                message_id=sent.id
            )

            if not HIDE_CAPTION:
                caption = f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>"
                markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_name, url=button_link)]]) if CHNL_BTN else None
                await copied.edit_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=markup)

            if AUTO_DEL:
                asyncio.create_task(delete_message(copied, DEL_TIMER))

            os.remove(file_path)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

            await message.delete()
            await reply_msg.delete()

        except Exception as e:
            logging.error(f"Upload error: {e}")