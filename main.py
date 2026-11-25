import os
import re
import base64
import asyncio
import threading
import aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client
from pyrogram.errors import FloodWait

# --- Render Port & Health Server ---
PORT = int(os.environ.get("PORT", "8080"))

status_info = {
    "bot_name": None,
    "user_name": None,
    "user_connected": False,
    "last_activity": "Starting up..."
}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""
        <html>
        <head><title>Telegram Saver Bot</title></head>
        <body style="font-family: sans-serif; padding: 20px; line-height: 1.6;">
            <h2>🚀 Telegram Restricted Content Saver Bot</h2>
            <hr>
            <p><b>Bot Status:</b> {"✅ Active (@" + str(status_info['bot_name']) + ")" if status_info['bot_name'] else "⏳ Connecting..."}</p>
            <p><b>User Session:</b> {"✅ Connected (" + str(status_info['user_name']) + ")" if status_info['user_connected'] else "❌ Disconnected"}</p>
            <p><b>Last Status:</b> {status_info['last_activity']}</p>
            <p><b>Server:</b> Running 24/7 on port {PORT}</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# --- Credentials & Config ---
API_ID = int(os.environ.get("API_ID", "28220028"))
API_HASH = os.environ.get("API_HASH", "2644b27a6f3bff5dea5d09e657b01a5f")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9138676538:AAGmn3JyvgTlJVuWHf6X-_GfKr4jaqstuzU").strip().strip('"').strip("'")

raw_session = os.environ.get(
    "SESSION_STRING",
    "AQGumnwApofV6x8AURQDcalOpweXjIpV4ADbnie6FX3UuZvNSf79ANF0XavKZUXduAw6ZQ9yI9LasbNtt5afR85n3HPns4-Dttx-ZLPeFmrwkPYysOoDtw7uIjptH-D7G3szqYEyndvYgfVi6UNYY0Uk4UzCSogm_AAYTpJUMBzQWjjYZ1Tp_3UeCcWlYkUMElq3N-Zd-6Y4s6NlT639n51tksdEn_I8rFZedL1yWx8vvZZ-nWGkOYwAn9KmQHoYQcefZomXvj5zbcdmJ2_SkGC0vJRa0Pq_aoOuQrA5P6detlgbT_ii2yC0OQ7vlF5s-jzRxsvG2I_nHUzHZVJdSnoR7ee8qwAAAAHeUpBIAA"
).strip()

pad = '=' * (-len(raw_session) % 4)
decoded = base64.urlsafe_b64decode(raw_session + pad)
if len(decoded) == 270:
    SESSION_STRING = base64.urlsafe_b64encode(decoded + b'\x00').decode().rstrip('=')
else:
    SESSION_STRING = raw_session

# Caption & Thumbnail config
CUSTOM_FOOTER = os.environ.get("CUSTOM_FOOTER", "")
TELEGRAM_ID = os.environ.get("TELEGRAM_ID", "")
CHANNEL_MENTION = os.environ.get("CHANNEL_MENTION", "")
CUSTOM_THUMBNAIL_URL = os.environ.get("CUSTOM_THUMBNAIL_URL", "")
CUSTOM_THUMBNAIL_PATH = os.environ.get("CUSTOM_THUMBNAIL_PATH", "thumb.jpg")

if not CUSTOM_FOOTER and (TELEGRAM_ID or CHANNEL_MENTION):
    footer_lines = []
    if TELEGRAM_ID:
        footer_lines.append(f"👤 By: {TELEGRAM_ID}")
    if CHANNEL_MENTION:
        footer_lines.append(f"📢 Channel: {CHANNEL_MENTION}")
    CUSTOM_FOOTER = "\n".join(footer_lines)

def format_caption(original_caption: str) -> str:
    caption = original_caption or ""
    if CUSTOM_FOOTER:
        if caption:
            caption = f"{caption}\n\n{CUSTOM_FOOTER}"
        else:
            caption = CUSTOM_FOOTER
    if len(caption) > 1024:
        caption = caption[:1020] + "..."
    return caption

