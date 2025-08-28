from pyrogram.errors import FloodWait
import asyncio

async def safe_send(app, chat_id, text):
    try:
        await app.send_message(chat_id, text)
    except FloodWait as e:
        print(f"⚠️ FloodWait: Sleeping for {e.value} seconds...")
        await asyncio.sleep(e.value)
        await app.send_message(chat_id, text)
