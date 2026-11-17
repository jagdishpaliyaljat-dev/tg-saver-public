import os
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
SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()

SOURCE_CHAT = int(os.environ.get("SOURCE_CHAT", "-1003863573134"))
DESTINATION_CHAT = int(os.environ.get("DESTINATION_CHAT", "-1004406877280"))

START_MSG_ID = int(os.environ.get("START_MSG_ID", "1"))
END_MSG_ID = int(os.environ.get("END_MSG_ID", "3572"))

if not SESSION_STRING:
    print("ERROR: SESSION_STRING environment variable is missing! Please set SESSION_STRING in cloud settings.")
    import time
    while True:
        time.sleep(3600)

app = Client("koyeb_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

async def start_transfer():
    await app.start()
    print("Telegram account connected successfully!")
    print("Loading dialogs...")
    async for _ in app.get_dialogs(limit=50):
        pass

    print(f"Transfer started: From message {START_MSG_ID} to {END_MSG_ID}")
    total_saved = 0

    for msg_id in range(START_MSG_ID, END_MSG_ID + 1):
        try:
            msg = await app.get_messages(SOURCE_CHAT, msg_id)
            if not msg or msg.empty:
                continue

            if msg.video or msg.document or msg.photo:
                caption = msg.caption or ""
                print(f"[{msg_id}/{END_MSG_ID}] Downloading...")
                file_path = await app.download_media(msg)
                if not file_path:
                    continue

                print(f"[{msg_id}/{END_MSG_ID}] Uploading to destination channel...")
                if msg.video:
                    await app.send_video(DESTINATION_CHAT, video=file_path, caption=caption)
                elif msg.document:
                    await app.send_document(DESTINATION_CHAT, document=file_path, caption=caption)
                elif msg.photo:
                    await app.send_photo(DESTINATION_CHAT, photo=file_path, caption=caption)

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