def prepare_thumbnail():
    if CUSTOM_THUMBNAIL_URL and not os.path.exists(CUSTOM_THUMBNAIL_PATH):
        try:
            import urllib.request
            print(f"Downloading custom thumbnail from {CUSTOM_THUMBNAIL_URL}...")
            urllib.request.urlretrieve(CUSTOM_THUMBNAIL_URL, CUSTOM_THUMBNAIL_PATH)
            print("Custom thumbnail downloaded successfully!")
        except Exception as e:
            print(f"Failed to download thumbnail: {e}")
    if os.path.exists(CUSTOM_THUMBNAIL_PATH):
        return CUSTOM_THUMBNAIL_PATH
    return None

# Pyrogram Clients
user_app = Client("user_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot_app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# --- Helper: Bot API HTTP Caller ---
async def call_bot_api(session: aiohttp.ClientSession, method: str, payload: dict = None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        async with session.post(url, json=payload or {}, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            return await resp.json()
    except Exception as e:
        print(f"Bot API {method} error: {e}")
        return None

async def send_text_msg(session: aiohttp.ClientSession, chat_id: int, text: str):
    return await call_bot_api(session, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })

async def edit_text_msg(session: aiohttp.ClientSession, chat_id: int, message_id: int, text: str):
    return await call_bot_api(session, "editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown"
    })


# --- Handle Incoming Message ---
async def handle_message(session: aiohttp.ClientSession, msg: dict):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    user_name = msg.get("from", {}).get("first_name", "Friend")

    status_info["last_activity"] = f"Received message from {user_name} ({chat_id})"
    print(f"📩 Incoming from {user_name} ({chat_id}): {text}")

    # 1. /start command
    if text.startswith("/start"):
        session_status = "✅ Connected" if status_info["user_connected"] else "⚠️ Disconnected"
        welcome_text = (
            f"👋 **Namaste {user_name}!**\n\n"
            "Main **Save Restricted Content Bot** hoon.\n\n"
            f"⚡ **User Session Status:** {session_status}\n\n"
            "📌 **Kaise use karein:**\n"
            "Mujhe kisi bhi restricted Telegram post ka link bhejo:\n\n"
            "• **Single post:** `https://t.me/c/3863573134/31`\n"
            "• **Multiple posts (Range):** `https://t.me/c/3863573134/31-35`\n\n"
            "Files download hokar bina restriction ke aapko mil jayengi! 🚀"
        )
        await send_text_msg(session, chat_id, welcome_text)
        return

    # 2. Telegram Link handler
    if "t.me/" in text:
        if not status_info["user_connected"]:
            await send_text_msg(session, chat_id, "⚠️ User session abhi connect nahi hai. Kripya thoda wait karein ya logs check karein.")
            return

        resp = await send_text_msg(session, chat_id, "⏳ **Link process ho raha hai...**")
        status_msg_id = resp.get("result", {}).get("message_id") if resp else None

        thumb_file = prepare_thumbnail()

        try:
            clean_text = text.split("?")[0].strip()
            parts = clean_text.split("/")
            last_part = parts[-1]

            if "-" in last_part:
                start_id, end_id = map(int, last_part.split("-"))
            else:
                start_id = end_id = int(last_part)

            if "/c/" in clean_text:
                source_chat_id = int("-100" + parts[-2])
            else:
                source_chat_id = parts[-2]

            total_msgs = (end_id - start_id) + 1
            if total_msgs > 100:
                if status_msg_id:
                    await edit_text_msg(session, chat_id, status_msg_id, "⚠️ Ek baar me maximum 100 messages hi save kar sakte hain!")
                return

            saved_count = 0
            for curr_id in range(start_id, end_id + 1):
                try:
                    status_text = f"📥 **Downloading message [{curr_id}/{end_id}]...**" if total_msgs > 1 else "📥 **Restricted file download ho rahi hai...**"
                    if status_msg_id:
                        await edit_text_msg(session, chat_id, status_msg_id, status_text)

                    # Fetch message using user session
                    target_msg = await user_app.get_messages(source_chat_id, curr_id)
                    if not target_msg or target_msg.empty:
                        continue

                    final_caption = format_caption(target_msg.caption)

                    if target_msg.media:
                        file_path = await user_app.download_media(target_msg)
                        if not file_path:
                            continue

                        if status_msg_id:
                            await edit_text_msg(session, chat_id, status_msg_id, "📤 **Aapki chat me upload ho raha hai...**")

                        # Send via Pyrogram bot_app (supports up to 2GB)
                        try:
                            if target_msg.video:
                                await bot_app.send_video(chat_id, video=file_path, caption=final_caption, thumb=thumb_file)
                            elif target_msg.document:
                                await bot_app.send_document(chat_id, document=file_path, caption=final_caption, thumb=thumb_file)
                            elif target_msg.photo:
                                await bot_app.send_photo(chat_id, photo=file_path, caption=final_caption)
                            elif target_msg.audio:
                                await bot_app.send_audio(chat_id, audio=file_path, caption=final_caption)
                            elif target_msg.voice:
                                await bot_app.send_voice(chat_id, voice=file_path, caption=final_caption)
                        except Exception as upload_err:
                            print(f"bot_app upload error: {upload_err}. Trying user_app upload...")
                            # Fallback upload via user_app
                            if target_msg.video:
                                await user_app.send_video(chat_id, video=file_path, caption=final_caption, thumb=thumb_file)
                            elif target_msg.document:
                                await user_app.send_document(chat_id, document=file_path, caption=final_caption, thumb=thumb_file)
                            elif target_msg.photo:
                                await user_app.send_photo(chat_id, photo=file_path, caption=final_caption)

                        if os.path.exists(file_path):
                            os.remove(file_path)
                        saved_count += 1

                    elif target_msg.text:
                        await send_text_msg(session, chat_id, format_caption(target_msg.text))
                        saved_count += 1

                    await asyncio.sleep(1)

                except FloodWait as fw:
                    wait_sec = fw.value + 2
                    if status_msg_id:
                        await edit_text_msg(session, chat_id, status_msg_id, f"⏳ Telegram FloodWait: {wait_sec}s wait kar rahe hain...")
                    await asyncio.sleep(wait_sec)
                except Exception as inner_err:
                    print(f"Error on msg {curr_id}: {inner_err}")

            if saved_count > 0:
                if status_msg_id:
                    await call_bot_api(session, "deleteMessage", {"chat_id": chat_id, "message_id": status_msg_id})
            else:
                if status_msg_id:
                    await edit_text_msg(session, chat_id, status_msg_id, "❌ Message ya media nahi mila! Check karein ki aapka account channel me joined hai.")

        except Exception as e:
            if status_msg_id:
                await edit_text_msg(session, chat_id, status_msg_id, f"⚠️ Error: `{str(e)}`")
        return

    # 3. Default fallback
    await send_text_msg(session, chat_id, "💡 Kripya kisi restricted Telegram post ka link bhejein, jaise:\n`https://t.me/c/3863573134/31`")


# --- Rock-solid HTTP Bot API Polling Loop ---
async def bot_polling_loop():
    print("Starting Telegram Bot API HTTP Polling Loop...")
    offset = 0
    timeout_client = aiohttp.ClientTimeout(total=45)

    async with aiohttp.ClientSession(timeout=timeout_client) as session:
        # Get bot info
        me_resp = await call_bot_api(session, "getMe")
        if me_resp and me_resp.get("ok"):
            status_info["bot_name"] = me_resp["result"]["username"]
            print(f"✅ Bot API Poller connected as @{status_info['bot_name']}")

        while True:
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
                payload = {"offset": offset, "timeout": 20}
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            if "message" in update:
                                asyncio.create_task(handle_message(session, update["message"]))
                    else:
                        await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Polling warning: {e}")
                await asyncio.sleep(2)


# --- Main Entry Point ---
async def main():
    # 1. Connect user session (for downloading restricted media)
    try:
        print("Connecting User Account Session...")
        await user_app.start()
        user_me = await user_app.get_me()
        status_info["user_connected"] = True
        status_info["user_name"] = user_me.first_name
        print(f"✅ User account connected: {user_me.first_name} (@{user_me.username})")
    except Exception as e:
        print(f"❌ User session connection error: {e}")

    # 2. Start bot_app (for sending up to 2GB media to users)
    try:
        print("Connecting Pyrogram bot_app...")
        await bot_app.start()
        print("✅ bot_app started for media uploads!")
    except Exception as e:
        print(f"⚠️ bot_app MTProto warning: {e}")

    # 3. Start guaranteed HTTP Polling Loop
    status_info["last_activity"] = "Bot is LIVE and listening for messages!"
    await bot_polling_loop()

if __name__ == "__main__":
    asyncio.run(main())
