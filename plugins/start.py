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


# Enable logging
logging.basicConfig(level=logging.INFO)

@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    id = message.from_user.id
    user_id = message.from_user.id
    VERIFY_EXPIRE = await db.get_verified_time()
    text = message.text
    verify_status = await db.get_verify_status(id)

    # Handle expired verification
    if (
        verify_status['is_verified'] and
        VERIFY_EXPIRE is not None and
        VERIFY_EXPIRE < (time.time() - verify_status['verified_time'])
    ):
        await db.update_verify_status(id, is_verified=False)

    logging.info(f"Received /start command from user ID: {id}")

    # Check and add user to the database if not present
    if not await db.present_user(id):
        try:
            await db.add_user(id)
        except Exception as e:
            logging.error(f"Error adding user: {e}")
            
    # Token verification logic
    if "verify_" in message.text:
        _, token = message.text.split("_", 1)
        if verify_status['verify_token'] != token:
            return await message.reply("⚠️ Your token is invalid or expired. Please try again with /start.")

        # Update verification status
        await db.update_verify_status(user_id, is_verified=True, verified_time=time.time())
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

    else:
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("😊 About Me", callback_data="about"),
                 InlineKeyboardButton("🔒 Close", callback_data="close")],
                [InlineKeyboardButton('BUY PREMIUM', callback_data='buy_prem')],
                [InlineKeyboardButton('⛩️ Channel', url='https://t.me/CodeFlix_Bots'),
                 InlineKeyboardButton('⚡️ Support', url='https://t.me/CodeflixSupport')],
                [InlineKeyboardButton('🌐 Developer', url='https://t.me/rohit_1888')]
            ]
        )

        await message.reply_photo(
            photo=START_PIC,
            caption=START_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name or '',
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=reply_markup,
        )
#=====================================================================================##

WAIT_MSG = """"<b>Processing ...</b>"""

REPLY_ERROR = """<code>Use this command as a replay to any telegram message with out any spaces.</code>"""

#=====================================================================================##


# Create a global dictionary to store chat data
chat_data_cache = {}

