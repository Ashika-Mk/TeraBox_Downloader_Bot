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
import aiohttp
import mmap
from shutil import which
import subprocess

async def download_video(url, reply_msg, user_mention, user_id, chunk_size=50 * 1024 * 1024, max_workers=8):
    try:
        logging.info(f"Fetching video info: {url}")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.get(f"https://tbox-vids.vercel.app/api?data={url}") as response:
                data = await response.json()

        if "file_name" not in data or "direct_link" not in data:
            raise Exception("Invalid API response format.")

        # Extract details
        download_link = data["direct_link"]
        video_title = data["file_name"]
        file_size = data.get("sizebytes", 0)
        thumb_url = data.get("thumb")
        download_link += f"&random={random.randint(1, 10)}"

        logging.info(f"Downloading: {video_title} | Size: {file_size} bytes")

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.terabox.com/",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }

        file_path = video_title
        thumb_path = None

        # Download thumbnail
        if thumb_url:
            thumb_path = f"{video_title}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(thumb_url) as response:
                    if response.status == 200:
                        async with aio_open(thumb_path, "wb") as f:
                            await f.write(await response.read())
                    else:
                        thumb_path = None

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

        # Use aria2c if available
        if which("aria2c"):
            logging.info("Using aria2c for faster download.")
            aria_cmd = [
                "aria2c",
                "-x16", "-s16",  # 16 parallel connections
                "-k1M",  # 1MB chunk size
                "-o", file_path,
                download_link
            ]
            process = await asyncio.create_subprocess_exec(*aria_cmd)
            await process.communicate()

            if process.returncode == 0:
                logging.info(f"Download complete: {file_path}")
                await reply_msg.edit_text(f"✅ **Download Complete!**\n📂 {video_title}")
                return file_path, thumb_path, video_title, None

        # Fallback to manual chunked download
        downloaded_size = 0
        last_update_time = time.time()
        last_downloaded = 0
        semaphore = asyncio.Semaphore(max_workers)

        async def download_chunk(start, end, part_num):
            nonlocal downloaded_size, last_update_time, last_downloaded
            async with semaphore:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                    async with session.get(download_link, headers={**headers, "Range": f"bytes={start}-{end}"}) as response:
                        part_filename = f"{file_path}.part{part_num}"
                        async with aio_open(part_filename, "wb") as f:
                            async for chunk in response.content.iter_any():
                                await f.write(chunk)
                                downloaded_size += len(chunk)
                                last_downloaded += len(chunk)

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

        chunk_tasks = []
        chunk_size = min(chunk_size, file_size // max_workers)
        num_parts = 0

        for i in range(0, file_size, chunk_size):
            chunk_tasks.append(download_chunk(i, min(i + chunk_size - 1, file_size - 1), num_parts))
            num_parts += 1

        await asyncio.gather(*chunk_tasks)

        # Merge chunks with mmap
        chunk_files = sorted([f"{file_path}.part{i}" for i in range(num_parts)], key=lambda x: int(x.split("part")[-1]))

        with open(file_path, "wb") as final_file:
            with mmap.mmap(final_file.fileno(), 0, access=mmap.ACCESS_WRITE) as mm:
                for part_path in chunk_files:
                    with open(part_path, "rb") as part_file:
                        mm.write(part_file.read())
                    os.remove(part_path)

        logging.info(f"Download complete: {file_path}")
        await reply_msg.edit_text(f"✅ **Download Complete!**\n📂 {video_title}")

        return file_path, thumb_path, video_title, None

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