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


async def download(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int) -> str:
    sanitized_filename = filename.replace("/", "_").replace("\\", "_")
    file_path = os.path.join(os.getcwd(), sanitized_filename)

    cookies = await fetch_json(f"{TERABOX_API_URL}/gc?token={TERABOX_API_TOKEN}")

    download_key = f"{user_id}-{sanitized_filename}"  # Unique key per file
    downloads_manager[download_key] = {"downloaded": 0}

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=900),
        cookies=cookies
    ) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch video: HTTP {resp.status}")

            total_size = int(resp.headers.get("Content-Length", 0)) or file_size  # Ensure file size is correct
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
                    chunk = await resp.content.read(20 * 1024 * 1024)  # 20MB chunks
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

async def download_video(url, reply_msg, user_mention, user_id, max_retries=3):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details
        api_response = await fetch_json(f"{TERABOX_API_URL}/url?url={url}&token={TERABOX_API_TOKEN}")

        if not api_response or not isinstance(api_response, list) or "filename" not in api_response[0]:
            raise Exception("Invalid API response format.")

        # Extract details from response
        data = api_response[0]
        download_link = data["link"] + f"&random={random.randint(1, 10)}"
        video_title = data["filename"]
        file_size = int(data.get("size", 0))  # Convert to int to ensure proper type
        thumb_url = data["thumbnail"] # Use default if missing

        logging.info(f"Downloading: {video_title} | Size: {file_size} bytes")

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

        # Retry logic for robustness
        for attempt in range(1, max_retries + 1):
            try:
                file_path = await asyncio.create_task(download(download_link, user_id, video_title, reply_msg, user_mention, file_size))
                break  # Exit loop if successful
            except Exception as e:
                logging.warning(f"Download failed (Attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    raise e  # Raise error if all retries fail
                await asyncio.sleep(3)

        # Send completion message
        await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")
        return file_path, thumb_url, video_title, None  # No duration in response

    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return None, None, None, None

async def upload_video(client, file_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message, max_retries=3):
    try:
        # Retry logic for upload attempts
        for attempt in range(1, max_retries + 1):
            try:
                collection_message = await upload_helper(client, file_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)
                return collection_message  # Exit loop if successful
            except Exception as e:
                logging.warning(f"Upload failed (Attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    raise e  # Raise error if all retries fail
                await asyncio.sleep(3)

    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        return None

async def upload_helper(client, file_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message):
    # Core upload logic (no retries here, it's handled by the calling function)
    
    file_size = os.path.getsize(file_path)
    uploaded = 0
    start_time = datetime.now()
    last_update_time = time.time()

    # Fetch config individually
    AUTO_DEL = await db.get_auto_delete()
    DEL_TIMER = await db.get_del_timer()
    HIDE_CAPTION = await db.get_hide_caption()
    CHNL_BTN = await db.get_channel_button()
    PROTECT_MODE = await db.get_protect_content()
    button_data = await db.get_channel_button_link()
    button_name, button_link = button_data if CHNL_BTN else (None, None)

    # Generate thumbnail
    thumbnail_path = f"{file_path}.jpg"
    thumbnail_path = generate_thumbnail(file_path, thumbnail_path)

    # Get duration
    duration = get_video_duration(file_path)

    # Upload progress updater
    async def progress(current, total):
        nonlocal uploaded, last_update_time
        uploaded = current
        percentage = (current / total) * 100 if total else 0
        elapsed = (datetime.now() - start_time).total_seconds()
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0

        if time.time() - last_update_time > 2:
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

    # Start the actual upload
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

    # Copy the message to the user's chat
    copied_msg = await client.copy_message(
        chat_id=message.chat.id,
        from_chat_id=db_channel_id,
        message_id=collection_message.id
    )

    # Update caption and buttons if needed
    caption = "" if HIDE_CAPTION else f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=button_name, url=button_link)]]) if CHNL_BTN else None

    await copied_msg.edit_caption(
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

    # Set up auto-delete if enabled
    if AUTO_DEL:
        asyncio.create_task(delete_message(copied_msg, DEL_TIMER))

    # Clean up files after upload
    try:
        os.remove(file_path)
        if thumbnail_path and os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
    except Exception as e:
        logging.warning(f"Cleanup error: {e}")

    # Delete reply and user command message
    await asyncio.gather(
        reply_msg.delete(),
        message.delete()
    )

    # Send optional sticker
    try:
        sticker_msg = await message.reply_sticker("CAACAgIAAxkBAAEZdwRmJhCNfFRnXwR_lVKU1L9F3qzbtAAC4gUAAj-VzApzZV-v3phk4DQE")
        await asyncio.sleep(5)
        await sticker_msg.delete()
    except Exception:
        pass

    return collection_message.id