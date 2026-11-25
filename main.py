import os
import re
import time
import math
import base64
import asyncio
import threading
import aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, raw
from pyrogram.errors import FloodWait

# Ensure an asyncio event loop exists in MainThread for Pyrogram
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# --- Render Port & Health Server ---
PORT = int(os.environ.get("PORT", "8080"))

status_info = {
    "bot_name": None,
    "user_name": None,
    "user_connected": False,
    "tgcrypto": "⏳ Checking...",
    "last_activity": "Starting up..."
}

try:
    import tgcrypto
    status_info["tgcrypto"] = "✅ Active (Hardware C-Acceleration 50x-100x Faster)"
    print("🚀 Hardware Accelerated TgCrypto is ACTIVE! Maximum upload/download speed enabled.")
except ImportError:
    status_info["tgcrypto"] = "⚠️ Missing (Slow Pure-Python)"
    print("⚠️ TgCrypto missing, running in slow pure-python mode.")

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
            <p><b>Speed Acceleration:</b> {status_info['tgcrypto']}</p>
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

# Destination Channel Mapping
default_dest = os.environ.get("DESTINATION_CHAT", "").strip()
try:
    DEFAULT_DESTINATION = int(default_dest) if default_dest else None
except ValueError:
    DEFAULT_DESTINATION = default_dest

user_destinations = {}
stop_batch_flags = {}

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

def format_caption(original_caption: str, user_id: int = None) -> str:
    caption = original_caption or ""
    active_footer = user_destinations.get(f"caption_{user_id}", CUSTOM_FOOTER) if user_id else CUSTOM_FOOTER
    if active_footer:
        if caption:
            caption = f"{caption}\n\n{active_footer}"
        else:
            caption = active_footer
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

# Pyrogram Clients with multiple workers and auto-flood handling
user_app = Client("user_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING, workers=16, sleep_threshold=60)
bot_app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=16, sleep_threshold=60)


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


# Safe message fetch with automatic peer resolving cache
async def get_target_message_safe(chat_id, msg_id):
    try:
        return await user_app.get_messages(chat_id, msg_id)
    except Exception as e:
        print(f"Initial get_messages for {chat_id} msg {msg_id} failed: {e}. Resolving peer cache...")
        try:
            async for dialog in user_app.get_dialogs(limit=50):
                if dialog.chat and dialog.chat.id == chat_id:
                    break
        except Exception as d_err:
            print(f"Dialog cache scan error: {d_err}")
        return await user_app.get_messages(chat_id, msg_id)


