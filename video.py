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

async def download_video(url, reply_msg):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://terabox.web.id/url?url={url}&token=rohit95") as response:
                if response.status != 200:
                    raise Exception("Failed to fetch video details.")
                data = await response.json()

        if not isinstance(data, list) or not data:
            raise Exception("Invalid API response format.")

        # Extract details
        video_info = data[0]
        video_title = video_info["filename"]
        download_link = video_info["link"]
        file_size = video_info.get("size", 0)
        thumb_url = video_info.get("thumbnail")

        logging.info(f"Downloading: {video_title} | Size: {file_size} bytes")

        # Sanitize filename
        safe_title = video_title.replace(" ", "_").replace("/", "_").replace("\\", "_")
        file_path = f"{safe_title}"
        thumb_path = None

        # Download thumbnail
        if thumb_url:
            thumb_path = f"{safe_title}.jpg"
            async with session.get(thumb_url) as response:
                if response.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await response.read())
                    logging.info(f"Thumbnail downloaded: {thumb_path}")
                else:
                    thumb_path = None  # Thumbnail download failed

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

        start_time = time.time()
        downloaded_size = 0
        last_update_time = start_time

        async with session.get(download_link) as response:
            if response.status != 200:
                raise Exception(f"Failed to start download. HTTP {response.status}")

            async with aiofiles.open(file_path, "wb") as file:
                async for chunk in response.content.iter_any():
                    await file.write(chunk)
                    downloaded_size += len(chunk)

                    # Update progress every 5 seconds
                    if time.time() - last_update_time > 5:
                        progress = min((downloaded_size / file_size) * 100, 100)
                        speed = downloaded_size / (time.time() - start_time)
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

        logging.info(f"Download complete: {file_path}")

        # Send completion message
        total_time = time.time() - start_time
        speed_str = f"{(file_size / total_time) / (1024 * 1024):.2f} MB/s"
        file_size_str = f"{file_size / (1024 * 1024):.2f} MB"

        await reply_msg.edit_text(
            f"✅ Download Complete!\n📂 {video_title}\n📦 Size: `{file_size_str}`\n🚀 Speed: `{speed_str}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return file_path, thumb_path, video_title, file_size_str, speed_str

    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return None, None, None, None, None

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
