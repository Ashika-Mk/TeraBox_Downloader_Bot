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
#from urllib.parse import urlparse
import urllib.parse



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


import requests
import math
from pathlib import Path
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor

TERABOX_COOKIES = "browserid=cLNycJqGL6eOGpkhz9CtW3sG7CS89UeNe0Ycq2Ainq-UD9VlRDZiyB8tBaI=; lang=en; TSID=7neW7n6LXenkJEV0l9xwoXc87YgeObNR; __bid_n=1971ea13b40eefcf4f4207; _ga=GA1.1.113339747.1748565576; ndus=YvZErXkpeHui6z7tOvOuDPvaDsYiQOZosuA0eNJq; csrfToken=7rbF54M2IP5Hy8dh_ZCHGIFY"


downloads_manager = {}

# Replace the TeraBox scraping functions with API calls to your VPS
SCRAPER_API_URL = "http://128.199.108.75:5000/terabox/fetch"

def truncate_filename(filename, max_length=40):
    """
    Replace 'getnewlink' patterns with '@NyxKingS', otherwise keep filename unchanged.
    """
    import re

    # Only replace if filename contains getnewlink patterns
    if any(pattern in filename.lower() for pattern in ['getnewlink', 'getnewlink.com', '@getnewlink']):
        # Replace getnewlink patterns with @NyxKingS
        filename = re.sub(r'(@)?getnewlink(\.com)?', '@Codeflix_Bots ', filename, flags=re.IGNORECASE)

    # Return the filename as-is (either modified or original)
    return filename