@Bot.on_message(filters.command('start') & filters.private & ~banUser)
async def not_joined(client: Client, message: Message):
    temp = await message.reply(f"<b>??</b>")

    user_id = message.from_user.id

    REQFSUB = await db.get_request_forcesub()
    buttons = []
    count = 0

    try:
        for total, chat_id in enumerate(await db.get_all_channels(), start=1):
            await message.reply_chat_action(ChatAction.PLAYING)

            # Show the join button of non-subscribed Channels.....
            if not await is_userJoin(client, user_id, chat_id):
                try:
                    # Check if chat data is in cache
                    if chat_id in chat_data_cache:
                        data = chat_data_cache[chat_id]  # Get data from cache
                    else:
                        data = await client.get_chat(chat_id)  # Fetch from API
                        chat_data_cache[chat_id] = data  # Store in cache

                    cname = data.title

                    # Handle private channels and links
                    if REQFSUB and not data.username: 
                        link = await db.get_stored_reqLink(chat_id)
                        await db.add_reqChannel(chat_id)

                        if not link:
                            link = (await client.create_chat_invite_link(chat_id=chat_id, creates_join_request=True)).invite_link
                            await db.store_reqLink(chat_id, link)
                    else:
                        link = data.invite_link

                    # Add button for the chat
                    buttons.append([InlineKeyboardButton(text=cname, url=link)])
                    count += 1
                    await temp.edit(f"<b>{'! ' * count}</b>")

                except Exception as e:
                    print(f"Can't Export Channel Name and Link..., Please Check If the Bot is admin in the FORCE SUB CHANNELS:\nProvided Force sub Channel:- {chat_id}")
                    return await temp.edit(f"<b><i>! Eʀʀᴏʀ, Cᴏɴᴛᴀᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ ᴛᴏ sᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇs @rohit_1888</i></b>\n<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>")

        try:
            buttons.append([InlineKeyboardButton(text='♻️ Tʀʏ Aɢᴀɪɴ', url=f"https://t.me/{client.username}?start={message.command[1]}")])
        except IndexError:
            pass

        await message.reply_photo(
            photo=FORCE_PIC,
            caption=FORCE_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    except Exception as e:
        print(f"Error: {e}")  # Print the error message for debugging
        # Optionally, send an error message to the user or handle further actions here
        await temp.edit(f"<b><i>! Eʀʀᴏʀ, Cᴏɴᴛᴀᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ ᴛᴏ sᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇs @rohit_1888</i></b>\n<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>")

@Bot.on_message(filters.command('users') & filters.private & filters.user(OWNER_ID))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await db.full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@Bot.on_message(filters.private & filters.command('broadcast') & is_admin)
async def send_text(client: Bot, message: Message):
    if message.reply_to_message:
        query = await db.full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0

        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await db.del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await db.del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1

        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""

        return await pls_wait.edit(status)

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()


# Command to add premium user
@Bot.on_message(filters.command('addpaid') & filters.private & is_admin)
async def add_premium_user_command(client, msg):
    if len(msg.command) != 4:
        await msg.reply_text("Usage: /addpaid <user_id> <time_value> <time_unit (m/d)>")
        return

    try:
        user_id = int(msg.command[1])
        time_value = int(msg.command[2])
        time_unit = msg.command[3].lower()  # 'm' or 'd'

        # Call add_premium function
        expiration_time = await add_premium(user_id, time_value, time_unit)

        # Notify the admin about the premium activation
        await msg.reply_text(
            f"User {user_id} added as a premium user for {time_value} {time_unit}.\n"
            f"Expiration Time: {expiration_time}"
        )

        # Notify the user about their premium status
        await client.send_message(
            chat_id=user_id,
            text=(
                f"🎉 Congratulations! You have been upgraded to premium for {time_value} {time_unit}.\n\n"
                f"Expiration Time: {expiration_time}.\n\n"
                f"Happy Downloading 💦"
            ),
        )

    except ValueError:
        await msg.reply_text("Invalid input. Please check the user_id, time_value, and time_unit.")
    except Exception as e:
        await msg.reply_text(f"An error occurred: {str(e)}")


# Command to remove premium user
@Bot.on_message(filters.command('removepaid') & filters.private & is_admin)
async def pre_remove_user(client: Client, msg: Message):
    if len(msg.command) != 2:
        await msg.reply_text("useage: /removeuser user_id ")
        return
    try:
        user_id = int(msg.command[1])
        await remove_premium(user_id)
        await msg.reply_text(f"User {user_id} has been removed.")
    except ValueError:
        await msg.reply_text("user_id must be an integer or not available in database.")


# Command to list active premium users
@Bot.on_message(filters.command('listpaid') & filters.private & is_admin)
async def list_premium_users_command(client, message):
    # Define IST timezone
    ist = timezone("Asia/Kolkata")

    # Retrieve all users from the collection
    premium_users_cursor = collection.find({})
    premium_user_list = ['Active Premium Users in database:']
    current_time = datetime.now(ist)  # Get current time in IST

    # Use async for to iterate over the async cursor
    async for user in premium_users_cursor:
        user_id = user["user_id"]
        expiration_timestamp = user["expiration_timestamp"]

        try:
            # Convert expiration_timestamp to a timezone-aware datetime object in IST
            expiration_time = datetime.fromisoformat(expiration_timestamp).astimezone(ist)

            # Calculate remaining time
            remaining_time = expiration_time - current_time

            if remaining_time.total_seconds() <= 0:
                # Remove expired users from the database
                await collection.delete_one({"user_id": user_id})
                continue  # Skip to the next user if this one is expired

            # If not expired, retrieve user info
            user_info = await client.get_users(user_id)
            username = user_info.username if user_info.username else "No Username"
            first_name = user_info.first_name

            # Calculate days, hours, minutes, seconds left
            days, hours, minutes, seconds = (
                remaining_time.days,
                remaining_time.seconds // 3600,
                (remaining_time.seconds // 60) % 60,
                remaining_time.seconds % 60,
            )
            expiry_info = f"{days}d {hours}h {minutes}m {seconds}s left"

            # Add user details to the list
            premium_user_list.append(
                f"UserID: <code>{user_id}</code>\n"
                f"User: @{username}\n"
                f"Name: <code>{first_name}</code>\n"
                f"Expiry: {expiry_info}"
            )
        except Exception as e:
            premium_user_list.append(
                f"UserID: <code>{user_id}</code>\n"
                f"Error: Unable to fetch user details ({str(e)})"
            )

    if len(premium_user_list) == 1:  # No active users found
        await message.reply_text("I found 0 active premium users in my DB")
    else:
        await message.reply_text("\n\n".join(premium_user_list), parse_mode=None)

@Bot.on_message(filters.command('myplan') & filters.private)
async def check_plan(client: Client, message: Message):
    user_id = message.from_user.id  # Get user ID from the message

    # Get the premium status of the user
    status_message = await check_user_plan(user_id)

    # Send the response message to the user
    await message.reply(status_message)

@Bot.on_message(filters.command('forcesub') & filters.private & ~banUser)
async def fsub_commands(client: Client, message: Message):
    button = [[InlineKeyboardButton("Cʟᴏsᴇ ✖️", callback_data="close")]]
    await message.reply(text=FSUB_CMD_TXT, reply_markup=InlineKeyboardMarkup(button), quote=True)


@Bot.on_message(filters.command('help') & filters.private & ~banUser)
async def help(client: Client, message: Message):
    buttons = [
        [
            InlineKeyboardButton("🤖 Oᴡɴᴇʀ", url=f"tg://openmessage?user_id={OWNER_ID}"), 
            InlineKeyboardButton("🥰 Dᴇᴠᴇʟᴏᴘᴇʀ", url="https://t.me/rohit1888")
        ]
    ]
    
    try:
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo = FORCE_PIC,
            caption = HELP_TEXT.format(
                first = message.from_user.first_name,
                last = message.from_user.last_name,
                username = None if not message.from_user.username else '@' + message.from_user.username,
                mention = message.from_user.mention,
                id = message.from_user.id
            ),
            reply_markup = reply_markup#,
            #message_effect_id = 5046509860389126442 #🎉
        )
    except Exception as e:
        return await message.reply(f"<b><i>! Eʀʀᴏʀ, Cᴏɴᴛᴀᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ ᴛᴏ sᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇs @rohit_1888</i></b>\n<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>")

@Bot.on_message(filters.command('short') & filters.private & is_admin)
async def shorten_link_command(client, message):
    id = message.from_user.id

    try:
        # Prompt the user to send the link to be shortened
        set_msg = await client.ask(
            chat_id=id,
            text="<b><blockquote>⏳ Sᴇɴᴅ ᴀ ʟɪɴᴋ ᴛᴏ ʙᴇ sʜᴏʀᴛᴇɴᴇᴅ</blockquote>\n\nFᴏʀ ᴇxᴀᴍᴘʟᴇ: <code>https://example.com/long_url</code></b>",
            timeout=60
        )

        # Validate the user input for a valid URL
        original_url = set_msg.text.strip()

        if original_url.startswith("http") and "://" in original_url:
            try:
                # Call the get_shortlink function
                short_link = await get_shortlink(original_url)

                # Inform the user about the shortened link
                await set_msg.reply(f"<b>🔗 Lɪɴᴋ Cᴏɴᴠᴇʀᴛᴇᴅ Sᴜᴄᴄᴇssғᴜʟʟʏ ✅</b>\n\n<blockquote>🔗 Sʜᴏʀᴛᴇɴᴇᴅ Lɪɴᴋ: <code>{short_link}</code></blockquote>")
            except ValueError as ve:
                # If shortener details are missing
                await set_msg.reply(f"<b>❌ Error: {ve}</b>")
            except Exception as e:
                # Handle errors during the shortening process
                await set_msg.reply(f"<b>❌ Error while shortening the link:\n<code>{e}</code></b>")
        else:
            # If the URL is invalid, prompt the user to try again
            await set_msg.reply("<b>❌ Invalid URL. Please send a valid link that starts with 'http'.</b>")

    except asyncio.TimeoutError:
        # Handle timeout exceptions
        await client.send_message(
            id,
            text="<b>⏳ Tɪᴍᴇᴏᴜᴛ. Yᴏᴜ ᴛᴏᴏᴋ ᴛᴏᴏ ʟᴏɴɢ ᴛᴏ ʀᴇsᴘᴏɴᴅ. Pʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.</b>",
            disable_notification=True
        )
        print(f"! Timeout occurred for user ID {id} while processing '/shorten' command.")

    except Exception as e:
        # Handle any other exceptions
        await client.send_message(
            id,
            text=f"<b>❌ Aɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:\n<code>{e}</code></b>",
            disable_notification=True
        )
        print(f"! Error occurred on '/short' command: {e}")


@Bot.on_message(filters.command("check"))
async def check_command(client, message):
    user_id = message.from_user.id

    verify_status = await db.get_verify_status(user_id)
    logging.info(f"Verify status for user {user_id}: {verify_status}")

    if verify_status['is_verified']:
        expiry_time = get_exp_time(VERIFY_EXPIRE - (time.time() - verify_status['verified_time']))
        await message.reply(f"Your token is verified and valid for {expiry_time}.")
    else:
        await message.reply("Your token is not verified or has expired , /start to generate! Verify token....")


@Bot.on_message(filters.command("set_free_limit") & is_admin)
async def set_free_limit(client: Client, message: Message):
    try:
        limit = int(message.text.split()[1])
        await db.set_free_limit(limit=limit)
        await message.reply(f"✅ Free usage limit has been set to {limit}.")
    except (IndexError, ValueError):
        await message.reply("❌ Invalid usage. Use the command like this:\n`/set_free_limit 10`")


@Bot.on_message(filters.command('free') & filters.private & is_admin)
async def toggle_freemode(client: Client, message: Message):
    await message.reply_chat_action(ChatAction.TYPING)

    # Check the current caption state (enabled or disabled)
    current_state = await db.get_free_state(message.from_user.id)

    # Toggle the state
    new_state = not current_state
    await db.set_free_state(message.from_user.id, new_state)

    # Create buttons for ✅ and ❌ based on the new state
    caption_button = InlineKeyboardButton(
        text="✅ Free Enabled" if new_state else "❌ Free  Disabled", 
        callback_data="toggle_caption"
    )

    # Send a message with the toggle button
    await message.reply_text(
        f"Free Mode is now {'enabled' if new_state else 'disabled'}.",
        reply_markup=InlineKeyboardMarkup([
            [caption_button]
        ])
    )


@Bot.on_message(filters.command("stats") & is_admin)
async def stats_command(client, message):
    total_users = users_collection.count_documents({})
    verified_users = users_collection.count_documents({"verify_status.is_verified": True})
    unverified_users = total_users - verified_users

    free_settings = await db.get_free_settings()
    free_limit = free_settings["limit"]
    free_enabled = free_settings["enabled"]

    status = f"""<b><u>Verification Stats</u></b>

Total Users: <code>{total_users}</code>
Verified Users: <code>{verified_users}</code>
Unverified Users: <code>{unverified_users}</code>

<b><u>Free Usage Settings</u></b>
Free Usage Limit: <code>{free_limit}</code>
Free Usage Enabled: <code>{free_enabled}</code>"""

    await message.reply(status)
