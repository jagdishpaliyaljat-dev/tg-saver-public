import os
import base64
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client
from pyrogram.errors import FloodWait

PORT = int(os.environ.get("PORT", "8080"))

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Telegram Saver Bot is running 24/7!")
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

API_ID = int(os.environ.get("API_ID", "28220028"))
API_HASH = os.environ.get("API_HASH", "2644b27a6f3bff5dea5d09e657b01a5f")

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

# Custom Caption and Thumbnail configuration
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

app = Client("koyeb_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

async def start_transfer():
    await app.start()
    print("Telegram account connected successfully!")
    print("Loading dialogs...")
    async for _ in app.get_dialogs(limit=50):
        pass

    thumb_file = prepare_thumbnail()
    if thumb_file:
        print(f"Using custom thumbnail: {thumb_file}")

    print(f"Transfer started: From message {START_MSG_ID} to {END_MSG_ID}")
    total_saved = 0

    for msg_id in range(START_MSG_ID, END_MSG_ID + 1):
        try:
            msg = await app.get_messages(SOURCE_CHAT, msg_id)
            if not msg or msg.empty:
                continue

            if msg.video or msg.document or msg.photo:
                final_caption = format_caption(msg.caption)
                print(f"[{msg_id}/{END_MSG_ID}] Downloading...")
                file_path = await app.download_media(msg)
                if not file_path:
                    continue

                print(f"[{msg_id}/{END_MSG_ID}] Uploading to destination channel...")
                if msg.video:
                    await app.send_video(DESTINATION_CHAT, video=file_path, caption=final_caption, thumb=thumb_file)
                elif msg.document:
                    await app.send_document(DESTINATION_CHAT, document=file_path, caption=final_caption, thumb=thumb_file)
                elif msg.photo:
                    await app.send_photo(DESTINATION_CHAT, photo=file_path, caption=final_caption)

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
    await app.stop()

if __name__ == "__main__":
    asyncio.run(start_transfer())
