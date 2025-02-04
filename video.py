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



async def download_video(url, reply_msg, user_mention, user_id):
    try:
        logging.info(f"Fetching video info: {url}")

        # Fetch video details
        response = requests.get(f"https://tbox-vids.vercel.app/api?data={url}")
        response.raise_for_status()
        data = response.json()

        if "file_name" not in data or "direct_link" not in data:
            raise Exception("Invalid API response")

        # Extract details
        download_link = data["direct_link"]
        video_title = data["file_name"]
        video_size = data["sizebytes"]
        thumbnail_url = data.get("thumb")
        video_duration = data.get("time", "Unknown")

        logging.info(f"Downloading: {video_title} | Size: {video_size} bytes")

        # Start Aria2 download with headers
        download = await asyncio.to_thread(aria2.add_uris, [download_link], options={
            "header": [
                f"Accept: {headersList['Accept']}",
                f"Accept-Encoding: {headersList['Accept-Encoding']}",
                f"Accept-Language: {headersList['Accept-Language']}",
                f"Connection: {headersList['Connection']}",
                f"Cookie: {headersList['Cookie']}",
                f"DNT: {headersList['DNT']}",
                f"Host: {headersList['Host']}",
                f"Sec-Fetch-Dest: {headersList['Sec-Fetch-Dest']}",
                f"Sec-Fetch-Mode: {headersList['Sec-Fetch-Mode']}",
                f"Sec-Fetch-Site: {headersList['Sec-Fetch-Site']}",
                f"Sec-Fetch-User: {headersList['Sec-Fetch-User']}",
                f"Upgrade-Insecure-Requests: {headersList['Upgrade-Insecure-Requests']}",
                f"User-Agent: {headersList['User-Agent']}",
                f"sec-ch-ua: {headersList['sec-ch-ua']}",
                f"sec-ch-ua-mobile: {headersList['sec-ch-ua-mobile']}",
                f"sec-ch-ua-platform: {headersList['sec-ch-ua-platform']}"
            ]
        })

        start_time = datetime.now()
        last_percentage = 0

        while not download.is_complete:
            download.update()
            percentage = int(download.progress)
            speed = download.download_speed / (1024 * 1024)  # Convert to MB/s
            eta = download.eta
            elapsed_time = (datetime.now() - start_time).total_seconds()

            # Update progress only if percentage has changed significantly
            if percentage >= last_percentage + 2:
                progress_text = (
                    f"📥 **Downloading:** {video_title}\n"
                    f"📊 **Progress:** {percentage}%\n"
                    f"🚀 **Speed:** {speed:.2f} MB/s\n"
                    f"⏳ **ETA:** {eta}s\n"
                    f"⏱ **Elapsed:** {elapsed_time:.2f}s\n"
                )
                await reply_msg.edit_text(progress_text)
                last_percentage = percentage

            await asyncio.sleep(2)  # Faster updates

        if download.is_complete:
            file_path = download.files[0].path
            logging.info(f"Download complete: {file_path}")

            # Download thumbnail
            thumbnail_path = None
            if thumbnail_url:
                thumb_response = requests.get(thumbnail_url)
                thumbnail_path = f"{os.path.splitext(file_path)[0]}_thumb.jpg"
                with open(thumbnail_path, "wb") as thumb_file:
                    thumb_file.write(thumb_response.content)
                logging.info(f"Thumbnail saved: {thumbnail_path}")

            await reply_msg.edit_text(f"✅ **Download Complete!**\n📽️ **Duration:** {video_duration}")
            return file_path, thumbnail_path, video_title, video_duration

    except Exception as e:
        logging.error(f"Error: {e}")
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