import requests
import aria2p
from datetime import datetime
from status import format_progress_bar
import asyncio
import base64
import logging
import os
import random
import re
import string 
import string as rohit
import time
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode, ChatAction
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from plugins.autoDelete import auto_del_notification, delete_message
from bot import Bot
from config import *
from helper_func import *
from database.database import *
from database.database import db
from database.db_premium import *
from config import *
from plugins.FORMATS import *
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid
from datetime import datetime, timedelta
from pytz import timezone
from io import BytesIO
#import httpx
from aiofiles import open as aio_open
import aiohttp, aiofiles
import mmap
from shutil import which
import subprocess

import os
import aiohttp
import aiofiles
import random
import asyncio
import logging
import time
from datetime import datetime
from collections import defaultdict

#rohit95 old token

TERABOX_API_URL = "https://terabox.web.id"
TERABOX_API_TOKEN = "85ebfdd8-77d5-4725-a3b6-3a03ba188a5c_7328629001"
THUMBNAIL = "https://envs.sh/S-T.jpg"


downloads_manager = {}


async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def download(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int) -> str:
    sanitized_filename = filename.replace("/", "_").replace("\\", "_")
    file_path = os.path.join(os.getcwd(), sanitized_filename)

    download_key = f"{user_id}-{sanitized_filename}"  # Unique key per file
    downloads_manager[download_key] = {"downloaded": 0}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=900)) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch video: HTTP {resp.status}")

            total_size = int(resp.headers.get("Content-Length", 0)) or file_size
            start_time = datetime.now()
            last_update_time = time.time()

            async def progress(current, total):
                nonlocal last_update_time
                percentage = (current / total) * 100 if total else 0
                elapsed_time_seconds = (datetime.now() - start_time).total_seconds()
                speed = current / elapsed_time_seconds if elapsed_time_seconds > 0 else 0
                eta = (total - current) / speed if speed > 0 else 0

                if time.time() - last_update_time > 2:
                    progress_text = format_progress_bar(
                        filename=filename,
                        percentage=percentage,
                        done=current,
                        total_size=total,
                        status="Downloading",
                        eta=eta,
                        speed=speed,
                        elapsed=elapsed_time_seconds,
                        user_mention=user_mention,
                        user_id=user_id,
                        aria2p_gid=""
                    )
                    try:
                        await reply_msg.edit_text(progress_text)
                        last_update_time = time.time()
                    except Exception as e:
                        logging.warning(f"Error updating progress message: {e}")

            async with aiofiles.open(file_path, 'wb') as f:
                while True:
                    chunk = await resp.content.read(10 * 1024 * 1024)  # 10MB chunks
                    if not chunk:
                        break
                    if downloads_manager[download_key]["downloaded"] + len(chunk) > total_size:
                        logging.warning(f"Download exceeded expected size for {filename}. Stopping...")
                        break
                    await f.write(chunk)
                    downloads_manager[download_key]['downloaded'] += len(chunk)
                    await progress(downloads_manager[download_key]['downloaded'], total_size)

    downloads_manager.pop(download_key, None)  # Cleanup after completion
    return file_path


