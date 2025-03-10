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

async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()


COOKIES = await fetch_json("https://terabox.web.id/gc?token=rohit95")

async def download_video(url, reply_msg, user_mention, user_id, max_retries=5):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://terabox.web.id/url?url={url}&token=rohit95") as response:
                if response.status != 200:
                    raise Exception("Failed to fetch video details.")
                api_response = await response.json()

        if not api_response or not isinstance(api_response, list) or "filename" not in api_response[0]:
            raise Exception("Invalid API response format.")

        # Extract details from the response
        data = api_response[0]
        download_link = data["link"]
        video_title = data["filename"]
        file_size = data.get("size", 0)
        thumb_url = data.get("thumbnail")

        # Add a random query parameter to bypass caching
        download_link += f"&random={random.randint(1, 10)}"

        logging.info(f"Downloading: {video_title} | Size: {file_size} bytes")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://www.terabox.com/",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Cookie": COOKIES
        }

        file_path = video_title
        thumb_path = None

        # Download thumbnail if available
        if thumb_url:
            thumb_path = f"{video_title}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(thumb_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(thumb_path, "wb") as f:
                            await f.write(await response.read())
                    else:
                        thumb_path = None  # Thumbnail download failed

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

        downloaded_size = 0
        last_update_time = time.time()
        last_downloaded = 0
        start_time = time.time()

        # **Use TCP Connector for better performance**
        connector = aiohttp.TCPConnector(limit=8, force_close=True)

        # **Retry Mechanism**
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(download_link, headers=headers, timeout=900) as response:
                        if response.status not in [200, 206]:
                            raise Exception(f"Failed to start download. HTTP {response.status}")

                        async with aiofiles.open(file_path, "wb") as file:
                            async for chunk in response.content.iter_chunked(5 * 1024 * 1024):  # 5 MB chunks
                                await file.write(chunk)
                                downloaded_size += len(chunk)
                                last_downloaded += len(chunk)

                                # Update progress every 5 seconds
                                if time.time() - last_update_time > 5:
                                    progress = min((downloaded_size / file_size) * 100, 100)  # Ensure max 100%
                                    speed = last_downloaded / (time.time() - last_update_time)
                                    eta = (file_size - downloaded_size) / speed if speed > 0 else 0

                                    speed_str = f"{speed / (1024 * 1024):.2f} MB/s"
                                    eta_str = time.strftime("%M:%S", time.gmtime(eta))
                                    file_size_str = f"{file_size / (1024 * 1024):.2f} MB"

                                    await reply_msg.edit_text(
                                        f"📥 Downloading: {video_title}\n"
                                        f"📊 Progress: `{progress:.2f}%`\n"
                                        f"📦 File Size: `{file_size_str}`\n"
                                        f"🚀 Speed: `{speed_str}`\n"
                                        f"⏳ ETA: `{eta_str}`",
                                        parse_mode=ParseMode.MARKDOWN
                                    )
                                    last_update_time = time.time()
                                    last_downloaded = 0

                logging.info(f"Download complete: {file_path}")

                # Send completion message
                await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")
                return file_path, thumb_path, video_title, None  # No duration in response

            except Exception as e:
                logging.warning(f"Download failed (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)  # Wait before retrying
                else:
                    raise  # Raise error if all retries fail

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