# --- High-Speed Hardware-Accelerated Media Upload (up to 2 GB) ---
async def upload_media_file(
    session: aiohttp.ClientSession,
    target_chat_id: int,
    file_path: str,
    media_type: str,
    caption: str,
    thumb_file: str,
    status_msg_id: int,
    user_chat_id: int,
    curr_id: int = 0,
    end_id: int = 0
):
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)
    print(f"Uploading {media_type} ({file_size_mb:.2f} MB) to {target_chat_id}...")

    # Strategy 1: Files <= 49 MB use Fast HTTP Bot API (instant, bypasses MTProto)
    if file_size_mb <= 49.0:
        try:
            method_map = {
                "video": "sendVideo",
                "photo": "sendPhoto",
                "audio": "sendAudio",
                "voice": "sendVoice",
                "document": "sendDocument"
            }
            method = method_map.get(media_type, "sendDocument")
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

            form = aiohttp.FormData()
            form.add_field("chat_id", str(target_chat_id))
            if caption:
                form.add_field("caption", caption)
                form.add_field("parse_mode", "Markdown")

            field_name = "video" if media_type == "video" else ("photo" if media_type == "photo" else ("audio" if media_type == "audio" else ("voice" if media_type == "voice" else "document")))
            form.add_field(field_name, open(file_path, "rb"), filename=os.path.basename(file_path))

            if thumb_file and os.path.exists(thumb_file) and media_type in ["video", "document"]:
                form.add_field("thumb", open(thumb_file, "rb"), filename="thumb.jpg")

            async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                res_data = await resp.json()
                if res_data and res_data.get("ok"):
                    print("✅ Fast HTTP Bot API upload succeeded!")
                    return True
                else:
                    print(f"HTTP upload non-ok: {res_data}. Trying Pyrogram MTProto...")
        except Exception as http_err:
            print(f"HTTP upload error: {http_err}. Trying Pyrogram MTProto...")

    # Strategy 2: Ultra Fast Hardware-Accelerated MTProto Stream Upload (up to 2 GB)
    start_up = time.time()
    last_update = [0]

    async def progress_cb(current, total):
        now = time.time()
        if now - last_update[0] >= 3.0:
            last_update[0] = now
            pct = int((current / total) * 100) if total > 0 else 0
            c_mb = current / (1024 * 1024)
            t_mb = total / (1024 * 1024)
            elapsed = now - start_up
            speed_mb = (c_mb / elapsed) if elapsed > 0 else 0
            eta_sec = int((t_mb - c_mb) / speed_mb) if speed_mb > 0 else 0

            header = f"📤 **Uploading Msg [{curr_id}/{end_id}]:** `{pct}%`" if curr_id else f"📤 **Uploading Media:** `{pct}%`"
            if status_msg_id:
                asyncio.create_task(edit_text_msg(
                    session,
                    user_chat_id,
                    status_msg_id,
                    f"{header}\n"
                    f"📊 **Size:** `{c_mb:.1f} MB / {t_mb:.1f} MB`\n"
                    f"⚡ **Speed:** `{speed_mb:.1f} MB/s` | ⏳ **ETA:** `{eta_sec}s`\n"
                    f"🎯 **Target:** `{target_chat_id}`\n\n"
                    f"✋ *Rukne ke liye* **/stop** *likhein.*"
                ))

    # Determine clients to try: prefer bot_app, fallback to user_app (or vice versa)
    clients_to_try = []
    if bot_app and bot_app.is_connected:
        clients_to_try.append(bot_app)
    if user_app and user_app.is_connected and user_app not in clients_to_try:
        clients_to_try.append(user_app)

    if not clients_to_try:
        raise RuntimeError("No connected Pyrogram client available for upload!")

    last_exc = None
    for client in clients_to_try:
        try:
            print(f"Attempting upload via {client.name}...")
            thumb_arg = thumb_file if (thumb_file and os.path.exists(thumb_file)) else None
            if media_type == "video":
                await client.send_video(
                    target_chat_id,
                    video=file_path,
                    caption=caption,
                    thumb=thumb_arg,
                    supports_streaming=True,
                    progress=progress_cb
                )
            elif media_type == "document":
                await client.send_document(
                    target_chat_id,
                    document=file_path,
                    caption=caption,
                    thumb=thumb_arg,
                    progress=progress_cb
                )
            elif media_type == "photo":
                await client.send_photo(
                    target_chat_id,
                    photo=file_path,
                    caption=caption,
                    progress=progress_cb
                )
            elif media_type == "audio":
                await client.send_audio(
                    target_chat_id,
                    audio=file_path,
                    caption=caption,
                    thumb=thumb_arg,
                    progress=progress_cb
                )
            elif media_type == "voice":
                await client.send_voice(
                    target_chat_id,
                    voice=file_path,
                    caption=caption,
                    progress=progress_cb
                )
            else:
                await client.send_document(
                    target_chat_id,
                    document=file_path,
                    caption=caption,
                    thumb=thumb_arg,
                    progress=progress_cb
                )
            print(f"✅ Successfully uploaded via {client.name}!")
            return True
        except Exception as e:
            print(f"⚠️ Upload via {client.name} failed: {e}")
            last_exc = e

    if last_exc:
        raise last_exc
    return False


