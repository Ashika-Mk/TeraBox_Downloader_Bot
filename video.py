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

import urllib.parse
import asyncio
import logging
import time
from datetime import datetime
from collections import defaultdict

#rohit95 old token

TERABOX_API_URL = "https://terabox.web.id"
TERABOX_API_TOKEN = "85ebfdd8-77d5-4725-a3b6-3a03ba188a5c_7328629001"
THUMBNAIL = "https://envs.sh/S-T.jpg"

# Setup logger
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more detailed logs
    format="%(asctime)s [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TeraBoxDownloader")

downloads_manager = {}

# headers
my_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.terabox.com/"
}



# Fetch cookie from environment
cookie_string = "browserid=avLKUlrztrL0C84414VnnfWxLrQ1vJbslh4m8WCMxL7TZWIMpPdno52qQb27fk957PE6sUd5VZJ1ATlUe; TSID=DLpCxYPseu0EL2J5S2Hf36yFszAufv2G; ndus=Yd6IpupteHuieos8muZScO1E7xfuRT_csD6LBOF3; csrfToken=mKahcZKmznpDIODk5qQvF1YS; lang=en; __bid_n=1964760716d8bd55e14207; ndut_fmt=B7951F1AB0B1ECA11BDACDA093585A5F0F88DE80879A2413BE32F25A6B71C658"

# Convert cookie string to dict
cookies_dict = dict(item.strip().split("=", 1) for item in cookie_string.split(";"))


async def find_between(string, start, end):
    start_index = string.find(start) + len(start)
    end_index = string.find(end, start_index)
    return string[start_index:end_index]


async def find_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except IndexError:
        return None

async def fetch_download_link_async(url):
    encoded_url = urllib.parse.quote(url)

    # Create a session with appropriate headers and support for brotli compression
    async with aiohttp.ClientSession(cookies=cookies_dict) as my_session:
        my_session.headers.update(my_headers)


        # Manual fallback as last resort
        try:
            async with my_session.get(url, timeout=30) as response:
                response.raise_for_status()
                response_data = await response.text()

            js_token = await find_between(response_data, 'fn%28%22', '%22%29')
            log_id = await find_between(response_data, 'dp-logid=', '&')

            if not js_token or not log_id:
                logger.error("Required tokens not found.")
                return None

            request_url = str(response.url)
            surl = None

            # Try different methods to extract surl
            if 'surl=' in request_url:
                surl = request_url.split('surl=')[1].split('&')[0]
            elif '/s/' in request_url:
                surl = request_url.split('/s/')[1].split('?')[0]

            if not surl:
                logger.error("Could not extract surl parameter from URL")
                return None

            params = {
                'app_id': '250528',
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'jsToken': js_token,
                'dplogid': log_id,
                'page': '1',
                'num': '20',
                'order': 'time',
                'desc': '1',
                'site_referer': request_url,
                'shorturl': surl,
                'root': '1'
            }

            async with my_session.get('https://www.1024tera.com/share/list', params=params, timeout=30) as response2:
                response_data2 = await response2.json()
                if 'list' not in response_data2:
                    logger.error("No list found in response.")
                    return None

                if response_data2['list'][0]['isdir'] == "1":
                    params.update({
                        'dir': response_data2['list'][0]['path'],
                        'order': 'asc',
                        'by': 'name',
                        'dplogid': log_id
                    })
                    params.pop('desc')
                    params.pop('root')

                    async with my_session.get('https://www.1024tera.com/share/list', params=params, timeout=30) as response3:
                        response_data3 = await response3.json()
                        if 'list' not in response_data3:
                            logger.error("No list found in nested directory response.")
                            return None
                        logger.info("Using file list from manual fallback (nested directory)")
                        return response_data3['list']

                logger.info("Using file list from manual fallback")
                return response_data2['list']

        except Exception as e:
            import traceback
            error_details = repr(e) if str(e) == "" else str(e)
            logger.error(f"Final fallback failed: {error_details}")
            logger.debug(f"Error traceback: {traceback.format_exc()}")
            return None



async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def download(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int) -> str:
    sanitized_filename = filename.replace("/", "_").replace("\\", "_")
    file_path = os.path.join(os.getcwd(), sanitized_filename)

    download_key = f"{user_id}-{sanitized_filename}"  # Unique key per file
    downloads_manager[download_key] = {"downloaded": 0}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=900)) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch video: HTTP {resp.status}")

            total_size = int(resp.headers.get("Content-Length", 0)) or file_size
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
                    chunk = await resp.content.read(10 * 1024 * 1024)  # 10MB chunks
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


async def download_video(url, reply_msg, user_mention, user_id, client, db_channel_id, message, max_retries=3):
    try:
        logging.info(f"Fetching download list via fallback: {url}")

        file_list = await fetch_download_link_async(url)

        if not file_list or not isinstance(file_list, list) or 'dlink' not in file_list[0]:
            raise Exception("No downloadable file found or invalid format.")

        # Pick the first file
        file = file_list[0]
        download_link = file.get('dlink') or file.get('downloadlink') or None
        video_title = file.get('server_filename') or file.get('filename') or "video.mp4"
        file_size = int(file.get('size', 0))
        thumb_url = THUMBNAIL  # Static or generate based on file type

        if not download_link or file_size == 0:
            raise Exception("Missing download link or file size.")

        for attempt in range(1, max_retries + 1):
            try:
                file_path = await asyncio.create_task(
                    download(download_link, user_id, video_title, reply_msg, user_mention, file_size)
                )
                break
            except Exception as e:
                logging.warning(f"Download failed (Attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    raise e
                await asyncio.sleep(3)

        await reply_msg.edit_text(f"✅ Download Complete!\n📂 {video_title}")
        return file_path, thumb_url, video_title, None

    except Exception as e:
        logging.error(f"Error in download_video: {e}", exc_info=True)
        return None, None, None, None


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

uploads_manager = {}

async def upload_video(client, file_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message):
    try:
        # Create the background task to handle upload
        uploads_manager.setdefault(user_id, []).append(file_path)

        file_size = os.path.getsize(file_path)
        uploaded = 0
        start_time = datetime.now()
        last_update_time = time.time()

        # Fetch config options
        AUTO_DEL, DEL_TIMER, HIDE_CAPTION, CHNL_BTN, PROTECT_MODE = await asyncio.gather(
            db.get_auto_delete(), db.get_del_timer(), db.get_hide_caption(),
            db.get_channel_button(), db.get_protect_content()
        )
        button_name, button_link = await db.get_channel_button_link() if CHNL_BTN else (None, None)

        # Thumbnail + duration
        thumbnail_path = f"{file_path}.jpg"
        thumbnail_path = generate_thumbnail(file_path, thumbnail_path)
        duration = get_video_duration(file_path)

        # Progress function
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
        # Clean up
        uploads_manager[user_id].remove(file_path)
        if not uploads_manager[user_id]:
            uploads_manager.pop(user_id)

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(f"{file_path}.jpg"):
                os.remove(f"{file_path}.jpg")
            await message.delete()
            await reply_msg.delete()
        except Exception as e:
            logging.warning(f"Cleanup error: {e}")