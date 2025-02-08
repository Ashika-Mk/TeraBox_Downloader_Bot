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

#@Bot.on_message(filters.private & is_admin & ~filters.command([
    #'start', 'users', 'broadcast', 'stats', #'addpaid', 'removepaid', 'listpaid',
    #'help', 'add_fsub', 'fsub_chnl', 'restart', #'del_fsub', 'add_admins', 'del_admins', 
    #'admin_list', 'cancel', 'auto_del', #'forcesub', 'files', 'add_banuser', 'token', #'del_banuser', 'banuser_list', 
   # 'status', 'req_fsub', 'myplan', 'short', #'check', 'free', 'set_free_limit']))
