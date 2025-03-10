#(©)Codexbotz
import binascii
import base64
import re
import asyncio
from pyrogram import filters, Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from shortzy import Shortzy
import requests
import time
from datetime import datetime
from database.database import *
from config import OWNER_ID
import random
import string
from datetime import datetime, timedelta
from database.database import db  # Ensure this is the correct import for your database instance
#=============================================================================================================================================================================
# -------------------- HELPER FUNCTIONS FOR USER VERIFICATION IN DIFFERENT CASES -------------------- 
#=============================================================================================================================================================================
# used for checking banned user
async def check_banUser(filter, client, update):
    try:
        user_id = update.from_user.id
        return await db.ban_user_exist(user_id)
    except: #Exception as e:
        #print(f"!Error on check_banUser(): {e}")
        return False


#used for cheking if a user is admin ~Owner also treated as admin level
async def check_admin(filter, client, update):
    try:
        user_id = update.from_user.id       
        return any([user_id == OWNER_ID, await db.admin_exist(user_id)])
    except Exception as e:
        print(f"! Exception in check_admin: {e}")
        return False


# Check user subscription in Channels in a more optimized way
async def is_subscribed(client, update):
    if update is None or update.from_user is None:  # Check if update is None
        return False  # Treat as not subscribed (or handle differently)

    Channel_ids = await db.get_all_channels() or []  # Ensure it's always a list

    if not Channel_ids:
        return True

    user_id = update.from_user.id

    if any([user_id == OWNER_ID, await db.admin_exist(user_id)]):
        return True

    # Handle the case for a single channel directly
    if len(Channel_ids) == 1:
        return await is_userJoin(client, user_id, Channel_ids[0])

    # Use asyncio.gather to check multiple channels concurrently
    tasks = [is_userJoin(client, user_id, ids) for ids in Channel_ids if ids]
    results = await asyncio.gather(*tasks)

    return all(results)  # Return False if any check fails


#Chcek user subscription by specifying channel id and user id
async def is_userJoin(client, user_id, channel_id):
    #REQFSUB = await db.get_request_forcesub()
    try:
        member = await client.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER}

    except UserNotParticipant:
        if await db.get_request_forcesub(): #and await privateChannel(client, channel_id):
                return await db.reqSent_user_exist(channel_id, user_id)

        return False

    except Exception as e:
        print(f"!Error on is_userJoin(): {e}")
        return False
#=============================================================================================================================================================================


async def get_messages(client, message_ids):
    messages = []
    total_messages = 0
    while total_messages != len(message_ids):
        temb_ids = message_ids[total_messages:total_messages+200]
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temb_ids
            )
        except FloodWait as e:
            await asyncio.sleep(e.x)
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temb_ids
            )
        except:
            pass
        total_messages += len(temb_ids)
        messages.extend(msgs)
    return messages

async def get_message_id(client, message):
    if message.forward_from_chat:
        if message.forward_from_chat.id == client.db_channel.id:
            return message.forward_from_message_id
        else:
            return 0
    elif message.forward_sender_name:
        return 0
    elif message.text:
        pattern = "https://t.me/(?:c/)?(.*)/(\d+)"
        matches = re.match(pattern,message.text)
        if not matches:
            return 0
        channel_id = matches.group(1)
        msg_id = int(matches.group(2))
        if channel_id.isdigit():
            if f"-100{channel_id}" == str(client.db_channel.id):
                return msg_id
        else:
            if channel_id == client.db_channel.username:
                return msg_id
    else:
        return 0



default_verify = {
    'is_verified': False,
    'verified_time': 0,
    'verify_token': "",
    'link': ""
}

async def get_verify_status(user_id):
    return await db.get_verify_status(user_id)

async def get_shortlink(link):
    # Fetch shortener details from the database
    shortener_url = await db.get_shortener_url()
    shortener_api = await db.get_shortener_api()

    # Validate shortener details
    if not shortener_url or not shortener_api:
        logging.error("Shortener URL or API key is missing.")
        raise ValueError("Shortener details are not configured.")

    # Log the shortener URL and long URL for debugging
    logging.info(f"Using shortener URL: {shortener_url}")
    logging.info(f"Original Link: {link}")

    try:
        # Initialize Shortzy without altering the shortener_url
        shortzy = Shortzy(api_key=shortener_api, base_site=shortener_url)
        short_link = await shortzy.convert(link)
        return short_link
    except Exception as e:
        logging.error(f"Error using Shortzy: {e}")
        raise

def get_exp_time(seconds):
    periods = [('days', 86400), ('hours', 3600), ('mins', 60), ('secs', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)}{period_name}'
    return result



def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time

#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#Check user subscription in Channels
"""async def is_subscribed(filter, client, update):
    Channel_ids = await db.get_all_channels()
    
    if not Channel_ids:
        return True

    user_id = update.from_user.id

    if any([user_id == OWNER_ID, await db.admin_exist(user_id)]):
        return True
        
    member_status = ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER
    
    REQFSUB = await db.get_request_forcesub()
                    
    for id in Channel_ids:
        if not id:
            continue
            
        try:
            member = await client.get_chat_member(chat_id=id, user_id=user_id)
        except UserNotParticipant:
            member = None
            if REQFSUB and await privateChannel(client, id):
                if not await db.reqSent_user_exist(id, user_id):
                    return False
            else:
                return False
                
        if member:
            if member.status not in member_status:
                if REQFSUB and await privateChannel(client, id):
                    if not await db.reqSent_user_exist(id, user_id):
                        return False
                else:
                    return False

    return True"""

#Check user subscription in Channels in More Simpler way
"""async def is_subscribed(filter, client, update):
    Channel_ids = await db.get_all_channels()
    
    if not Channel_ids:
        return True

    user_id = update.from_user.id

    if any([user_id == OWNER_ID, await db.admin_exist(user_id)]):
        return True

    for ids in Channel_ids:
        if not ids:
            continue
            
        if not await is_userJoin(client, user_id, ids):
            return False
            
    return True"""
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------


#subscribed = filters.create(is_subscribed)
is_admin = filters.create(check_admin)
banUser = filters.create(check_banUser)