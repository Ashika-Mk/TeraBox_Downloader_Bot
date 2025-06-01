import requests
import aria2p
from datetime import datetime
from status import format_progress_bar
import asyncio, aiofiles
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
from aiofiles import open as aio_open
import aiohttp, aiofiles
import mmap
from shutil import which
import subprocess
from urllib.parse import urlparse


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




COOKIE = (
"browserid=avLKUlrztrL0C84414VnnfWxLrQ1vJblh4m8WCMxL7TZWIMpPdno52qQb27fk957PE6sUd5VZJ1ATlUe; TSID=DLpCxYPseu0EL2J5S2Hf36yFszAufv2G; ndus=Yd6IpupteHuieos8muZScO1E7xfuRT_csD6LBOF3; csrfToken=mKahcZKmznpDIODk5qQvF1YS; lang=en; __bid_n=1964760716d8bd55e14207; ndut_fmt=B7951F1AB0B1ECA11BDACDA093585A5F0F88DE80879A2413BE32F25A6B71C658;"
)

async def download_video(url, reply_msg, user_mention, user_id, max_retries=5):
    try:
        logging.info(f"Fetching video info: {url}")

        # Step 1: Fetch video metadata
        async with aiohttp.ClientSession() as session:
            api_url = f"https://api-gules-one-93.vercel.app/api/download?url={url}&token=TERAXBOTZ"
            async with session.get(api_url) as response:
                if response.status != 200:
                    raise Exception("Failed to fetch metadata.")
                json_data = await response.json()

        if not json_data.get("success") or not json_data.get("data"):
            raise Exception("API returned invalid structure.")

        downloaded_files = []

        for file_info in json_data["data"]:
            download_link = file_info["direct_link"] + f"&nocache={random.randint(1000, 9999)}"
            video_title = file_info["filename"]
            file_size = int(file_info.get("sizebytes", 0))
            thumb_url = file_info.get("thumb")
            file_path = video_title
            thumb_path = None

            # Step 2: Download thumbnail
            if thumb_url:
                thumb_path = f"{video_title}.jpg"
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(thumb_url) as response:
                            if response.status == 200:
                                async with aiofiles.open(thumb_path, "wb") as f:
                                    await f.write(await response.read())
                            else:
                                thumb_path = None
                except Exception:
                    thumb_path = None

            if file_size == 0:
                raise Exception("Missing file size.")

            parsed = urlparse(download_link)
            cdn_host = parsed.hostname or "www.terabox.com"

            headers = {
                "User-Agent": "netdisk;P2SP;2.2.60.26",
                "Referer": "https://www.terabox.com/",
                "Origin": "https://www.terabox.com",
                "Accept-Encoding": "identity",
                "Connection": "Keep-Alive",
                "Host": cdn_host,
                "Cookie": COOKIE,
            }

            downloaded_size = 0
            start_time = datetime.now()
            last_update_time = time.time()

            for attempt in range(max_retries):
                try:
                    connector = aiohttp.TCPConnector(limit=6, ssl=False, force_close=True)

                    async with aiohttp.ClientSession(connector=connector) as session:
                        async with session.get(download_link, headers=headers, timeout=900) as response:
                            if response.status not in [200, 206]:
                                raise Exception(f"HTTP {response.status} on download.")

                            async with aiofiles.open(file_path, "wb") as f:
                                async for chunk in response.content.iter_chunked(4 * 1024 * 1024):
                                    await f.write(chunk)
                                    downloaded_size += len(chunk)

                                    if time.time() - last_update_time > 2:
                                        percent = min(100, (downloaded_size / file_size) * 100)
                                        elapsed = (datetime.now() - start_time).total_seconds()
                                        speed = downloaded_size / elapsed if elapsed else 0
                                        eta = (file_size - downloaded_size) / speed if speed else 0

                                        progress = format_progress_bar(
                                            filename=video_title,
                                            percentage=percent,
                                            done=downloaded_size,
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
                                            await reply_msg.edit_text(progress)
                                            last_update_time = time.time()
                                        except:
                                            pass

                    logging.info(f"Download complete: {file_path}")
                    await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")
                    downloaded_files.append((file_path, thumb_path, video_title, None))
                    break

                except Exception as e:
                    logging.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                    await asyncio.sleep(2)

            else:
                logging.error(f"All retries failed for: {video_title}")

        return downloaded_files if downloaded_files else None

    except Exception as e:
        logging.error(f"Final Error: {e}", exc_info=True)
        return None

uploads_manager = {}

async def upload_videos(client, files_data, reply_msg, db_channel_id, user_mention, user_id, message):
    """
    Upload multiple files concurrently.

    :param client: Telegram client
    :param files_data: List of tuples [(file_path, thumb_path, video_title), ...]
    :param reply_msg: Message to update progress
    :param db_channel_id: Channel ID to upload files
    :param user_mention: User mention string
    :param user_id: User ID
    :param message: Original user message (for cleanup)
    :return: List of message IDs of uploaded files
    """
    uploads_manager.setdefault(user_id, [])

    async def upload_single_file(file_path, thumb_path, video_title):
        try:
            uploads_manager[user_id].append(file_path)
            file_size = os.path.getsize(file_path)
            uploaded = 0
            start_time = datetime.now()
            last_update_time = time.time()

            AUTO_DEL, DEL_TIMER, HIDE_CAPTION, CHNL_BTN, PROTECT_MODE = await asyncio.gather(
                db.get_auto_delete(), db.get_del_timer(), db.get_hide_caption(),
                db.get_channel_button(), db.get_protect_content()
            )
            button_name, button_link = await db.get_channel_button_link() if CHNL_BTN else (None, None)

            # Thumbnail + duration
            thumbnail_path = thumb_path or f"{file_path}.jpg"
            if not os.path.exists(thumbnail_path):
                thumbnail_path = generate_thumbnail(file_path, thumbnail_path)
            duration = get_video_duration(file_path)

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
                thumb=thumbnail_path if os.path.exists(thumbnail_path) else None,
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
            uploads_manager[user_id].remove(file_path)
            if not uploads_manager[user_id]:
                uploads_manager.pop(user_id)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                if thumb_path and os.path.exists(thumb_path):
                    os.remove(thumb_path)
                await message.delete()
                await reply_msg.delete()
            except Exception as e:
                logging.warning(f"Cleanup error: {e}")

    # Create upload tasks for all files
    upload_tasks = [
        asyncio.create_task(upload_single_file(file_path, thumb_path, video_title))
        for file_path, thumb_path, video_title, _ in files_data
    ]

    # Await all uploads to finish
    results = await asyncio.gather(*upload_tasks)

    return results