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

async def download_video(url, reply_msg, user_mention, user_id, chunk_size=50 * 1024 * 1024, max_workers=8):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(f"https://tbox-vids.vercel.app/api?data={url}")
            response.raise_for_status()
            data = response.json()

        if "file_name" not in data or "direct_link" not in data:
            raise Exception("Invalid API response format.")

        # Extract details
        download_link = data["direct_link"]
        video_title = data["file_name"]
        file_size = data.get("sizebytes", 0)
        thumb_url = data.get("thumb")
        video_duration = data.get("duration", None)  # Extract duration if available

        # Add a random query parameter to bypass caching
        download_link += f"&random={random.randint(1, 10)}"

        logging.info(f"Downloading: {video_title} | Size: {file_size} bytes")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://www.terabox.com/",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }

        file_path = video_title
        thumb_path = None

        # Download thumbnail if available
        if thumb_url:
            thumb_path = f"{video_title}.jpg"
            async with httpx.AsyncClient() as client:
                response = await client.get(thumb_url)
                if response.status_code == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(response.content)
                else:
                    thumb_path = None  # Thumbnail download failed

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

        # First attempt: Use aria2c for high-speed download
        aria2_file_path = f"{file_path}.aria2"
        aria2_cmd = [
            "aria2c", "--continue=true", "--max-connection-per-server=16", "--split=16",
            "--min-split-size=10M", "--file-allocation=none", "--dir=.", "--out", file_path, download_link
        ]

        logging.info(f"Starting download with aria2c: {file_path}")
        process = await asyncio.create_subprocess_exec(*aria2_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()

        # Check if aria2c succeeded
        if process.returncode == 0 and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            logging.info(f"Aria2c download complete: {file_path}")
        else:
            logging.warning(f"Aria2c failed or empty file: {stderr.decode()}")

            # Fall back to aiohttp streaming
            downloaded_size = 0
            last_update_time = time.time()
            last_downloaded = 0
            semaphore = asyncio.Semaphore(max_workers)

            async def download_chunk(start, end, part_num):
                nonlocal downloaded_size, last_update_time, last_downloaded

                async with semaphore:
                    async with aiohttp.ClientSession() as session:
                        headers["Range"] = f"bytes={start}-{end}"
                        async with session.get(download_link, headers=headers) as response:
                            if response.status != 206 and response.status != 200:
                                raise Exception(f"HTTP Error {response.status} for chunk {part_num}")

                            part_filename = f"{file_path}.part{part_num}"
                            async with aiofiles.open(part_filename, "wb") as f:
                                async for chunk in response.content.iter_chunked(1024 * 512):
                                    await f.write(chunk)
                                    downloaded_size += len(chunk)
                                    last_downloaded += len(chunk)

                                    # Update progress every 5 seconds
                                    if time.time() - last_update_time > 5:
                                        speed = last_downloaded / (time.time() - last_update_time)
                                        eta = (file_size - downloaded_size) / speed if speed > 0 else 0

                                        speed_str = f"{speed / (1024 * 1024):.2f} MB/s"
                                        eta_str = time.strftime("%M:%S", time.gmtime(eta))

                                        await reply_msg.edit_text(
                                            f"📥 **Downloading:** {video_title}\n"
                                            f"📊 Progress: `{(downloaded_size / file_size) * 100:.2f}%`\n"
                                            f"🚀 Speed: `{speed_str}`\n"
                                            f"⏳ ETA: `{eta_str}`",
                                            parse_mode=ParseMode.MARKDOWN
                                        )
                                        last_update_time = time.time()
                                        last_downloaded = 0

            # Create chunk download tasks
            chunk_tasks = []
            chunk_size = min(chunk_size, file_size // max_workers)
            num_parts = 0

            for i in range(0, file_size, chunk_size):
                start = i
                end = min(i + chunk_size - 1, file_size - 1)
                chunk_tasks.append(download_chunk(start, end, num_parts))
                num_parts += 1

            # Download all chunks concurrently
            await asyncio.gather(*chunk_tasks)

            # Merge chunks
            async with aiofiles.open(file_path, "wb") as final_file:
                for i in range(num_parts):
                    part_path = f"{file_path}.part{i}"
                    async with aiofiles.open(part_path, "rb") as part_file:
                        await final_file.write(await part_file.read())
                    os.remove(part_path)

        # Final file integrity check
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise Exception("Download failed: File is empty after retries.")

        logging.info(f"Download complete: {file_path}")

        # Send completion message
        await reply_msg.edit_text(f"✅ **Download Complete!**\n📂 {video_title}")

        return file_path, thumb_path, video_title, video_duration

    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        await reply_msg.reply_text(
            "⚠️ Download failed. Try again or use the manual link below.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Download Manually", url=url)]])
        )
        return None, None, None, None


async def upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message):
    file_size = os.path.getsize(file_path)
    uploaded = 0
    start_time = datetime.now()
    last_update_time = time.time()

    # Default initialization
    AUTO_DEL = False
    DEL_TIMER = 0
    HIDE_CAPTION = False
    CHNL_BTN = None
    PROTECT_MODE = False

    # Fetch configurations for auto-delete and other settings
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

    with open(file_path, 'rb') as file:
        # Upload the video to the database channel
        collection_message = await client.send_video(
            chat_id=db_channel_id,
            video=file,
            caption=f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>",
            thumb=thumbnail_path,
            progress=progress
        )

        # Prepare customized caption and buttons for the user's chat
        original_caption = f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 <b>ʙʏ @Javpostr </b>"
        caption = f"{original_caption}" if HIDE_CAPTION else original_caption

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=button_name, url=button_link)]]
        ) if CHNL_BTN else None

        # Send the uploaded video to the user's chat
        copied_msg = await client.send_video(
            chat_id=message.chat.id,
            video=open(file_path, 'rb'),
            caption=caption,
            parse_mode=ParseMode.HTML,
            thumb=thumbnail_path,
            reply_markup=reply_markup,
            protect_content=PROTECT_MODE
        )

        # Handle auto-delete for the user's chat
        if AUTO_DEL:
            asyncio.create_task(delete_message(copied_msg, DEL_TIMER))

        await message.delete()

    await reply_msg.delete()
    sticker_message = await message.reply_sticker("CAACAgIAAxkBAAEZdwRmJhCNfFRnXwR_lVKU1L9F3qzbtAAC4gUAAj-VzApzZV-v3phk4DQE")
    os.remove(file_path)
    os.remove(thumbnail_path)
    await asyncio.sleep(5)
    await sticker_message.delete()
    return collection_message.id