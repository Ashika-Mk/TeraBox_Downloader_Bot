import requests
import aria2p
import asyncio
import base64
import logging
import os
import random
import re
import string as rohit
from status import format_progress_bar
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode, ChatAction
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, PeerIdInvalid
from plugins.autoDelete import auto_del_notification, delete_message
from bot import Bot
from config import *
from helper_func import *
from database.database import db
from database.db_premium import *
from plugins.FORMATS import *
from pytz import timezone
import httpx
import aiohttp
import aiofiles
from aiofiles import open as aio_open
from shutil import which
import subprocess
from collections import defaultdict

# Rohit95 old token
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

    cookies = await fetch_json(f"{TERABOX_API_URL}/gc?token={TERABOX_API_TOKEN}")
    download_key = f"{user_id}-{sanitized_filename}"
    downloads_manager[download_key] = {"downloaded": 0}

    CHUNK_SIZE = 20 * 1024 * 1024  # 20MB
    MAX_CONCURRENT_CONNECTIONS = 4  # Number of parallel downloads

    headers = {
        "Range": f"bytes=0-{file_size-1}"
    }

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=1800),
        cookies=cookies
    ) as session:
        while True:
            async with session.head(url) as resp:
                if resp.status not in [200, 206]:
                    if resp.status == 302:
                        # Handle redirect
                        redirect_url = resp.headers.get("Location")
                        logging.info(f"Redirected to {redirect_url}")
                        url = redirect_url  # Follow the redirection
                        continue  # Retry with the new URL
                    raise Exception(f"Server error: HTTP {resp.status}")

            part_size = file_size // MAX_CONCURRENT_CONNECTIONS

            async def download_part(start, end, part_num):
                part_headers = {"Range": f"bytes={start}-{end}"}
                async with session.get(url, headers=part_headers, allow_redirects=True) as resp:
                    if resp.status not in [206, 200]:
                        raise Exception(f"Failed part {part_num}: HTTP {resp.status}")
                    async with aiofiles.open(file_path, 'rb+') as f:
                        await f.seek(start)
                        while True:
                            chunk = await resp.content.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            await f.write(chunk)
                            downloads_manager[download_key]['downloaded'] += len(chunk)

            async def update_progress():
                start_time = datetime.now()
                last_update_time = 0
                while downloads_manager.get(download_key):
                    now = time.time()
                    if now - last_update_time > 2:
                        current = downloads_manager[download_key]['downloaded']
                        percentage = (current / file_size) * 100
                        elapsed = (datetime.now() - start_time).total_seconds()
                        speed = current / elapsed if elapsed > 0 else 0
                        eta = (file_size - current) / speed if speed > 0 else 0

                        progress_text = format_progress_bar(
                            filename=filename,
                            percentage=percentage,
                            done=current,
                            total_size=file_size,
                            status="Downloading",
                            eta=eta,
                            speed=speed,
                            elapsed=elapsed,
                            user_mention=user_mention,
                            user_id=user_id,
                            aria2p_gid=""
                        )
                        try:
                            await reply_msg.edit_text(progress_text)
                        except Exception as e:
                            logging.warning(f"Progress update error: {e}")
                        last_update_time = now
                    await asyncio.sleep(1)

            # Pre-allocate file
            with open(file_path, 'wb') as f:
                f.truncate(file_size)

            download_tasks = []
            for part in range(MAX_CONCURRENT_CONNECTIONS):
                start = part * part_size
                end = (start + part_size - 1) if part < MAX_CONCURRENT_CONNECTIONS - 1 else file_size - 1
                download_tasks.append(download_part(start, end, part))

            await asyncio.gather(update_progress(), *download_tasks)

            break  # Exit the loop once the download is complete

    downloads_manager.pop(download_key, None)
    return file_path

async def download_video(url, reply_msg, user_mention, user_id, max_retries=3):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details
        api_response = await fetch_json(f"{TERABOX_API_URL}/url?url={url}&token={TERABOX_API_TOKEN}")

        if not api_response or not isinstance(api_response, list) or "filename" not in api_response[0]:
            raise Exception("Invalid API response format.")

        data = api_response[0]
        download_link = data["link"] + f"&random={random.randint(1, 10)}"
        video_title = data["filename"]
        file_size = int(data.get("size", 0))
        thumb_url = data.get("thumbnail", THUMBNAIL)

        logging.info(f"Downloading: {video_title} | Size: {file_size} bytes")

        if file_size == 0:
            raise Exception("Invalid file size detected.")

        for attempt in range(1, max_retries + 1):
            try:
                file_path = await asyncio.create_task(
                    download(download_link, user_id, video_title, reply_msg, user_mention, file_size)
                )
                break
            except Exception as e:
                logging.warning(f"Download attempt {attempt}/{max_retries} failed: {e}")
                if attempt == max_retries:
                    raise e
                await asyncio.sleep(3)

        await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")
        return file_path, thumb_url, video_title, None

    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return None, None, None, None


uploads_manager = {}

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

async def upload_video(client, file_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message):
    try:
        uploads_manager[user_id] = file_path
        file_size = os.path.getsize(file_path)
        uploaded = 0
        start_time = datetime.now()
        last_update_time = time.time()

        # Fetch configs
        AUTO_DEL, DEL_TIMER, HIDE_CAPTION, CHNL_BTN, PROTECT_MODE = await asyncio.gather(
            db.get_auto_delete(), db.get_del_timer(), db.get_hide_caption(),
            db.get_channel_button(), db.get_protect_content()
        )
        button_name, button_link = await db.get_channel_button_link() if CHNL_BTN else (None, None)

        # Generate thumbnail
        thumbnail_path = f"{file_path}.jpg"
        thumbnail_path = generate_thumbnail(file_path, thumbnail_path)

        # Fix duration
        duration = get_video_duration(file_path)

        # Upload progress
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

        # Copy to user chat
        copied_msg = await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=db_channel_id,
            message_id=collection_message.id
        )

        # Final caption + button
        caption = "" if HIDE_CAPTION else f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=button_name, url=button_link)]]) if CHNL_BTN else None

        await copied_msg.edit_caption(
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

        # Auto delete
        if AUTO_DEL:
            asyncio.create_task(delete_message(copied_msg, DEL_TIMER))

        # Cleanups
        try:
            os.remove(file_path)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        except Exception as e:
            logging.warning(f"Failed to clean file: {e}")

        try:
            await message.delete()
            await reply_msg.delete()
        except Exception as e:
            logging.warning(f"Failed to delete messages: {e}")

        # Optional sticker
        try:
            sticker_msg = await message.reply_sticker("CAACAgIAAxkBAAEZdwRmJhCNfFRnXwR_lVKU1L9F3qzbtAAC4gUAAj-VzApzZV-v3phk4DQE")
            await asyncio.sleep(5)
            await sticker_msg.delete()
        except Exception:
            pass

        return collection_message.id

    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        return None
    finally:
        uploads_manager.pop(user_id, None)