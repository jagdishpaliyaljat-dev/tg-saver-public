import os
import base64
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait
from pyrogram.types import Message

# --- Render Port & Health Server ---
PORT = int(os.environ.get("PORT", "8080"))

bot_status_info = {
    "bot_connected": False,
    "bot_username": None,
    "user_connected": False,
    "user_name": None,
    "error": None
}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""
        <html>
        <head><title>Telegram Saver Bot Status</title></head>
        <body style="font-family: sans-serif; padding: 20px; line-height: 1.6;">
            <h2>🚀 Telegram Restricted Content Saver Bot</h2>
            <hr>
            <p><b>Bot Client:</b> {"✅ Connected (@" + str(bot_status_info['bot_username']) + ")" if bot_status_info['bot_connected'] else "❌ Disconnected / Invalid BOT_TOKEN"}</p>
            <p><b>User Session:</b> {"✅ Connected (" + str(bot_status_info['user_name']) + ")" if bot_status_info['user_connected'] else "❌ Disconnected"}</p>
            {"<p style='color:red;'><b>Error:</b> " + str(bot_status_info['error']) + "</p>" if bot_status_info['error'] else ""}
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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip().strip('"').strip("'")

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

source_val = os.environ.get("SOURCE_CHAT", "-1003863573134")
try:
    SOURCE_CHAT = int(source_val)
except ValueError:
    SOURCE_CHAT = source_val

dest_val = os.environ.get("DESTINATION_CHAT", "-1004406877280")
try:
    DESTINATION_CHAT = int(dest_val)
except ValueError:
    DESTINATION_CHAT = dest_val

START_MSG_ID = int(os.environ.get("START_MSG_ID", "1"))
END_MSG_ID = int(os.environ.get("END_MSG_ID", "3572"))
AUTO_TRANSFER = os.environ.get("AUTO_TRANSFER", "false").lower() == "true"

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
            print(f"Failed to download custom thumbnail: {e}")
    if os.path.exists(CUSTOM_THUMBNAIL_PATH):
        return CUSTOM_THUMBNAIL_PATH
    return None

# User client (Always initialized for fetching restricted media)
user_app = Client("user_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# Bot client (Always initialized to listen for user commands)
# If BOT_TOKEN is empty in env, we create client conditionally
bot_app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN) if BOT_TOKEN else None


# --- Bot Message Handlers ---
if bot_app:
    @bot_app.on_message(filters.command("start") & filters.private)
    async def start_command(client, message: Message):
        user_name = message.from_user.first_name if message.from_user else "User"
        
        status_line = "✅ **User Session:** Connected" if bot_status_info["user_connected"] else "⚠️ **User Session:** Disconnected"
        
        welcome_text = (
            f"👋 **Namaste {user_name}!**\n\n"
            "Main **Save Restricted Content Bot** hoon.\n\n"
            f"{status_line}\n\n"
            "📌 **Kaise use karein:**\n"
            "Mujhe kisi bhi Telegram post ka link bhejo:\n\n"
            "• **Single post:** `https://t.me/c/1234567890/42`\n"
            "• **Multiple posts (Range):** `https://t.me/c/1234567890/42-45`\n\n"
            "⚡ *Restricted / Protected files download hokar aapko mil jayengi!*"
        )
        await message.reply_text(welcome_text)

    @bot_app.on_message(filters.text & filters.private)
    async def link_handler(client, message: Message):
        text = message.text.strip()
        if "t.me/" not in text:
            await message.reply_text("❌ Kripya valid Telegram post link bhejein.\nExample: `https://t.me/c/1234567890/100`")
            return

        if not bot_status_info["user_connected"]:
            await message.reply_text("⚠️ User session connect nahi hai! Kripya Render logs ya session string check karein.")
            return

        status_msg = await message.reply_text("⏳ Processing link...")
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
                chat_id = int("-100" + parts[-2])
            else:
                chat_id = parts[-2]

            total_msgs = (end_id - start_id) + 1
            if total_msgs > 100:
                await status_msg.edit_text("⚠️ Ek baar me maximum 100 messages process kar sakte hain!")
                return

            saved_count = 0
            for curr_id in range(start_id, end_id + 1):
                try:
                    if total_msgs > 1:
                        await status_msg.edit_text(f"📥 Downloading message [{curr_id}/{end_id}]...")
                    else:
                        await status_msg.edit_text("📥 Content download ho raha hai...")

                    target_msg = await user_app.get_messages(chat_id, curr_id)
                    if not target_msg or target_msg.empty:
                        continue

                    final_caption = format_caption(target_msg.caption)

                    if target_msg.media:
                        file_path = await user_app.download_media(target_msg)
                        if not file_path:
                            continue

                        await status_msg.edit_text("📤 Upload ho raha hai...")

                        if target_msg.video:
                            await client.send_video(message.chat.id, video=file_path, caption=final_caption, thumb=thumb_file)
                        elif target_msg.document:
                            await client.send_document(message.chat.id, document=file_path, caption=final_caption, thumb=thumb_file)
                        elif target_msg.photo:
                            await client.send_photo(message.chat.id, photo=file_path, caption=final_caption)
                        elif target_msg.audio:
                            await client.send_audio(message.chat.id, audio=file_path, caption=final_caption)
                        elif target_msg.voice:
                            await client.send_voice(message.chat.id, voice=file_path, caption=final_caption)

                        if os.path.exists(file_path):
                            os.remove(file_path)
                        saved_count += 1

                    elif target_msg.text:
                        await client.send_message(message.chat.id, text=format_caption(target_msg.text))
                        saved_count += 1

                    await asyncio.sleep(1)

                except FloodWait as fw:
                    await status_msg.edit_text(f"⏳ Telegram FloodWait: {fw.value}s wait kar rahe hain...")
                    await asyncio.sleep(fw.value + 2)
                except Exception as inner_err:
                    print(f"Error on message {curr_id}: {inner_err}")

            if saved_count > 0:
                await status_msg.delete()
            else:
                await status_msg.edit_text("❌ Koi content nahi mila. Kripya check karein ki aapka account us channel me joined hai!")

        except Exception as e:
            await status_msg.edit_text(f"⚠️ Error: `{str(e)}`")


