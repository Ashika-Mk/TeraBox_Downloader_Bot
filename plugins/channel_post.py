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

@Bot.on_message(filters.command("download") & filters.private)
async def handle_download_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_mention = message.from_user.mention

    # Add user to the database if not already present
    if not await db.present_user(user_id):
        try:
            await db.add_user(user_id)
        except Exception as e:
            logging.error(f"Failed to add user {user_id} to the database: {e}")

    # Fetch user details and free usage settings
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
    


    if (
        verify_status['is_verified'] and
        VERIFY_EXPIRE is not None and
        VERIFY_EXPIRE < (time.time() - verify_status['verified_time'])
    ):
        await db.update_verify_status(user_id, is_verified=False)

    # Token verification logic
    if "verify_" in message.text:
        _, token = message.text.split("_", 1)
        if verify_status['verify_token'] != token:
            return await message.reply("⚠️ Your token is invalid or expired. Please try again with /start.")

        # Update verification status
        await db.update_verify_status(user_id, is_verified=True, verified_time=time.time())
        await db.update_verification_time(user_id)
        if verify_status["link"] == "":
            await message.reply(
                f"✅ **Your token has been successfully verified.**\n\n"
                f"🔑 Valid for: {get_exp_time(VERIFY_EXPIRE)}.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("BUY PREMIUM", callback_data="buy_prem")]]
                ),
                protect_content=False,
                quote=True
            )
            return

    # Ask for a valid TeraBox link
    await message.reply_text(
        "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴛᴇʀᴀʙᴏx ʟɪɴᴋ ᴡɪᴛʜɪɴ 30 sᴇᴄᴏɴᴅs."
    )

    valid_domains = [
        'terabox.com', 'nephobox.com', '4funbox.com', 'mirrobox.com',
        'momerybox.com', 'teraboxapp.com', '1024tera.com',
        'terabox.app', 'gibibox.com', 'goaibox.com', 'terasharelink.com',
        'teraboxlink.com', 'terafileshare.com'
    ]

    try:
        # Wait for the user to send a valid link within 30 seconds
        response = await client.listen(
            chat_id=message.chat.id,
            filters=filters.text,
            timeout=30
        )
        terabox_link = response.text.strip()

        # Check if the link is valid
        if any(domain in terabox_link for domain in valid_domains):
            await response.reply_text("ᴠᴀʟɪᴅ ʟɪɴᴋ ʀᴇᴄᴇɪᴠᴇᴅ! ᴘʀᴏᴄᴇssɪɴɢ...")
            # Proceed with further actions (e.g., downloading the link content)
        else:
            await response.reply_text("ᴛʜᴀᴛ's ɴᴏᴛ ᴀ ᴠᴀʟɪᴅ ᴛᴇʀᴀʙᴏx ʟɪɴᴋ.")
    except TimeoutError:
        await message.reply_text("⏰ ᴛɪᴍᴇᴏᴜᴛ! ʏᴏᴜ ᴅɪᴅ ɴᴏᴛ sᴇɴᴅ ᴀ ʟɪɴᴋ ɪɴ ᴛɪᴍᴇ.")

    # Send an initial message to the user, which will be updated later
    reply_msg = await message.reply_text("🔄 **Processing your link, please wait...**")

    # Handle premium users
    if is_premium:
        premium_msg = await message.reply("✅ Processing your TeraBox link as a premium user...")
        try:
            # Download video from the provided link
            file_path, thumbnail_path, video_title, video_duration = await download_video(terabox_link, reply_msg, user_mention, user_id)

            if file_path is None:
                await reply_msg.edit_text("Failed to download the video. The provided download link may be broken.")
                return

            # Upload video
            await upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)

            await premium_msg.delete()

        except Exception as e:
            logging.error(f"Error handling message: {e}")
            await reply_msg.edit_text("❌ **Api has given a broken download link. Please don't contact the owner for this issue.**")
            return

    # Handle verified users
    if verify_status['is_verified']:
        verified_msg = await message.reply("✅ Processing your TeraBox link as a verified user...")
        try:
            # Download video from the provided link
            file_path, thumbnail_path, video_title, video_duration = await download_video(terabox_link, reply_msg, user_mention, user_id)

            if file_path is None:
                await reply_msg.edit_text("Failed to download the video. The provided download link may be broken.")
                return

            # Upload video
            await upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)

            await verified_msg.delete()

        except Exception as e:
            logging.error(f"Error handling message: {e}")
            await reply_msg.edit_text("❌ **Api has given a broken download link. Please don't contact the owner for this issue.**")
            return


    if not shortener_url or not shortener_api:

        await message.reply(
            "⚠️ Your 1 limit has expired.**\n\n"
            "Please purchase premium access to continue using the bot.\n\n"
            "Contact @rohit_1888 to upgrade.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]]
            )
        )
        return

    if free_enabled and not is_premium and not shortener_url and not shortener_api:
        free_count = await db.check_free_usage(user_id)

        if free_count >= free_limit:
            
            await message.reply(
                "⚠️ Your free limit has expired.**\n\n"
                "Please purchase premium access to continue using the bot.\n\n"
                "Contact @rohit_1888 to upgrade.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]]
                )
            )
            return
        if free_count < free_limit:

        # Allow free usage
            await db.update_free_usage(user_id)
            remaining_attempts = free_limit - free_count - 1
            free_msg = await message.reply(
                f"✅ Processing your TeraBox link as a free user...\n"
                f"🔄 Remaining free attempts: {remaining_attempts}"
            )
            try:
            # Download video from the provided link
                file_path, thumbnail_path, video_title, video_duration = await download_video(terabox_link, reply_msg, user_mention, user_id)
                if file_path is None:
                    await reply_msg.edit_text("Failed to download the video. The provided download link may be broken.")
                    return

                # Upload video
                await upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)

                await free_msg.delete()
            except Exception as e:
                logging.error(f"Error handling message: {e}")
                await reply_msg.edit_text("❌ Api has given a broken download link. Please don't contact the owner for this issue.")
                return

    # Handle free users with token generation once every 24 hours
    elif free_enabled and not is_premium and not verify_status['is_verified']:
        free_count = await db.check_free_usage(user_id)

        if free_count >= free_limit:
            # Check when the token was last generated
            if is_verified_recently:  # Token verified in the last 24 hours
                await message.reply(
                    "⚠️ Your token has expired.**\n\n"
                    "Please purchase premium access to continue using the bot.\n\n"
                    "Contact @rohit_1888 to upgrade.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]]
                    )
                )
                return

        elif not is_verified_recently:
            # Generate a new token
            short_link = await get_shortlink(long_url)
            await db.update_verify_status(user_id, verify_token=token, verified_time=current_time, link="")

            
            btn = [
                [InlineKeyboardButton("Click here", url=short_link),
                 InlineKeyboardButton('How to verify', url=tut_vid_url)],
                [InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]
            ]

            await message.reply(
                f"⚠️ Your free usage limit has been exceeded.**\n\n"
                f"Please verify your token to continue.\n\n"
                f"Token Timeout: {get_exp_time(VERIFY_EXPIRE)}\n\n"
                f"🔑 What is the token?\n\n"
                f"By completing 1 ad, you can use the bot for {get_exp_time(VERIFY_EXPIRE)}.",
                reply_markup=InlineKeyboardMarkup(btn),
                protect_content=False
            )
            return

    elif free_enabled and not is_premium and not verify_status['is_verified']:
            # Check when the token was last generated
        if is_verified_recently:  # Token verified in the last 24 hours
            await message.reply(
                "⚠️ Your token has expired.**\n\n"
                "Please purchase premium access to continue using the bot.\n\n"
                "Contact @rohit_1888 to upgrade.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]]
                )
            )
            return

    elif not is_verified_recently:
            # Generate a new token
        short_link = await get_shortlink(long_url)
        await db.update_verify_status(user_id, verify_token=token, verified_time=current_time, link="")


        btn = [
            [InlineKeyboardButton("Click here", url=short_link),
             InlineKeyboardButton('How to verify', url=tut_vid_url)],
            [InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]
        ]

        await message.reply(
            f"⚠️ Your free usage limit has been exceeded.**\n\n"
            f"Please verify your token to continue.\n\n"
            f"Token Timeout: {get_exp_time(VERIFY_EXPIRE)}\n\n"
            f"🔑 What is the token?\n\n"
            f"By completing 1 ad, you can use the bot for {get_exp_time(VERIFY_EXPIRE)}.",
            reply_markup=InlineKeyboardMarkup(btn),
            protect_content=False
        )
        return

    #elif not free_enabled or not shortener_url or not shortener_api:
        #await message.reply(
            #"⚠️ Your limit has expired.\n\n"
            #"Please purchase premium access to continue using the bot.\n\n"
            #"Contact @rohit_1888 to upgrade.",
            #reply_markup=InlineKeyboardMarkup(
                #[[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]]
            #)
        #)
        #return
    #else:
        # Allow free usage#
        #await db.update_free_usage(user_id)
        #remaining_attempts = free_limit - free_count - 1
        #free_msg = await message.reply(
            #f"✅ Processing your TeraBox link as a free user...\n"
            #f"🔄 Remaining free attempts: {remaining_attempts}"
        #)
        #try:
            # Download video from the provided link#
            #file_path, thumbnail_path, video_title = await download_video(
                #terabox_link, reply_msg, user_mention, user_id
            #)

            #if file_path is None:
                #await reply_msg.edit_text("Failed to download the video. The provided download link may be broken.")
                #return

            # Upload video#
            #await upload_video(client, file_path, thumbnail_path, video_title, reply_msg, db_channel_id, user_mention, user_id, message)

            #await free_msg.delete()
        #except Exception as e:
            #logging.error(f"Error handling message: {e}")
            #await reply_msg.edit_text("❌ Api has given a broken download link. Please don't contact the owner for this issue.")
            #return

    # Token expired or unverified users
    #elif free_enabled and not shortener_url and not shortener_api:
        #if free_count >= free_limit:
            #await message.reply(
                #"⚠️ Your Today's free limit has expired.**\n\n"
               # "Please purchase premium access to continue using the bot.\n\n"
                #"Contact @rohit_1888 to upgrade.",
                #reply_markup=InlineKeyboardMarkup(
                   # [[InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')]]
               # )
            #)
       # return
    # Premium or verified users proceed
    #else:
        #await message.reply("✅ You have access. Thank you for being a premium/verified user.")
        #return


# Don't remove This Line From Here. Tg: @rohit_1888 | @Javpostr
