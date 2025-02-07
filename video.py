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
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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


async def download_video(url, reply_msg, user_mention, user_id):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details with retry logic
        for attempt in range(3):  # Retry up to 3 times
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(f"https://tbox-vids.vercel.app/api?data={url}")
                    response.raise_for_status()
                    data = response.json()
                break  # Exit loop if request is successful
            except httpx.ReadTimeout:
                logging.warning(f"Attempt {attempt + 1}: API request timed out. Retrying...")
                await asyncio.sleep(5)  # Wait before retrying
        else:
            raise Exception("API request failed after multiple attempts.")

        # Validate API response
        if "file_name" not in data or "direct_link" not in data:
            raise Exception("Invalid API response format.")

        # Extract details
        download_link = data["direct_link"]
        video_title = data["file_name"]
        video_size = data.get("sizebytes", 0)
        thumbnail_url = data.get("thumb")
        video_duration = data.get("time", "Unknown")

        logging.info(f"Downloading: {video_title} | Size: {video_size} bytes")

        headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.terabox.com/",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Cookie": "PANWEB=1;browserid=DbGhIfUwCmz5pRL9tNJXj71VLCdZrMpJCpPmKGukZJeoKTWs9RGbALdghHUX9LKmR2YNgbW3uYThf_Qx; lang=en; TSID=fe2VGbjvZZ8mG6VoBnSOKa9tzuKhVwfm; __bid_n=194d786a6d8a0663344207; _ga=GA1.1.1902279557.1738782858; _gcl_au=1.1.955760083.1738782878; _fbp=fb.1.1738782878094.854442062512751170; _ga_RSNVN63CM3=GS1.1.1738782878.1.0.1738782882.56.0.0; csrfToken=rrRaANB6emff_Cw1hA9R3JY5; __stripe_mid=7ed47557-32aa-4096-ba79-c391f754e8b547445a;"
}

        file_path = f"{video_title}"

        # Start video download with retry logic
        for attempt in range(3):  # Retry up to 3 times
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    with open(file_path, "wb") as f:
                        async with client.stream("GET", download_link, headers=headers) as response:
                            response.raise_for_status()
                            total_size = int(response.headers.get("content-length", 0))
                            downloaded = 0
                            start_time = datetime.now()
                            last_percentage = 0

                            async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                                f.write(chunk)
                                downloaded += len(chunk)

                                # Progress Update
                                percentage = int((downloaded / total_size) * 100) if total_size else 0
                                elapsed_time = (datetime.now() - start_time).total_seconds()
                                speed = (downloaded / (1024 * 1024)) / elapsed_time if elapsed_time > 0 else 0

                                if percentage >= last_percentage + 2:
                                    progress_text = (
                                        f"📥 **Downloading:** {video_title}\n"
                                        f"📊 **Progress:** {percentage}%\n"
                                        f"🚀 **Speed:** {speed:.2f} MB/s\n"
                                        f"⏳ **Elapsed:** {elapsed_time:.2f}s\n"
                                    )
                                    await reply_msg.edit_text(progress_text)
                                    last_percentage = percentage
                break  # Exit loop if download is successful
            except httpx.ReadTimeout:
                logging.warning(f"Attempt {attempt + 1}: Download request timed out. Retrying...")
                await asyncio.sleep(5)  # Wait before retrying
        else:
            raise Exception("Video download failed after multiple attempts.")

        logging.info(f"Download complete: {file_path}")

        # Download thumbnail if available
        thumbnail_path = None
        if thumbnail_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    thumb_response = await client.get(thumbnail_url)
                    thumb_response.raise_for_status()
                    thumbnail_path = f"{os.path.splitext(file_path)[0]}_thumb.jpg"
                    with open(thumbnail_path, "wb") as thumb_file:
                        thumb_file.write(thumb_response.content)
                logging.info(f"Thumbnail saved: {thumbnail_path}")
            except httpx.HTTPError as e:
                logging.warning(f"Failed to download thumbnail: {e}")

        await reply_msg.edit_text(f"✅ **Download Complete!**\n📽️ **Duration:** {video_duration}")
        return file_path, thumbnail_path, video_title, video_duration

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
            caption=f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 ᴜsᴇʀ ʟɪɴᴋ: tg://user?id={user_id}",
            thumb=thumbnail_path,
            progress=progress
        )

        # Prepare customized caption and buttons for the user's chat
        original_caption = f"✨ {video_title}\n👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : {user_mention}\n📥 ᴜsᴇʀ ʟɪɴᴋ: tg://user?id={user_id}"
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