# --- Automated Channel Batch Transfer (Optional) ---
async def start_transfer():
    print(f"Auto-Transfer started: From message {START_MSG_ID} to {END_MSG_ID}")
    total_saved = 0
    thumb_file = prepare_thumbnail()

    for msg_id in range(START_MSG_ID, END_MSG_ID + 1):
        try:
            msg = await user_app.get_messages(SOURCE_CHAT, msg_id)
            if not msg or msg.empty:
                continue

            if msg.video or msg.document or msg.photo:
                final_caption = format_caption(msg.caption)
                print(f"[{msg_id}/{END_MSG_ID}] Downloading...")
                file_path = await user_app.download_media(msg)
                if not file_path:
                    continue

                print(f"[{msg_id}/{END_MSG_ID}] Uploading to destination channel...")
                if msg.video:
                    await user_app.send_video(DESTINATION_CHAT, video=file_path, caption=final_caption, thumb=thumb_file)
                elif msg.document:
                    await user_app.send_document(DESTINATION_CHAT, document=file_path, caption=final_caption, thumb=thumb_file)
                elif msg.photo:
                    await user_app.send_photo(DESTINATION_CHAT, photo=file_path, caption=final_caption)

                total_saved += 1
                if os.path.exists(file_path):
                    os.remove(file_path)

                print(f"[{msg_id}] Done! (Total transferred: {total_saved})")
                await asyncio.sleep(2)
        except FloodWait as e:
            print(f"FloodWait: sleeping {e.value} seconds...")
            await asyncio.sleep(e.value + 5)
        except Exception as e:
            print(f"Error on msg {msg_id}: {e}")

    print(f"All done! Total {total_saved} files transferred.")


# --- Main Runner ---
async def main():
    # 1. Start Bot Client FIRST (guarantees bot is alive and responds to /start)
    if bot_app:
        try:
            print("Starting Telegram Bot (@BotFather token)...")
            await bot_app.start()
            bot_me = await bot_app.get_me()
            bot_status_info["bot_connected"] = True
            bot_status_info["bot_username"] = bot_me.username
            print(f"✅ Bot successfully started as @{bot_me.username} (ID: {bot_me.id})")
        except Exception as e:
            bot_status_info["error"] = f"Bot Start Error: {e}"
            print(f"❌ Error starting bot_app: {e}")
    else:
        print("⚠️ NOTE: BOT_TOKEN is missing or empty in Environment Variables!")
        print("Render me Environment tab me jakar BOT_TOKEN key zaroor add karein.")

    # 2. Start User Client (in separate try block so it NEVER crashes bot)
    try:
        print("Connecting Telegram User Session...")
        await user_app.start()
        user_me = await user_app.get_me()
        bot_status_info["user_connected"] = True
        bot_status_info["user_name"] = user_me.first_name
        print(f"✅ User account connected: {user_me.first_name} (@{user_me.username})")
        
        async for _ in user_app.get_dialogs(limit=20):
            pass
    except Exception as e:
        bot_status_info["error"] = f"User Session Error: {e}"
        print(f"❌ User session failed to connect: {e}")
        print("Check if SESSION_STRING is valid and account is active.")

    if AUTO_TRANSFER and bot_status_info["user_connected"]:
        asyncio.create_task(start_transfer())

    print("⚡ System is running. Waiting for events...")
    await idle()

if __name__ == "__main__":
    asyncio.run(main())