async def fetch_json_from_api(url: str) -> dict:
    """Fetch data from your VPS scraper API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{SCRAPER_API_URL}?url={url}",
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"API returned status {resp.status}")
                return await resp.json()
    except Exception as e:
        logging.error(f"Error fetching from scraper API: {e}")
        raise

async def process_shared_content(share_url):
    """Process TeraBox shared content using your VPS API"""
    try:
        logging.info(f"Fetching data from scraper API for: {share_url}")

        api_response = await fetch_json_from_api(share_url)

        if api_response.get("status") != "success":
            raise Exception(f"API error: {api_response.get('message', 'Unknown error')}")

        files = api_response.get("files", [])

        if not files:
            raise Exception("No files found in API response")

        # Convert API response format to match expected format
        processed_content = []
        for file_data in files:
            raw_filename = file_data.get("file_name", "unnamed_file")
            cleaned_filename = truncate_filename(raw_filename)

            processed_content.append({
                "file_name": cleaned_filename,
                "path": file_data.get("path"),
                "size": file_data.get("size"),
                "size_bytes": file_data.get("size_bytes"),
                "download_url": file_data.get("download_url"),
                "modify_time": file_data.get("modify_time"),
                "thumbnails": file_data.get("thumbnails", {})
            })

        logging.info(f"Successfully fetched {len(processed_content)} files from API")
        return processed_content

    except Exception as e:
        logging.error(f"Failed to process shared content via API for {share_url}: {e}")
        return []



async def download_parallel(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int, num_chunks: int = 4) -> str:
    """Download file using parallel chunks for maximum speed"""
    sanitized_filename = filename.replace("/", "_").replace("\\", "_").replace(":", "_").replace("?", "_").replace("*", "_").replace("|", "_").replace("<", "_").replace(">", "_").replace('"', "_")
    file_path = os.path.join(os.getcwd(), sanitized_filename)

    download_key = f"{user_id}-{sanitized_filename}"
    downloads_manager[download_key] = {"downloaded": 0, "chunks": {}}

    # Check if server supports range requests
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.terabox.com/'
    }

    # Test for range support
    async with aiohttp.ClientSession() as session:
        async with session.head(url, headers=headers) as resp:
            if resp.status != 200:
                # Fallback to single-threaded download
                return await download_single(url, user_id, filename, reply_msg, user_mention, file_size)

            accept_ranges = resp.headers.get('Accept-Ranges', '').lower()
            content_length = int(resp.headers.get('Content-Length', 0)) or file_size

            if accept_ranges != 'bytes' or content_length < 50 * 1024 * 1024:  # Less than 50MB
                # Fallback to single-threaded for small files or no range support
                return await download_single(url, user_id, filename, reply_msg, user_mention, file_size)

    # Calculate chunk sizes for parallel download
    chunk_size = content_length // num_chunks
    ranges = []

    for i in range(num_chunks):
        start = i * chunk_size
        end = start + chunk_size - 1 if i < num_chunks - 1 else content_length - 1
        ranges.append((start, end))

    logging.info(f"Starting parallel download with {num_chunks} chunks: {filename}")

    start_time = datetime.now()
    last_update_time = time.time()

    async def download_chunk(chunk_id: int, start: int, end: int):
        """Download a specific chunk of the file"""
        chunk_headers = headers.copy()
        chunk_headers['Range'] = f'bytes={start}-{end}'

        connector = aiohttp.TCPConnector(
            limit=200,
            limit_per_host=50,
            ttl_dns_cache=1800,
            use_dns_cache=True,
            keepalive_timeout=600,
            ssl=False
        )

        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=600)

        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(url, headers=chunk_headers) as resp:
                        if resp.status not in [200, 206]:
                            raise Exception(f"Chunk {chunk_id} HTTP {resp.status}")

                        chunk_data = bytearray()
                        async for data in resp.content.iter_chunked(1024 * 1024):  # 1MB read chunks
                            chunk_data.extend(data)
                            downloads_manager[download_key]['chunks'][chunk_id] = len(chunk_data)

                        return chunk_id, bytes(chunk_data)

            except Exception as e:
                logging.warning(f"Chunk {chunk_id} attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    raise e

    async def progress_updater():
        """Update progress while chunks are downloading"""
        nonlocal last_update_time
        while download_key in downloads_manager:
            try:
                if time.time() - last_update_time > 1:  # Update every second
                    total_downloaded = sum(downloads_manager[download_key]['chunks'].values())
                    percentage = (total_downloaded / content_length) * 100
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = total_downloaded / elapsed if elapsed > 0 else 0
                    eta = (content_length - total_downloaded) / speed if speed > 0 else 0

                    progress_text = format_progress_bar(
                        filename=filename, percentage=percentage, done=total_downloaded,
                        total_size=content_length, status="Dᴏᴡɴʟᴏᴀᴅɪɴɢ.. (Parallel)", eta=eta,
                        speed=speed, elapsed=elapsed, user_mention=user_mention,
                        user_id=user_id, aria2p_gid=""
                    )
                    try:
                        await reply_msg.edit_text(progress_text)
                        last_update_time = time.time()
                    except:
                        pass

                await asyncio.sleep(0.5)
            except:
                break

    try:
        # Start progress updater
        progress_task = asyncio.create_task(progress_updater())

        # Download all chunks in parallel
        chunk_tasks = [
            download_chunk(i, start, end) 
            for i, (start, end) in enumerate(ranges)
        ]

        chunk_results = await asyncio.gather(*chunk_tasks)

        # Stop progress updater
        progress_task.cancel()

        # Sort chunks by ID and write to file
        chunk_results.sort(key=lambda x: x[0])

        async with aiofiles.open(file_path, 'wb') as f:
            for chunk_id, chunk_data in chunk_results:
                await f.write(chunk_data)

        downloads_manager.pop(download_key, None)
        logging.info(f"Parallel download completed: {filename}")
        return file_path

    except Exception as e:
        logging.error(f"Parallel download failed: {e}")
        # Cleanup partial file
        if os.path.exists(file_path):
            os.remove(file_path)
        downloads_manager.pop(download_key, None)
        raise e

async def download_single(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int) -> str:
    """Fallback single-threaded download"""
    sanitized_filename = filename.replace("/", "_").replace("\\", "_").replace(":", "_").replace("?", "_").replace("*", "_").replace("|", "_").replace("<", "_").replace(">", "_").replace('"', "_")
    file_path = os.path.join(os.getcwd(), sanitized_filename)

    download_key = f"{user_id}-{sanitized_filename}"
    downloads_manager[download_key] = {"downloaded": 0}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.terabox.com/'
    }

    connector = aiohttp.TCPConnector(
        limit=100, limit_per_host=20, ttl_dns_cache=1800,
        use_dns_cache=True, keepalive_timeout=600, ssl=False
    )

    timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=600)

    async with aiohttp.ClientSession(connector=connector, headers=headers, timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status not in [200, 206]:
                raise Exception(f"HTTP {resp.status}")

            total_size = int(resp.headers.get("Content-Length", 0)) or file_size
            start_time = datetime.now()
            last_update_time = time.time()

            async def progress(current, total):
                nonlocal last_update_time
                if time.time() - last_update_time > 1:
                    percentage = (current / total) * 100 if total else 0
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0

                    progress_text = format_progress_bar(
                        filename=filename, percentage=percentage, done=current,
                        total_size=total, status="Downloading", eta=eta,
                        speed=speed, elapsed=elapsed, user_mention=user_mention,
                        user_id=user_id, aria2p_gid=""
                    )
                    try:
                        if reply_msg:
                            await reply_msg.edit_text(progress_text)
                        last_update_time = time.time()
                    except:
                        pass

            async with aiofiles.open(file_path, 'wb') as f:
                chunk_size = 50 * 1024 * 1024  # 50MB chunks

                async for chunk in resp.content.iter_chunked(chunk_size):
                    if not chunk:
                        break
                    await f.write(chunk)
                    downloads_manager[download_key]['downloaded'] += len(chunk)
                    await progress(downloads_manager[download_key]['downloaded'], total_size)

    downloads_manager.pop(download_key, None)
    return file_path

# Update the main download function to use parallel downloading
async def download(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int) -> str:
    """Main download function with parallel support"""
    try:
        # Try parallel download first for large files
        if file_size > 100 * 1024 * 1024:  # Files larger than 100MB
            return await download_parallel(url, user_id, filename, reply_msg, user_mention, file_size, num_chunks=8)
        else:
            return await download_single(url, user_id, filename, reply_msg, user_mention, file_size)
    except Exception as e:
        logging.warning(f"Parallel download failed, falling back to single-threaded: {e}")
        return await download_single(url, user_id, filename, reply_msg, user_mention, file_size)



def format_size(size_bytes):
    """Format file size in human readable format"""
    try:
        size_bytes = int(size_bytes)
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
        elif size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes} bytes"
    except (ValueError, TypeError):
        return "Unknown size"


async def download(url: str, user_id: int, filename: str, reply_msg, user_mention, file_size: int) -> str:
    sanitized_filename = filename.replace("/", "_").replace("\\", "_").replace(":", "_").replace("?", "_").replace("*", "_").replace("|", "_").replace("<", "_").replace(">", "_").replace('"', "_")
    file_path = os.path.join(os.getcwd(), sanitized_filename)

    download_key = f"{user_id}-{sanitized_filename}"
    downloads_manager[download_key] = {"downloaded": 0}

    # Production headers with rotation
    headers_list = [
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.terabox.com/',
            'Cookie': TERABOX_COOKIES
        },
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://dm.1024tera.com/',
            'Cookie': TERABOX_COOKIES
        }
    ]

    # Production connector with conservative settings
    connector = aiohttp.TCPConnector(
        limit=150,
        limit_per_host=110,
        ttl_dns_cache=3600,
        use_dns_cache=True,
        keepalive_timeout=900,
        enable_cleanup_closed=True,
        ssl=False
    )

    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=60,
        sock_read=300
    )

    for attempt in range(3):
        try:
            headers = random.choice(headers_list)

            async with aiohttp.ClientSession(
                connector=connector, 
                headers=headers, 
                timeout=timeout
            ) as session:
                async with session.get(url) as resp:
                    if resp.status not in [200, 206]:
                        raise Exception(f"HTTP {resp.status}")

                    total_size = int(resp.headers.get("Content-Length", 0)) or file_size
                    start_time = datetime.now()
                    last_update_time = time.time()

                    async def progress(current, total):
                        nonlocal last_update_time
                        if time.time() - last_update_time > 3:  # Reduce update frequency for production
                            percentage = (current / total) * 100 if total else 0
                            elapsed = (datetime.now() - start_time).total_seconds()
                            speed = current / elapsed if elapsed > 0 else 0
                            eta = (total - current) / speed if speed > 0 else 0

                            progress_text = format_progress_bar(
                                filename=filename, percentage=percentage, done=current,
                                total_size=total, status="Dᴏᴡɴʟᴏᴀᴅɪɴɢ..", eta=eta,
                                speed=speed, elapsed=elapsed, user_mention=user_mention,
                                user_id=user_id, aria2p_gid=""
                            )
                            try:
                                await reply_msg.edit_text(progress_text)
                                last_update_time = time.time()
                            except:
                                pass

                    async with aiofiles.open(file_path, 'wb') as f:
                        chunk_size = 10 * 1024 * 1024  # Smaller chunks for production stability

                        async for chunk in resp.content.iter_chunked(chunk_size):
                            if not chunk:
                                break
                            await f.write(chunk)
                            downloads_manager[download_key]['downloaded'] += len(chunk)
                            await progress(downloads_manager[download_key]['downloaded'], total_size)

            downloads_manager.pop(download_key, None)
            return file_path

        except Exception as e:
            logging.warning(f"Download attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(5)
            else:
                raise e

async def download_video(url, reply_msg, user_mention, user_id, client, db_channel_id, message, max_retries=3):
    try:
        logging.info(f"Starting TeraBox scraping for: {url}")

        # Use direct scraping instead of API
        files = await process_shared_content(url)

        if not files:
            raise Exception("No files found or failed to scrape TeraBox content.")

        # Pick the first file for now (you can expand to all later if needed)
        file_data = files[0]
        download_link = file_data["download_url"]
        video_title = file_data["file_name"]
        file_size = int(file_data["size_bytes"])
        thumb_url = file_data["thumbnails"].get("url3", "") if file_data["thumbnails"] else ""

        if file_size == 0:
            raise Exception("Failed to get file size, download aborted.")

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

        await reply_msg.edit_text(f"✅ Dᴏᴡɴʟᴏᴀᴅ Cᴏᴍᴘʟᴇᴛᴇ..!\n📂 {video_title}")

        # Return a list of 3-tuples, even if just one file
        return [(file_path, thumb_url, video_title)]

    except Exception as e:
        logging.error(f"Error in download_video: {e}", exc_info=True)
        await reply_msg.edit_text(f"❌ Error: {str(e)}")
        return []

#------###$$

uploads_manager = {}

async def upload_videos(client, files_data, reply_msg, db_channel_id, user_mention, user_id, message):
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

    # ✅ Correct unpacking here
    upload_tasks = [
        asyncio.create_task(upload_single_file(file_path, thumb_path, video_title))
        for file_path, thumb_path, video_title in files_data
    ]

    results = await asyncio.gather(*upload_tasks)
    return results