async def download_video(url, reply_msg, user_mention, user_id, client, db_channel_id, message, max_retries=3):
    try:
        logging.info(f"Fetching video info: {url}")

        api_response = await fetch_json(f"{TERABOX_API_URL}/url?url={url}&token={TERABOX_API_TOKEN}")

        if not api_response or not isinstance(api_response, list) or "filename" not in api_response[0]:
            raise Exception("Invalid API response format.")

        data = api_response[0]
        download_link = data["direct_link"]  # Use direct link instead of cookie-authenticated one
        video_title = data["filename"]
        file_size = int(data.get("size", 0))
        thumb_url = data["thumbnail"]

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

        for attempt in range(1, max_retries + 1):
            try:
                file_path = await asyncio.create_task(
                    download(download_link, user_id, video_title, reply_msg, user_mention, file_size)
                )
                break
            except Exception as e:
                logging.warning(f"Download failed (Attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    raise e
                await asyncio.sleep(3)

        await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")

        return file_path, thumb_url, video_title, None

    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return None, None, None, None


def generate_thumbnail(video_path: str, output_path: str, time_position: int = 10) -> str:
    try:
        subprocess.run(
            [
                "ffmpeg", "-ss", str(time_position), "-i", video_path,
                "-vframes", "1", "-q:v", "2", "-vf", "scale=320:-1",
                output_path
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return output_path if os.path.exists(output_path) else None
    except Exception as e:
        logging.warning(f"Thumbnail generation failed: {e}")
        return None

def get_video_duration(file_path: str) -> int:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return int(float(result.stdout.strip()))
    except Exception as e:
        logging.warning(f"Failed to get duration: {e}")
        return 0

uploads_manager = {}

async def upload_video(client, file_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message):
    try:
        # Create the background task to handle upload
        uploads_manager.setdefault(user_id, []).append(file_path)

        file_size = os.path.getsize(file_path)
        uploaded = 0
        start_time = datetime.now()
        last_update_time = time.time()

        # Fetch config options
        AUTO_DEL, DEL_TIMER, HIDE_CAPTION, CHNL_BTN, PROTECT_MODE = await asyncio.gather(
            db.get_auto_delete(), db.get_del_timer(), db.get_hide_caption(),
            db.get_channel_button(), db.get_protect_content()
        )
        button_name, button_link = await db.get_channel_button_link() if CHNL_BTN else (None, None)

        # Thumbnail + duration
        thumbnail_path = f"{file_path}.jpg"
        thumbnail_path = generate_thumbnail(file_path, thumbnail_path)
        duration = get_video_duration(file_path)

        # Progress function
        async def progress(current, total):
            nonlocal uploaded, last_update_time
            uploaded = current
            percentage = (current / total) * 100
            elapsed = (datetime.now() - start_time).total_seconds()
            if time.time() - last_update_time > 2:
                eta = (total - current) / (current / elapsed) if current > 0 else 0
                speed = current / elapsed if current > 0 else 0
                progress_text = format_progress_bar(
                    filename=video_title,
                    percentage=percentage,
                    done=current,
                    total_size=total,
                    status="Uploading",
                    eta=eta,
                    speed=speed,
                    elapsed=elapsed,
                    user_mention=user_mention,
                    user_id=user_id,
                    aria2p_gid=""
                )
                try:
                    await reply_msg.edit_text(progress_text)
                    last_update_time = time.time()
                except Exception as e:
                    logging.warning(f"Progress update failed: {e}")

        # Upload to DB channel
        collection_message = await client.send_video(
            chat_id=db_channel_id,
            video=file_path,
            caption=f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>",
            thumb=thumbnail_path if thumbnail_path else None,
            duration=duration,
            supports_streaming=True,
            progress=progress,
            protect_content=PROTECT_MODE
        )

        # Copy to user
        copied_msg = await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=db_channel_id,
            message_id=collection_message.id
        )

        caption = "" if HIDE_CAPTION else f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=button_name, url=button_link)]]) if CHNL_BTN else None

        await copied_msg.edit_caption(
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

        if AUTO_DEL:
            asyncio.create_task(delete_message(copied_msg, DEL_TIMER))

        # Send sticker and delete after 5 seconds
        sticker_msg = await message.reply_sticker("CAACAgIAAxkBAAEZdwRmJhCNfFRnXwR_lVKU1L9F3qzbtAAC4gUAAj-VzApzZV-v3phk4DQE")
        await asyncio.sleep(5)
        await sticker_msg.delete()

        return collection_message.id

    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        return None

    finally:
        # Clean up
        uploads_manager[user_id].remove(file_path)
        if not uploads_manager[user_id]:
            uploads_manager.pop(user_id)

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(f"{file_path}.jpg"):
                os.remove(f"{file_path}.jpg")
            await message.delete()
            await reply_msg.delete()
        except Exception as e:
            logging.warning(f"Cleanup error: {e}")