# Don't remove This Line From Here. Tg: @rohit_1888 | @Javpostr
from status import format_progress_bar
from video import download_video, upload_video
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
from plugins.query import *
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid
from datetime import datetime, timedelta
from pytz import timezone

db_channel_id=CHANNEL_ID

@Bot.on_message(filters.private & is_admin & ~filters.command([
    'start', 'users', 'broadcast', 'stats', 'addpaid', 'removepaid', 'listpaid',
    'help', 'add_fsub', 'fsub_chnl', 'restart', 'del_fsub', 'add_admins', 'del_admins', 
    'admin_list', 'cancel', 'auto_del', 'forcesub', 'files', 'add_banuser', 'token', 'del_banuser', 'banuser_list', 
    'status', 'req_fsub', 'myplan', 'short', 'check', 'free', 'set_free_limit', 'download', 'rohit']))
async def handle_download_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_mention = message.from_user.mention

    # Ensure user exists in DB
    if not await db.present_user(user_id):
        try:
            await db.add_user(user_id)
        except Exception as e:
            logging.error(f"Failed to add user {user_id} to the database: {e}")

    # Fetch user and feature settings
    is_premium = await is_premium_user(user_id)
    verify_status = await db.get_verify_status(user_id)
    await db.reset_free_usage(user_id)  # Reset free usage if 24 hours passed
    free_settings = await db.get_free_settings()
    VERIFY_EXPIRE = await db.get_verified_time()
    current_time = time.time()

    free_limit = await db.get_free_limit(user_id)
    free_enabled = await db.get_free_state(user_id)
    is_verified_recently = await db.was_verified_in_last_24hrs(user_id)
    token = ''.join(random.choices(rohit.ascii_letters + rohit.digits, k=10))
    shortener_url = await db.get_shortener_url()
    shortener_api = await db.get_shortener_api()
    long_url = f"https://telegram.dog/{client.username}?start=verify_{token}"
    tut_vid_url = await db.get_tut_video()
    free_count = await db.check_free_usage(user_id)

    # Expire verification if needed
    if verify_status['is_verified'] and VERIFY_EXPIRE and VERIFY_EXPIRE < (time.time() - verify_status['verified_time']):
        await db.update_verify_status(user_id, is_verified=False)

    # Handle token verification
    if "verify_" in message.text:
        _, token = message.text.split("_", 1)
        if verify_status['verify_token'] != token:
            return await message.reply("⚠️ Invalid or expired token. Please try again with /start.")

        await db.update_verify_status(user_id, is_verified=True, verified_time=time.time())
        await db.update_verification_time(user_id)

        return await message.reply(
            f"✅ Token successfully verified.\n\n"
            f"🔑 Valid for: {get_exp_time(VERIFY_EXPIRE)}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("BUY PREMIUM", callback_data="buy_prem")]]),
            protect_content=False,
            quote=True
        )

    # Request a valid TeraBox link
    valid_domains = [
        'terabox.com', 'nephobox.com', '4funbox.com', 'mirrobox.com',
        'momerybox.com', 'teraboxapp.com', '1024tera.com',
        'terabox.app', 'gibibox.com', 'goaibox.com', 'terasharelink.com',
        'teraboxlink.com', 'terafileshare.com'
    ]

    try:
        response = await client.listen(chat_id=message.chat.id, filters=filters.text)
        terabox_link = response.text.strip()

        if any(domain in terabox_link for domain in valid_domains):
            await response.reply_text("✅ Valid link received! Processing...")
        else:
            return
    except TimeoutError:
        return await message.reply_text("⏰ Timeout! No link received.")

    reply_msg = await message.reply_text("🔄 Processing your link, please wait...")

    # **Premium Users → Immediate Processing**
    if is_premium:
        premium_msg = await message.reply("✅ Processing as a premium user...")
        try:
            file_path, thumbnail_path, video_title, video_duration = await download_video(terabox_link, reply_msg, user_mention, user_id)

            if file_path is None:
                return await reply_msg.edit_text("Failed to download. The link may be broken.")

            await upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)
            await premium_msg.delete()
        except Exception as e:
            logging.error(f"Download error: {e}")
            return await reply_msg.edit_text("❌ API returned a broken link.")

    # **Verified Free Users**
    elif verify_status['is_verified']:
        verified_msg = await message.reply("✅ Processing as a verified user...")
        try:
            file_path, thumbnail_path, video_title, video_duration = await download_video(terabox_link, reply_msg, user_mention, user_id)

            if file_path is None:
                return await reply_msg.edit_text("Failed to download. The link may be broken.")

            await upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)
            await verified_msg.delete()
        except Exception as e:
            logging.error(f"Download error: {e}")
            return await reply_msg.edit_text("❌ API returned a broken link.")

    # **Free Usage Check**
    elif free_enabled:
        free_count = await db.check_free_usage(user_id)

        if free_count < free_limit:
            # Allow free usage
            await db.update_free_usage(user_id)
            remaining_attempts = free_limit - free_count - 1
            free_msg = await message.reply(f"✅ Processing as a free user...\n🔄 Remaining attempts: {remaining_attempts}")
            
            try:
                file_path, thumbnail_path, video_title, video_duration = await download_video(terabox_link, reply_msg, user_mention, user_id)

                if file_path is None:
                    return await reply_msg.edit_text("Failed to download. The link may be broken.")

                await upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)
                await free_msg.delete()
            except Exception as e:
                logging.error(f"Download error: {e}")
                return await reply_msg.edit_text("❌ API returned a broken link.")

        elif free_count >= free_limit:
            if shortener_url and shortener_api:
                if is_verified_recently:
                    return await message.reply(
                        "⚠️ Token expired. Please purchase premium.\nContact @rohit_1888 to upgrade.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]])
                    )

                # Generate new token
                short_link = await get_shortlink(long_url)
                await db.update_verify_status(user_id, verify_token=token, verified_time=current_time, link="")

                btn = [
                    [InlineKeyboardButton("Click here", url=short_link), InlineKeyboardButton('How to verify', url=tut_vid_url)],
                    [InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]
                ]

                return await message.reply(
                    f"⚠️ Free limit exceeded. Please verify your token to continue.\n\n"
                    f"Token Timeout: {get_exp_time(VERIFY_EXPIRE)}\n\n"
                    f"🔑 By completing 1 ad, you can use the bot for {get_exp_time(VERIFY_EXPIRE)}.",
                    reply_markup=InlineKeyboardMarkup(btn),
                    protect_content=False
                )

            else:
                return await message.reply(
                    "⚠️ Free limit expired. Purchase premium to continue.\nContact @rohit_1888 to upgrade.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]])
                )

    # **Free Usage Disabled**
    else:
        return await message.reply(
            "⚠️ Free downloads are disabled. Please purchase premium.\nContact @rohit_1888 to upgrade.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]])
        )