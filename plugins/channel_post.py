# Don't remove This Line From Here. Tg: @rohit_1888 | @Javpostr
from bot import Bot
from pyrogram.types import Message
from pyrogram import filters
from config import *
from datetime import datetime
from helper_func import *
from pytz import timezone
from status import format_progress_bar
from video import *
import asyncio
import base64
import logging
import os
import random
import re, sys
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
from plugins.start import *
from plugins.query import *
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid
from datetime import datetime, timedelta
from pytz import timezone
import subprocess 

db_channel_id=CHANNEL_ID



@Client.on_message(filters.command('update') & filters.private & is_admin)
async def update_bot(client, message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("You are not authorized to update the bot.")

    try:
        msg = await message.reply_text("<b><blockquote>Pulling the latest updates and restarting the bot...</blockquote></b>")

        # Run git pull
        git_pull = subprocess.run(["git", "pull"], capture_output=True, text=True)

        if git_pull.returncode == 0:
            await msg.edit_text(f"<b><blockquote>Updates pulled successfully:\n\n{git_pull.stdout}</blockquote></b>")
        else:
            await msg.edit_text(f"<b><blockquote>Failed to pull updates:\n\n{git_pull.stderr}</blockquote></b>")
            return

        await asyncio.sleep(3)

        await msg.edit_text("<b><blockquote>✅ Bot is restarting now...</blockquote></b>")

    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")
        return

    finally:
        # Restart the bot process
        os.execl(sys.executable, sys.executable, *sys.argv)

@Bot.on_message(filters.private & filters.incoming)
async def handle_message(client: Client, message: Message):
    user_id = message.from_user.id
    user_mention = message.from_user.mention
    message_text = message.text.strip() if message.text else ""

    # Ensure user exists in DB
    if not await db.present_user(user_id):
        try:
            await db.add_user(user_id)
        except Exception as e:
            logging.error(f"Failed to add user {user_id} to the database: {e}")



    # ✅ Check Force Subscription
    if not await is_subscribed(client, message):
        # Don't remove This Line From Here. Tg: @rohit_1888 | @Javpostr
        return await not_joined(client, message)

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
    free_count = await db.check_free_usage(user_id)
    tut_vid_url = await db.get_tut_video()
    shortener_url = await db.get_shortener_url()
    shortener_api = await db.get_shortener_api()

    # Expire verification if needed
    if verify_status['is_verified'] and VERIFY_EXPIRE and VERIFY_EXPIRE < (time.time() - verify_status['verified_time']):
        await db.update_verify_status(user_id, is_verified=False)

    # Handle token verification
    if message_text.startswith("verify_"):
        _, token = message_text.split("_", 1)
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

    # Check valid TeraBox link
    valid_domains = [
        'terabox.com', 'nephobox.com', '4funbox.com', 'mirrobox.com',
        'momerybox.com', 'teraboxapp.com', '1024tera.com',
        'terabox.app', 'gibibox.com', 'goaibox.com', 'terasharelink.com',
        'teraboxlink.com', 'terafileshare.com'
    ]

    if not any(domain in message_text for domain in valid_domains):
        return await message.reply("⚠️ Please send a valid TeraBox link.")

    # Process the link
    reply_msg = await message.reply_text("🔄 Processing your link, please wait...")

    files_data = []

          
    if is_premium:
        premium_msg = await message.reply("✅ Processing as a premium user...")
        try:
            files_data = await download_video(
                message_text,  # URL
                reply_msg,
                user_mention,
                user_id,
                client,
                db_channel_id,
                message
            )
            if not files_data:
                return await reply_msg.edit_text("Failed to download. The link may be broken.")
        except Exception as e:
            logging.error(f"Download error (premium): {e}")
            return await reply_msg.edit_text("❌ API returned a broken link.")

        try:
            await upload_videos(client, files_data, reply_msg, db_channel_id, user_mention, user_id, message)
            await premium_msg.delete()
        except Exception as e:
            logging.error(f"Upload error (premium): {e}")
            return await reply_msg.edit_text("❌ Failed to upload files.")

    elif verify_status['is_verified']:
        verified_msg = await message.reply("✅ Processing as a verified user...")
        try:
            files_data = await download_video(message_text, reply_msg, user_mention, user_id)
            if not files_data:
                return await reply_msg.edit_text("Failed to download. The link may be broken.")
        except Exception as e:
            logging.error(f"Download error (verified): {e}")
            return await reply_msg.edit_text("❌ API returned a broken link.")

        try:
            await upload_videos(client, files_data, reply_msg, db_channel_id, user_mention, user_id, message)
            await verified_msg.delete()
        except Exception as e:
            logging.error(f"Upload error (verified): {e}")
            return await reply_msg.edit_text("❌ Failed to upload files.")

    elif free_enabled:
        if free_count < free_limit:
            await db.update_free_usage(user_id)
            remaining_attempts = free_limit - free_count - 1

            free_msg = await message.reply(
                f"✅ Processing as a free user...\n🔄 Remaining attempts: {remaining_attempts}"
            )
            try:
                files_data = await download_video(message_text, reply_msg, user_mention, user_id)
                if not files_data:
                    return await reply_msg.edit_text("Failed to download. The link may be broken.")
            except Exception as e:
                logging.error(f"Download error (free): {e}")
                return await reply_msg.edit_text("❌ API returned a broken link.")

            try:
                await upload_videos(client, files_data, reply_msg, db_channel_id, user_mention, user_id, message)
                await free_msg.delete()
            except Exception as e:
                logging.error(f"Upload error (free): {e}")
                return await reply_msg.edit_text("❌ Failed to upload files.")

        else:
            if shortener_api and shortener_url:
                if not verify_status['is_verified'] or (is_verified_recently and not verify_status['is_verified']):
                    token = ''.join(random.choices(rohit.ascii_letters + rohit.digits, k=10))
                    long_url = f"https://telegram.dog/{client.username}?start=verify_{token}"
                    short_link = await get_shortlink(long_url)

                    await db.update_verify_status(user_id, verify_token=token, verified_time=current_time, link="")

                    btn = [
                        [InlineKeyboardButton("Click here", url=short_link),
                         InlineKeyboardButton('How to verify', url=tut_vid_url)],
                        [InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]
                    ]

                    return await message.reply(
                        f"⚠️ Your free usage limit has been exceeded.\n\n"
                        f"Please verify your token to continue.\n\n"
                        f"Token Timeout: {get_exp_time(VERIFY_EXPIRE)}\n\n"
                        f"🔑 What is the token?\n\n"
                        f"By completing 1 ad, you can use the bot for {get_exp_time(VERIFY_EXPIRE)}.",
                        reply_markup=InlineKeyboardMarkup(btn),
                        protect_content=False
                    )
            else:
                return await message.reply(
                    "⚠️ Free limit exceeded. Please purchase premium.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]])
                )

    else:
        return await message.reply(
            "⚠️ Free downloads are disabled. Please purchase premium.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]])
        )