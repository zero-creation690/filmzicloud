from http.server import BaseHTTPRequestHandler
import json
import os
import random
import requests
from urllib.parse import urlencode, quote
import redis

# Environment variables
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')
API_ID = os.environ.get('API_ID', '20288994')
API_HASH = os.environ.get('API_HASH', 'd702614912f1ad370a0d18786002adbf')
BASE_URL = os.environ.get('BASE_URL', 'https://filmzicloud.vercel.app')

# Initialize Redis
def get_redis_client():
    return redis.Redis(
        host=REDIS_URL.replace('https://', '').split(':')[0],
        port=6379,
        password=REDIS_TOKEN,
        ssl=True,
        decode_responses=True
    )

def random_id():
    return random.randint(10000000, 99999999)

def send_message(chat_id, text, parse_mode=None, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {'chat_id': chat_id, 'text': text}
    if parse_mode:
        data['parse_mode'] = parse_mode
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    response = requests.post(url, json=data)
    return response.json()

def get_file_direct_url(file_id):
    """Get direct download URL from Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/getFile"
    data = {'file_id': file_id}
    response = requests.post(url, json=data)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('ok'):
            file_path = result['result']['file_path']
            return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    return None

def save_to_redis(short_id, file_data):
    try:
        r = get_redis_client()
        key = f"file:{short_id}"
        r.set(key, json.dumps(file_data))
        
        # Save user-file mapping
        user_key = f"user:{file_data['user_id']}:files"
        r.sadd(user_key, short_id)
        return True
    except Exception as e:
        print(f"Redis error: {e}")
        return False

def get_from_redis(short_id):
    try:
        r = get_redis_client()
        key = f"file:{short_id}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"Redis error: {e}")
        return None

def get_user_files(user_id):
    try:
        r = get_redis_client()
        user_key = f"user:{user_id}:files"
        file_ids = r.smembers(user_key)
        files = []
        for file_id in file_ids:
            file_data = get_from_redis(file_id)
            if file_data:
                files.append(file_data)
        return files
    except Exception as e:
        print(f"Redis error: {e}")
        return []

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            update = json.loads(post_data.decode('utf-8'))
            
            # Handle callback queries
            if 'callback_query' in update:
                self.handle_callback_query(update['callback_query'])
                return
            
            message = update.get('message')
            if not message:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'No message')
                return
            
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            message_text = message.get('text', '')
            
            # Handle /start command
            if message_text.startswith('/start'):
                welcome_text = f"""
👋 **Welcome to Filmzi Cloud!**

📁 **Send me ANY file up to 2GB and get INSTANT download & streaming links!**

✨ **Ultimate Features:**
• 🛡️ Permanent Telegram Cloud Storage
• 🔗 **Download Links** - Direct file downloads
• 📺 **Streaming Links** - Watch videos directly in browser
• 💾 **2GB File Support** - Massive files supported
• ⚡ **Instant Processing** - No waiting time
• 🔒 **Secure & Private** - Your files are safe

**Commands:**
`/start` - Show this welcome message
`/files` - Manage your uploaded files
`/help` - Get help and instructions

**Just send me any file to get started!**
                """
                send_message(chat_id, welcome_text, parse_mode="Markdown")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
                return
            
            # Handle /files command
            if message_text.startswith('/files'):
                user_files = get_user_files(user_id)
                
                if not user_files:
                    send_message(chat_id, "📁 You haven't uploaded any files yet.\n\nSend me a file to get started!")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                    return
                
                files_text = f"📁 **Your Files ({len(user_files)}):**\n\n"
                for i, file_data in enumerate(user_files[:5], 1):
                    file_name = file_data.get('file_name', 'Unknown')
                    file_size = file_data.get('file_size', 0)
                    size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
                    short_id = file_data.get('short_id')
                    
                    files_text += f"{i}. **{file_name}**\n"
                    files_text += f"   📊 {size_mb} MB | 🆔 `{short_id}`\n\n"
                
                if len(user_files) > 5:
                    files_text += f"... and {len(user_files) - 5} more files\n\n"
                
                files_text += "**Quick Actions:**\n• Send /download [ID] to get links\n• Send /delete [ID] to remove file"
                
                send_message(chat_id, files_text, parse_mode="Markdown")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
                return
            
            # Handle /download command
            if message_text.startswith('/download'):
                parts = message_text.split()
                if len(parts) < 2:
                    send_message(chat_id, "❌ Usage: `/download FILE_ID`\n\nGet your FILE_ID from /files command", parse_mode="Markdown")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                    return
                
                short_id = parts[1]
                file_data = get_from_redis(short_id)
                
                if not file_data or file_data.get('user_id') != user_id:
                    send_message(chat_id, "❌ File not found or access denied.")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                    return
                
                file_name = file_data.get('file_name', 'Unknown')
                file_size = file_data.get('file_size', 0)
                size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
                
                # Build links
                clean_name = file_name.replace(' ', '_')
                encoded_name = quote(clean_name)
                download_link = f"{BASE_URL}/api/download/{encoded_name}-{short_id}"
                stream_link = f"{BASE_URL}/api/stream/{encoded_name}-{short_id}"
                
                links_text = f"""
🔗 **Download & Streaming Links**

📁 **File:** `{file_name}`
📊 **Size:** {size_mb} MB
🆔 **ID:** `{short_id}`

⬇️ **Download Link:**
`{download_link}`

📺 **Streaming Link:**
`{stream_link}`

💡 **Pro Tips:**
• Download link: Right-click → Save as
• Streaming link: Watch directly in browser
• Links are **PERMANENT** and never expire!
                """
                
                send_message(chat_id, links_text, parse_mode="Markdown")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
                return
            
            # Handle /help command
            if message_text.startswith('/help'):
                help_text = f"""
❓ **Filmzi Cloud Help Guide**

**How to Upload:**
1. Send me any file (video, document, audio, photo)
2. I'll instantly process it (up to 2GB)
3. You'll get **both download and streaming links**

**Available Commands:**
• `/start` - Welcome message
• `/files` - List your uploaded files
• `/download FILE_ID` - Get links for specific file
• `/help` - This help message

**Supported Files:**
• 📹 Videos (MP4, AVI, MKV, etc.)
• 📄 Documents (PDF, ZIP, EXE, etc.)
• 🎵 Audio (MP3, WAV, etc.)
• 📷 Photos (JPG, PNG, etc.)
• 💾 Any file type up to 2GB!

**Base URL:** `{BASE_URL}`
**Max File Size:** 2GB
**Storage:** Permanent Telegram Cloud

**Just send me a file and see the magic!** ✨
                """
                send_message(chat_id, help_text, parse_mode="Markdown")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
                return
            
            # Handle file upload
            file_obj = (message.get('document') or 
                       message.get('video') or 
                       message.get('audio') or 
                       message.get('photo'))
            
            if not file_obj:
                help_text = """
📤 **Ready to Upload!**

Just send me any file and I'll create:
• ✅ **Download Link** - Direct file download
• 📺 **Streaming Link** - Watch videos in browser
• 🛡️ **Permanent Storage** - Never expires

**Supported:** All file types up to 2GB!
**No limits, no waiting!**

Drag and drop your file or click the attachment icon 📎
                """
                send_message(chat_id, help_text, parse_mode="Markdown")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'No file found')
                return
            
            # Handle photo array
            if isinstance(file_obj, list):
                file_obj = max(file_obj, key=lambda x: x.get('file_size', 0))
            
            file_id = file_obj['file_id']
            file_name = file_obj.get('file_name', 'file')
            file_size = file_obj.get('file_size', 0)
            
            # Check file size limit (2GB = 2147483648 bytes)
            if file_size > 2147483648:
                send_message(chat_id, "❌ File too large! Maximum size is 2GB.\n\nPlease send a smaller file.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'File too large')
                return
            
            # Add extension for photos
            if message.get('photo') and not '.' in file_name:
                file_name += '.jpg'
            
            short_id = str(random_id())
            size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
            
            # Get direct download URL
            download_url = get_file_direct_url(file_id)
            
            if not download_url:
                send_message(chat_id, "❌ Failed to process file. Please try again.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'File URL failed')
                return
            
            # Prepare file data for Redis
            file_data = {
                'file_id': file_id,
                'file_name': file_name,
                'file_size': file_size,
                'download_url': download_url,
                'user_id': user_id,
                'timestamp': int(os.times().elapsed),
                'short_id': short_id,
                'chat_id': chat_id
            }
            
            # Save to Redis
            if not save_to_redis(short_id, file_data):
                send_message(chat_id, "❌ Failed to save file to storage. Please try again.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Redis save failed')
                return
            
            # Build permanent links
            clean_name = file_name.replace(' ', '_')
            encoded_name = quote(clean_name)
            download_link = f"{BASE_URL}/api/download/{encoded_name}-{short_id}"
            stream_link = f"{BASE_URL}/api/stream/{encoded_name}-{short_id}"
            
            # Determine file type for emoji
            file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
            file_emoji = "📁"
            if file_ext in ['mp4', 'avi', 'mkv', 'mov', 'wmv']:
                file_emoji = "🎥"
            elif file_ext in ['mp3', 'wav', 'flac', 'aac']:
                file_emoji = "🎵"
            elif file_ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                file_emoji = "🖼️"
            elif file_ext in ['pdf', 'doc', 'docx', 'txt']:
                file_emoji = "📄"
            elif file_ext in ['zip', 'rar', '7z', 'tar']:
                file_emoji = "📦"
            
            # Send success message
            success_text = f"""
✅ **Upload Successful!** {file_emoji}

📁 **File:** `{file_name}`
📊 **Size:** {size_mb} MB
🆔 **ID:** `{short_id}`

⬇️ **Download Link:**
`{download_link}`

📺 **Streaming Link:**
`{stream_link}`

💡 **Quick Actions:**
• Use `/files` to see all your files
• Use `/download {short_id}` to get these links again
• Links work forever - bookmark them!

🛡️ **Stored permanently in Telegram Cloud**
⚡ **2GB file support enabled**
                """
            
            send_message(chat_id, success_text, parse_mode="Markdown")
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            
        except Exception as e:
            print(f"Webhook error: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            
            try:
                send_message(chat_id, "❌ Server error occurred. Please try again.")
            except:
                pass
            
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'Server error: {str(e)}'.encode())
    
    def handle_callback_query(self, callback_query):
        """Handle button clicks"""
        try:
            chat_id = callback_query['message']['chat']['id']
            user_id = callback_query['from']['id']
            data = callback_query['data']
            message_id = callback_query['message']['message_id']
            
            # Basic callback handling
            if data == 'test':
                self.answer_callback(callback_query['id'], "Button clicked!")
            else:
                self.answer_callback(callback_query['id'], "Action completed!")
                
        except Exception as e:
            print(f"Callback error: {e}")
            self.answer_callback(callback_query['id'], "❌ Error processing request")
    
    def answer_callback(self, callback_id, text):
        """Answer callback query"""
        url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
        data = {'callback_query_id': callback_id, 'text': text}
        requests.post(url, json=data)
    
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        response = {
            "status": "Filmzi Cloud Bot is running!",
            "features": {
                "file_size": "Up to 2GB files supported",
                "links": "Download + Streaming links",
                "storage": "Permanent Telegram Cloud",
                "base_url": BASE_URL,
                "api_id": API_ID
            }
        }
        self.wfile.write(json.dumps(response, indent=2).encode())