# --- Handle Incoming Message ---
async def handle_message(session: aiohttp.ClientSession, msg: dict):
    chat_id = msg["chat"]["id"]
    from_user = msg.get("from", {})
    from_id = from_user.get("id", chat_id)
    text = msg.get("text", "").strip()
    user_name = from_user.get("first_name", "Friend")

    status_info["last_activity"] = f"Message from {user_name} ({chat_id})"
    print(f"📩 Incoming from {user_name} ({chat_id}): {text}")

    # Check if a message was forwarded from a channel to set destination
    if "forward_from_chat" in msg:
        fwd_chat = msg["forward_from_chat"]
        if fwd_chat.get("type") in ["channel", "supergroup", "group"]:
            target_id = fwd_chat["id"]
            target_title = fwd_chat.get("title", str(target_id))
            user_destinations[from_id] = target_id
            await send_text_msg(
                session,
                chat_id,
                f"✅ **Destination Set Ho Gaya!**\n\n"
                f"📢 **Channel:** `{target_title}`\n"
                f"🆔 **ID:** `{target_id}`\n\n"
                f"Ab aap jo bhi restricted link bhejenge, wo seedhe is channel me upload hoga! 🚀"
            )
            return

    # Check if a photo was sent to the bot -> Set as Custom Thumbnail!
    if "photo" in msg:
        photo_list = msg["photo"]
        best_photo = photo_list[-1]  # Highest resolution
        file_id = best_photo["file_id"]

        f_info = await call_bot_api(session, "getFile", {"file_id": file_id})
        if f_info and f_info.get("ok"):
            f_path = f_info["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f_path}"
            async with session.get(download_url) as img_resp:
                if img_resp.status == 200:
                    with open(CUSTOM_THUMBNAIL_PATH, "wb") as f:
                        f.write(await img_resp.read())
                    await send_text_msg(
                        session,
                        chat_id,
                        "🖼️ **Custom Thumbnail Set Ho Gaya!**\n\n"
                        "Ab se sabhi forwarded videos par yeh thumbnail lag kar aayega! 🚀\n\n"
                        "• Thumbnail dekhne ke liye: `/showthumb`\n"
                        "• Thumbnail hatane ke liye: `/delthumb`"
                    )
                    return

    # 1. /start command
    if text.startswith("/start"):
        session_status = "✅ Connected" if status_info["user_connected"] else "⚠️ Disconnected"
        curr_dest = user_destinations.get(from_id, DEFAULT_DESTINATION)
        dest_display = f"`{curr_dest}`" if curr_dest else "Private Chat (PM)"
        has_thumb = "✅ Set Hai" if os.path.exists(CUSTOM_THUMBNAIL_PATH) else "❌ Default"

        welcome_text = (
            f"👋 **Namaste {user_name}!**\n\n"
            "Main **Save Restricted Content Bot** hoon.\n\n"
            f"⚡ **User Session (Ananya):** {session_status}\n"
            f"🎯 **Destination:** {dest_display}\n"
            f"🖼️ **Thumbnail:** {has_thumb}\n\n"
            "📌 **Commands Menu:**\n"
            "• `/help` - Poora guide aur examples\n"
            "• `/caption` - Custom caption footer badlein\n"
            "• `/showthumb` - Current thumbnail dekhein\n"
            "• `/delthumb` - Thumbnail delete karein\n"
            "• `/channels` - Joined channels ki list\n"
            "• `/status` - Bot aur server status\n"
            "• `/mychat` - Active destination channel\n"
            "• `/clearchat` - Private chat me reset karein\n\n"
            "💡 **Thumbnail Set Karna:** Mujhe seedhe koi bhi **Photo** send karein!\n"
            "💡 **Caption Badlna:** `/caption 👤 By: @ID | 📢 Channel: @Channel`"
        )
        await send_text_msg(session, chat_id, welcome_text)
        return

    # 2. /showthumb command
    if text.startswith("/showthumb"):
        if os.path.exists(CUSTOM_THUMBNAIL_PATH):
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            form = aiohttp.FormData()
            form.add_field("chat_id", str(chat_id))
            form.add_field("caption", "🖼️ **Aapka Current Active Thumbnail**\n\nIse hatane ke liye `/delthumb` likhein.")
            form.add_field("photo", open(CUSTOM_THUMBNAIL_PATH, "rb"))
            await session.post(url, data=form)
        else:
            await send_text_msg(session, chat_id, "ℹ️ Abhi koi custom thumbnail set nahi hai.\n\nNaya thumbnail lagane ke liye mujhe koi bhi **Photo** bhejein!")
        return

    # 3. /delthumb command
    if text.startswith("/delthumb"):
        if os.path.exists(CUSTOM_THUMBNAIL_PATH):
            os.remove(CUSTOM_THUMBNAIL_PATH)
            await send_text_msg(session, chat_id, "🗑️ **Custom thumbnail delete ho gaya!**\nAb videos par unka original default thumbnail aayega.")
        else:
            await send_text_msg(session, chat_id, "ℹ️ Koi custom thumbnail set nahi tha.")
        return

    # 4. /help command
    if text.startswith("/help"):
        help_text = (
            "📖 **Telegram Restricted Saver Bot Guide:**\n\n"
            "🖼️ **1. Thumbnail Kaise Badlein?**\n"
            "• Bot ko chat me koi bhi **Photo** bhejein. Bot use automatically thumbnail bana dega!\n"
            "• `/showthumb` - Active thumbnail dekhne ke liye\n"
            "• `/delthumb` - Thumbnail hatane ke liye\n\n"
            "✍️ **2. Caption Kaise Badlein?**\n"
            "• Command likhein: `/caption 👤 By: @YourID | 📢 Channel: @YourChannel`\n"
            "• Check karne ke liye: `/caption`\n"
            "• Reset karne ke liye: `/caption reset`\n\n"
            "🚀 **3. Files Forward Karna:**\n"
            "• Channel ke sabse upar wale message ka link bhejein: `https://t.me/c/3863573134/1`\n"
            "• Bot automatically continuous batch shuru kar dega!\n"
            "• Rokne ke liye: `/stop`"
        )
        await send_text_msg(session, chat_id, help_text)
        return

    # 5. /status command
    if text.startswith("/status"):
        session_status = "✅ Connected (Ananya)" if status_info["user_connected"] else "❌ Disconnected"
        curr_dest = user_destinations.get(from_id, DEFAULT_DESTINATION)
        dest_display = f"`{curr_dest}`" if curr_dest else "Private Chat"
        has_thumb = "✅ Custom Set Hai" if os.path.exists(CUSTOM_THUMBNAIL_PATH) else "❌ Default"
        curr_cap = user_destinations.get(f"caption_{from_id}", CUSTOM_FOOTER or "Default")

        status_msg = (
            "⚡ **Live System Status:**\n\n"
            f"• **Bot Client:** ✅ Active (@{status_info['bot_name']})\n"
            f"• **User Account:** {session_status}\n"
            f"• **Destination:** {dest_display}\n"
            f"• **Thumbnail:** {has_thumb}\n"
            f"• **Caption Footer:** `{curr_cap}`\n"
            f"• **Port:** {PORT} (24/7 Alive)\n"
            f"• **Last Activity:** {status_info['last_activity']}\n"
        )
        await send_text_msg(session, chat_id, status_msg)
        return

    # 6. /caption command
    if text.startswith("/caption"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            new_caption = parts[1].strip()
            if new_caption.lower() == "reset":
                if f"caption_{from_id}" in user_destinations:
                    del user_destinations[f"caption_{from_id}"]
                await send_text_msg(session, chat_id, "✅ Caption footer reset ho gaya default par!")
            else:
                user_destinations[f"caption_{from_id}"] = new_caption
                await send_text_msg(
                    session,
                    chat_id,
                    f"✅ **Naya Caption Footer Set Ho Gaya!**\n\n`{new_caption}`\n\nAb se har video aur file ke caption ke niche yeh line jud kar aayegi! 🚀"
                )
        else:
            curr_cap = user_destinations.get(f"caption_{from_id}", CUSTOM_FOOTER or "Default")
            await send_text_msg(
                session,
                chat_id,
                f"✍️ **Current Caption Footer:**\n\n`{curr_cap}`\n\n"
                "📌 **Change karne ke liye:**\n`/caption Aapka Naya Footer Text`\n\n"
                "📌 **Example:**\n`/caption 👤 By: @YourID | 📢 Channel: @YourChannel`\n\n"
                "📌 **Reset karne ke liye:**\n`/caption reset`"
            )
        return

    # 2. /channels command (Lists all channels Ananya account is joined in)
    if text.startswith("/channels") or text.startswith("/check"):
        wait_msg = await send_text_msg(session, chat_id, "🔍 Ananya account ke joined channels scan ho rahe hain...")
        wait_id = wait_msg.get("result", {}).get("message_id") if wait_msg else None

        channels_list = []
        try:
            async for dialog in user_app.get_dialogs(limit=30):
                if dialog.chat and dialog.chat.type in ["channel", "supergroup"]:
                    title = dialog.chat.title or "Untitled"
                    cid = dialog.chat.id
                    channels_list.append(f"• **{title}** (`{cid}`)")
            
            if channels_list:
                result_text = "📋 **Aapka User Account (Ananya) in channels me joined hai:**\n\n" + "\n".join(channels_list[:20])
            else:
                result_text = "⚠️ Ananya account kisi bhi channel me joined nahi mila."
        except Exception as ch_err:
            result_text = f"❌ Error loading channels: `{ch_err}`"

        if wait_id:
            await edit_text_msg(session, chat_id, wait_id, result_text)
        else:
            await send_text_msg(session, chat_id, result_text)
        return

    # 3. /setchat command
    if text.startswith("/setchat"):
        parts = text.split()
        if len(parts) > 1:
            try:
                ch_id = int(parts[1])
            except ValueError:
                ch_id = parts[1]
            user_destinations[from_id] = ch_id
            await send_text_msg(session, chat_id, f"✅ Destination channel set to: `{ch_id}`!\nAb saari files is channel me upload hongi.")
        else:
            await send_text_msg(session, chat_id, "Usage: `/setchat -100xxxxxxxxxx` ya channel se koi post mujhe forward karein.")
        return

    # 4. /mychat command
    if text.startswith("/mychat"):
        curr_dest = user_destinations.get(from_id, DEFAULT_DESTINATION)
        if curr_dest:
            await send_text_msg(session, chat_id, f"🎯 Abhi saara content channel `{curr_dest}` me upload ho raha hai.\nPrivate chat me paane ke liye `/clearchat` likhein.")
        else:
            await send_text_msg(session, chat_id, "🎯 Abhi content aapki Private Chat (PM) me aa raha hai.\nChannel me bhejne ke liye channel se koi bhi post yahan forward karein.")
        return

    # 5. /clearchat command
    if text.startswith("/clearchat"):
        if from_id in user_destinations:
            del user_destinations[from_id]
        await send_text_msg(session, chat_id, "✅ Destination reset ho gaya! Ab files aapki Private Chat me aayengi.")
        return

    # 6. /stop command (Stops active continuous batch)
    if text.startswith("/stop"):
        stop_batch_flags[from_id] = True
        await send_text_msg(session, chat_id, "🛑 **Batch transfer rokne ka signal bhej diya gaya hai!**\nAbhi process ho rahi file ke baad transfer stop ho jayega.")
        return

    # 7. Telegram Link handler (Auto Continuous Batch Forwarding)
    if "t.me/" in text:
        if not status_info["user_connected"]:
            await send_text_msg(session, chat_id, "⚠️ User session abhi connect nahi hai. Kripya thoda wait karein ya logs check karein.")
            return

        target_destination = user_destinations.get(from_id, DEFAULT_DESTINATION or chat_id)
        stop_batch_flags[from_id] = False

        resp = await send_text_msg(session, chat_id, "⏳ **Channel detect ho raha hai aur batch taiyar ho raha hai...**")
        status_msg_id = resp.get("result", {}).get("message_id") if resp else None

        thumb_file = prepare_thumbnail()

        try:
            clean_text = text.split("?")[0].strip()
            parts = clean_text.split("/")
            last_part = parts[-1]

            if "/c/" in clean_text:
                source_chat_id = int("-100" + parts[-2])
            else:
                source_chat_id = parts[-2]

            # Check if user specified a manual range (e.g. 10-50) or single starting link
            if "-" in last_part:
                start_id, end_id = map(int, last_part.split("-"))
                is_auto_continuous = False
            else:
                start_id = int(last_part)
                is_auto_continuous = True
                
                # Automatically detect the latest message ID in this channel
                latest_id = None
                try:
                    async for m in user_app.get_chat_history(source_chat_id, limit=1):
                        latest_id = m.id
                except Exception as hist_err:
                    print(f"History lookup error: {hist_err}")

                if latest_id and latest_id >= start_id:
                    end_id = latest_id
                else:
                    end_id = start_id + 3000  # Will auto-stop when channel ends

            dest_name = f"Channel (`{target_destination}`)" if target_destination != chat_id else "Private Chat"
            initial_text = (
                f"🚀 **Continuous Batch Transfer Shuru!**\n\n"
                f"📌 **Start Message:** `{start_id}`\n"
                f"🎯 **Target Message:** `{end_id}`\n"
                f"📤 **Upload Destination:** {dest_name}\n\n"
                f"✋ *Transfer kisi bhi waqt rokne ke liye* **/stop** *likhein.*"
            )
            if status_msg_id:
                await edit_text_msg(session, chat_id, status_msg_id, initial_text)

            saved_count = 0
            empty_streak = 0
            last_err_detail = None
            stopped_by_user = False

            for curr_id in range(start_id, end_id + 1):
                # 1. Check if user sent /stop command
                if stop_batch_flags.get(from_id):
                    stopped_by_user = True
                    print(f"Batch stopped by user {from_id} at msg {curr_id}")
                    break

                # 2. Check empty streak (channel ended)
                if empty_streak >= 30:
                    print(f"30 consecutive empty messages. Reached end of channel at {curr_id}.")
                    break

                try:
                    # Fetch message safely with peer caching
                    target_msg = await get_target_message_safe(source_chat_id, curr_id)
                    
                    if not target_msg or target_msg.empty:
                        empty_streak += 1
                        last_err_detail = f"Message #{curr_id} empty hai ya delete ho chuka hai."
                        continue

                    empty_streak = 0  # Reset empty streak on valid message
                    final_caption = format_caption(target_msg.caption, from_id)

                    if target_msg.media:
                        start_dl = time.time()
                        last_dl_time = [0]

                        async def dl_progress(current, total):
                            now = time.time()
                            if now - last_dl_time[0] >= 3.0:
                                last_dl_time[0] = now
                                pct = int((current / total) * 100) if total > 0 else 0
                                c_mb = current / (1024 * 1024)
                                t_mb = total / (1024 * 1024)
                                elapsed = now - start_dl
                                speed = (c_mb / elapsed) if elapsed > 0 else 0
                                eta = int((t_mb - c_mb) / speed) if speed > 0 else 0
                                if status_msg_id:
                                    asyncio.create_task(edit_text_msg(
                                        session,
                                        chat_id,
                                        status_msg_id,
                                        f"📥 **Downloading Msg [{curr_id}/{end_id}]**\n"
                                        f"📊 **Progress:** `{pct}%` (`{c_mb:.1f} MB / {t_mb:.1f} MB`)\n"
                                        f"⚡ **Speed:** `{speed:.1f} MB/s` | ⏳ **ETA:** `{eta}s`\n"
                                        f"🎯 **Upload to:** {dest_name}\n\n"
                                        f"✋ *Rukne ke liye* **/stop** *likhein.*"
                                    ))

                        file_path = await user_app.download_media(target_msg, progress=dl_progress)
                        if not file_path:
                            last_err_detail = f"Message {curr_id} media download fail hua."
                            continue

                        # Determine media type
                        if target_msg.video:
                            m_type = "video"
                        elif target_msg.photo:
                            m_type = "photo"
                        elif target_msg.audio:
                            m_type = "audio"
                        elif target_msg.voice:
                            m_type = "voice"
                        else:
                            m_type = "document"

                        # Upload to target destination using Fast HTTP or Pyrogram
                        try:
                            await upload_media_file(
                                session=session,
                                target_chat_id=target_destination,
                                file_path=file_path,
                                media_type=m_type,
                                caption=final_caption,
                                thumb_file=thumb_file,
                                status_msg_id=status_msg_id,
                                user_chat_id=chat_id,
                                curr_id=curr_id,
                                end_id=end_id
                            )
                            saved_count += 1
                        except Exception as upload_err:
                            last_err_detail = f"Upload error: {upload_err}"
                            print(f"Upload error on msg {curr_id}: {upload_err}")
                            if status_msg_id:
                                await edit_text_msg(session, chat_id, status_msg_id, f"⚠️ Message {curr_id} upload fail: `{upload_err}`")

                        if os.path.exists(file_path):
                            os.remove(file_path)

                    elif target_msg.text:
                        await send_text_msg(session, target_destination, format_caption(target_msg.text, from_id))
                        saved_count += 1

                    await asyncio.sleep(1.5)

                except FloodWait as fw:
                    wait_sec = fw.value + 3
                    if status_msg_id:
                        await edit_text_msg(session, chat_id, status_msg_id, f"⏳ Telegram FloodWait: {wait_sec}s wait kar rahe hain...")
                    await asyncio.sleep(wait_sec)
                except Exception as inner_err:
                    last_err_detail = str(inner_err)
                    print(f"Error on msg {curr_id}: {inner_err}")

            # Batch finished or stopped
            if stopped_by_user:
                if status_msg_id:
                    await edit_text_msg(
                        session,
                        chat_id,
                        status_msg_id,
                        f"🛑 **Batch Transfer Rok Diya Gaya!**\n\n"
                        f"📦 Total **{saved_count} file(s)** safaltapoorvak {dest_name} me bhej di gayi hain."
                    )
            elif saved_count > 0:
                if status_msg_id:
                    await edit_text_msg(
                        session,
                        chat_id,
                        status_msg_id,
                        f"🎉 **Complete Chat Transfer Ho Gayi Hai!** 🚀\n\n"
                        f"📌 Start: Message `{start_id}`\n"
                        f"📦 Total Transferred: **{saved_count} file(s)**\n"
                        f"🎯 Destination: {dest_name}"
                    )
            else:
                if status_msg_id:
                    err_upper = (last_err_detail or "").upper()
                    if "USER_NOT_PARTICIPANT" in err_upper or "CHANNEL_PRIVATE" in err_upper:
                        reason = "Aapka user account (**Ananya**) is private channel me joined nahi hai! Kripya pehle **Ananya** account ko is channel me add/join karein."
                    elif "PEER_ID_INVALID" in err_upper:
                        reason = f"Channel peer ID `{source_chat_id}` Telegram cache me nahi mila. `/channels` command chala kar check karein."
                    elif "EMPTY" in err_upper:
                        reason = f"Message link galat hai ya message delete ho chuka hai (ID: {start_id})."
                    else:
                        reason = last_err_detail or "Unknown error"

                    error_report = (
                        f"❌ **Content Fetch Nahi Hua!**\n\n"
                        f"🔍 **Reason:** `{reason}`\n\n"
                        f"📌 **Tip:** Bot me `/channels` likhein taaki Ananya ke joined channels check ho sakein."
                    )
                    await edit_text_msg(session, chat_id, status_msg_id, error_report)

        except Exception as e:
            if status_msg_id:
                await edit_text_msg(session, chat_id, status_msg_id, f"⚠️ Error: `{str(e)}`")
        return

    # Default fallback
    await send_text_msg(session, chat_id, "💡 Kripya kisi restricted Telegram post ka link bhejein, jaise:\n`https://t.me/c/3863573134/31`\n\nChannels check karne ke liye `/channels` likhein.")


# --- Handle Bot Added as Admin to Channel / Group ---
async def handle_chat_member_update(session: aiohttp.ClientSession, member_update: dict):
    try:
        chat_info = member_update.get("chat", {})
        new_status = member_update.get("new_chat_member", {}).get("status")
        from_user = member_update.get("from", {})
        from_id = from_user.get("id")

        if new_status in ["administrator", "member"] and from_id:
            ch_id = chat_info.get("id")
            ch_title = chat_info.get("title", str(ch_id))
            user_destinations[from_id] = ch_id
            print(f"🎉 Bot added as {new_status} in {ch_title} ({ch_id}) by user {from_id}")
            
            await send_text_msg(
                session,
                from_id,
                f"🎉 **Bot ko '{ch_title}' me add/admin banaya gaya hai!**\n\n"
                f"Ab aap bot ko jo bhi link bhejenge, saari files **`{ch_title}`** channel me upload hongi! 🚀"
            )
    except Exception as e:
        print(f"Error handling chat member update: {e}")


# --- Rock-solid HTTP Bot API Polling Loop ---
async def bot_polling_loop():
    print("Starting Telegram Bot API HTTP Polling Loop...")
    offset = 0
    timeout_client = aiohttp.ClientTimeout(total=45)

    async with aiohttp.ClientSession(timeout=timeout_client) as session:
        me_resp = await call_bot_api(session, "getMe")
        if me_resp and me_resp.get("ok"):
            status_info["bot_name"] = me_resp["result"]["username"]
            print(f"✅ Bot API Poller connected as @{status_info['bot_name']}")

        # Register official command menu with Telegram UI
        commands_payload = {
            "commands": [
                {"command": "start", "description": "🚀 Bot start & info"},
                {"command": "help", "description": "📖 Usage guide & examples"},
                {"command": "channels", "description": "📋 Joined channels list"},
                {"command": "status", "description": "⚡ Bot & server status"},
                {"command": "mychat", "description": "🎯 Active destination channel"},
                {"command": "setchat", "description": "⚙️ Set destination channel ID"},
                {"command": "clearchat", "description": "🔄 Reset to private chat"},
                {"command": "stop", "description": "🛑 Stop ongoing batch transfer"},
                {"command": "caption", "description": "✍️ Custom caption footer"},
                {"command": "showthumb", "description": "🖼️ View active thumbnail"},
                {"command": "delthumb", "description": "🗑️ Delete custom thumbnail"}
            ]
        }
        await call_bot_api(session, "setMyCommands", commands_payload)

        while True:
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
                payload = {
                    "offset": offset,
                    "timeout": 20,
                    "allowed_updates": ["message", "my_chat_member"]
                }
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            if "message" in update:
                                asyncio.create_task(handle_message(session, update["message"]))
                            elif "my_chat_member" in update:
                                asyncio.create_task(handle_chat_member_update(session, update["my_chat_member"]))
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

        # Cache initial dialog peers
        print("Pre-caching channels from dialogs...")
        try:
            async for _ in user_app.get_dialogs(limit=30):
                pass
            print("✅ Channel peers cached successfully!")
        except Exception as d_err:
            print(f"Initial dialog pre-cache warning: {d_err}")

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
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        pass
