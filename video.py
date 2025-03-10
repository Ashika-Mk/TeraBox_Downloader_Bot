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
import httpx
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

TERABOX_API_URL = "https://terabox.web.id"
TERABOX_API_TOKEN = "rohit95"
THUMBNAIL = "https://envs.sh/S-T.jpg"

downloads_manager = {}

async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def download(url: str, user_id: int, reply_msg, video_title, user_mention) -> str:
    dir_path = 'DL'
    os.makedirs(dir_path, exist_ok=True)  # Ensure the directory exists

    path = f'{dir_path}/{user_id}_{random.randint(1,10)}.mp4'  # Prevent overwrite

    # Get fresh cookies for every request
    cookies = await fetch_json(f"{TERABOX_API_URL}/gc?token={TERABOX_API_TOKEN}")

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=900),  # 15-minute timeout
        cookies=cookies
    ) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch video: HTTP {resp.status}")

            async with aiofiles.open(path, 'wb') as f:
                total_size = int(resp.headers.get("Content-Length", 0))
                downloads_manager[user_id] = {"downloaded": 0}

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
                            filename=video_title,
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

                while True:
                    chunk = await resp.content.read(10 * 1024 * 1024)  # 10MB chunks
                    if not chunk:
                        break
                    await f.write(chunk)
                    downloads_manager[user_id]['downloaded'] += len(chunk)
                    await progress(downloads_manager[user_id]['downloaded'], total_size)

    return path

async def download_video(url, reply_msg, user_mention, user_id, max_retries=3):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details
        api_response = await fetch_json(f"{TERABOX_API_URL}/url?url={url}&token={TERABOX_API_TOKEN}")

        if not api_response or not isinstance(api_response, list) or "filename" not in api_response[0]:
            raise Exception("Invalid API response format.")

        # Extract details from response
        data = api_response[0]
        download_link = data["link"] + f"&random={random.randint(1, 10)}"  # Bypass caching
        video_title = data["filename"]
        file_size = data.get("size", 0)
        thumb_url = data.get("thumbnail", THUMBNAIL)  # Use default thumbnail if missing

        logging.info(f"Downloading: {video_title} | Size: {file_size} bytes")

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

        # Retry logic for robustness
        for attempt in range(1, max_retries + 1):
            try:
                file_path = await asyncio.create_task(download(download_link, user_id, reply_msg, video_title, user_mention))
                break  # Exit loop if successful
            except Exception as e:
                logging.warning(f"Download failed (Attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    raise e  # Raise error if all retries fail
                await asyncio.sleep(3)  # Wait before retrying

        # Send completion message
        await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")
        return file_path, thumb_url, video_title, None  # No duration in response

    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return None, None, None, None


async def upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message):
    try:
        file_size = os.path.getsize(file_path)
        uploaded = 0
        start_time = datetime.now()
        last_update_time = time.time()

        # Default settings
        AUTO_DEL = DEL_TIMER = HIDE_CAPTION = CHNL_BTN = PROTECT_MODE = False
        button_name = button_link = None

        # Fetch configurations from DB
        AUTO_DEL, DEL_TIMER, HIDE_CAPTION, CHNL_BTN, PROTECT_MODE = await asyncio.gather(
            db.get_auto_delete(), db.get_del_timer(), db.get_hide_caption(),
            db.get_channel_button(), db.get_protect_content()
        )

        if CHNL_BTN:
            button_name, button_link = await db.get_channel_button_link()

        async def progress(current, total):
            nonlocal uploaded, last_update_time
            uploaded = current
            percentage = (current / total) * 100
            elapsed_time_seconds = (datetime.now() - start_time).total_seconds()

            if time.time() - last_update_time > 2:
                progress_text = format_progress_bar(
                    filename=video_title,
                    percentage=percentage,
                    done=current,
                    total_size=total,
                    status="Uploading",
                    eta=(total - current) / (current / elapsed_time_seconds) if current > 0 else 0,
                    speed=current / elapsed_time_seconds if current > 0 else 0,
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

        # **Upload video to the database channel**
        with open(file_path, 'rb') as file:
            collection_message = await client.send_video(
                chat_id=db_channel_id,
                video=file,
                caption=f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>",
                thumb=thumbnail_path,
                progress=progress
            )

        # **Copy the video from the DB channel to user (No forward header)**
        copied_msg = await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=db_channel_id,
            message_id=collection_message.id
        )

        # Prepare customized caption & buttons
        original_caption = f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>"
        caption = "" if HIDE_CAPTION else original_caption
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=button_name, url=button_link)]]) if CHNL_BTN else None

        # Edit caption of copied message
        await copied_msg.edit_caption(
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

        # Handle auto-delete
        if AUTO_DEL:
            asyncio.create_task(delete_message(copied_msg, DEL_TIMER))

        # Clean up files and delete messages
        os.remove(file_path)
        if thumbnail_path:
            os.remove(thumbnail_path)

        await message.delete()
        await reply_msg.delete()

        # Send sticker (Optional)
        sticker_message = await message.reply_sticker("CAACAgIAAxkBAAEZdwRmJhCNfFRnXwR_lVKU1L9F3qzbtAAC4gUAAj-VzApzZV-v3phk4DQE")
        await asyncio.sleep(5)
        await sticker_message.delete()

        return collection_message.id

    except Exception as e:
        logging.error(f"Error during upload: {e}", exc_info=True)
        #await reply_msg.reply_text("⚠️ Upload failed. Please try again later.")
        return None
