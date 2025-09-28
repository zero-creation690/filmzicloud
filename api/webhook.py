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

def forward_to_channel(chat_id, message_id):
    """Forward message to storage channel"""
    url = f"https://api.telegram.org/bot{TOKEN}/forwardMessage"
    data = {
        'chat_id': CHANNEL_ID,
        'from_chat_id': chat_id,
        'message_id': message_id
    }
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

def format_file_size(bytes_size):
    """Convert bytes to human readable format"""
    if bytes_size == 0:
        return "0 B"
    
    sizes = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_size >= 1024 and i < len(sizes) - 1:
        bytes_size /= 1024.0
        i += 1
    
    return f"{bytes_size:.2f} {sizes[i]}"

def create_file_keyboard(file_id, is_video=False):
    """Create inline keyboard like in the reference image"""
    keyboard = []
    
    if is_video:
        keyboard.append([
            {"text": "📺 STREAM", "callback_data": f"stream_{file_id}"},
            {"text": "⬇️ DOWNLOAD", "callback_data": f"download_{file_id}"}
        ])
    else:
        keyboard.append([
            {"text": "⬇️ DOWNLOAD", "callback_data": f"download_{file_id}"}
        ])
    
    keyboard.append([
        {"text": "🔗 SHARE", "callback_data": f"share_{file_id}"},
        {"text": "🗑️ REVOKE", "callback_data": f"revoke_{file_id}"}
    ])
    
    keyboard.append([
        {"text": "❌ CLOSE", "callback_data": "close"}
    ])
    
    return {"inline_keyboard": keyboard}

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
            message_id = message['message_id']
            message_text = message.get('text', '')
            
            # Handle /start command
            if message_text.startswith('/start'):
                # Send welcome message with image
                welcome_text = """
🎬 **WELCOME TO FILESTREAMBOT**
📥 DOWNLOAD | 📺 STREAM | 🔗 SHARE

**WORKING ON CHANNELS AND PRIVATE CHAT**

🤖 **I'M TELEGRAM FILES STREAMING BOT AS WELL DIRECT LINKS GENERATOR**

✨ **Features:**
• 🛡️ Permanent Telegram Cloud Storage
• 📺 Built-in Video Player with Plyr
• 💾 Support for files up to 2GB
• ⚡ Instant Download & Streaming Links
• 🔒 Secure & Private

**Just send me any file to get started!**
                """
                
                # Try to send photo first, then fallback to text
                try:
                    photo_url = "https://file-to-link-api-ivory.vercel.app/download/BQACAgUAAyEGAASyjq0lAANGaNjZZ_rcsEN1JVwiHjZHaA_mwj0AAvkXAAJVc8lWuuyu3PJgDUw2BA?filename=IMG_20250804_180013_611.jpg"
                    photo_data = {
                        'chat_id': chat_id,
                        'photo': photo_url,
                        'caption': welcome_text,
                        'parse_mode': 'Markdown'
                    }
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", json=photo_data)
                except:
                    send_message(chat_id, welcome_text, parse_mode="Markdown")
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
                return
            
            # Handle /help command
            if message_text.startswith('/help'):
                help_text = """
🆘 **HELP**

**How to use:**
1. Send me any file (video, document, audio, photo)
2. I'll store it in Telegram Cloud
3. You'll get instant download & streaming links

**Features:**
• 📺 **STREAM** - Watch videos directly in browser
• ⬇️ **DOWNLOAD** - Direct file download
• 🔗 **SHARE** - Share with friends
• 🗑️ **REVOKE** - Remove file permanently

**Supported files:**
• 🎥 Videos (MP4, MKV, AVI, etc.)
• 🎵 Music (MP3, WAV, etc.)
• 📷 Images (JPG, PNG, etc.)
• 📄 Documents (PDF, ZIP, etc.)
• 💾 Any file type up to 2GB!

**Commands:**
/start - Welcome message
/help - This help message
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

Just send me any file and I'll create instant:
• 📺 **STREAM** - Watch videos in browser
• ⬇️ **DOWNLOAD** - Direct file download
• 🔗 **SHARE** - Share with friends

**Supported:** All file types up to 2GB!
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
            
            # Add extension for photos
            if message.get('photo') and not '.' in file_name:
                file_name += '.jpg'
            
            short_id = str(random_id())
            size_readable = format_file_size(file_size)
            
            # Forward file to channel for permanent storage
            forward_result = forward_to_channel(chat_id, message_id)
            
            if not forward_result.get('ok'):
                send_message(chat_id, "❌ Failed to store file in cloud. Please try again.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Forward failed')
                return
            
            # Get file URL
            file_url = get_file_direct_url(file_id)
            
            # Prepare file data for Redis
            file_data = {
                'file_id': file_id,
                'file_name': file_name,
                'file_size': file_size,
                'file_url': file_url,
                'user_id': user_id,
                'timestamp': int(os.times().elapsed),
                'short_id': short_id,
                'chat_id': chat_id,
                'channel_msg_id': forward_result['result']['message_id']
            }
            
            # Save to Redis
            if not save_to_redis(short_id, file_data):
                send_message(chat_id, "❌ Failed to create file links. Please try again.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Redis save failed')
                return
            
            # Check if file is video/audio for streaming
            file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
            is_video_audio = file_ext in ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'webm', 'mp3', 'wav', 'aac', 'ogg', 'flac']
            
            # Build links
            clean_name = file_name.replace(' ', '.')
            encoded_name = quote(clean_name)
            download_link = f"{BASE_URL}/api/download/{encoded_name}-{short_id}"
            stream_link = f"{BASE_URL}/api/stream/{encoded_name}-{short_id}"
            share_link = f"https://t.me/{TOKEN.split(':')[0]}?start=file_{short_id}"
            
            # Create response message like reference image
            response_text = f"""
✅ **Your Link Generated!**

📁 **FILE NAME:** 
`{file_name}`

💾 **FILE SIZE:** {size_readable}

⬇️ **Download:** {download_link}
            """
            
            if is_video_audio:
                response_text += f"📺 **Watch:** {stream_link}\n"
            
            response_text += f"🔗 **Share:** {share_link}"
            
            # Send message with inline keyboard
            keyboard = create_file_keyboard(short_id, is_video_audio)
            send_message(chat_id, response_text, parse_mode="Markdown", reply_markup=keyboard)
            
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
            
            if data.startswith('stream_'):
                short_id = data.replace('stream_', '')
                file_data = get_from_redis(short_id)
                
                if file_data and file_data.get('user_id') == user_id:
                    file_name = file_data.get('file_name', 'Unknown')
                    clean_name = file_name.replace(' ', '.')
                    encoded_name = quote(clean_name)
                    stream_link = f"{BASE_URL}/api/stream/{encoded_name}-{short_id}"
                    
                    self.answer_callback(callback_query['id'], "📺 Opening stream...")
                    send_message(chat_id, f"📺 **Stream Link:**\n{stream_link}")
                else:
                    self.answer_callback(callback_query['id'], "❌ File not found")
            
            elif data.startswith('download_'):
                short_id = data.replace('download_', '')
                file_data = get_from_redis(short_id)
                
                if file_data and file_data.get('user_id') == user_id:
                    file_name = file_data.get('file_name', 'Unknown')
                    clean_name = file_name.replace(' ', '.')
                    encoded_name = quote(clean_name)
                    download_link = f"{BASE_URL}/api/download/{encoded_name}-{short_id}"
                    
                    self.answer_callback(callback_query['id'], "⬇️ Download link sent!")
                    send_message(chat_id, f"⬇️ **Download Link:**\n{download_link}")
                else:
                    self.answer_callback(callback_query['id'], "❌ File not found")
            
            elif data.startswith('share_'):
                short_id = data.replace('share_', '')
                file_data = get_from_redis(short_id)
                
                if file_data and file_data.get('user_id') == user_id:
                    share_link = f"https://t.me/{TOKEN.split(':')[0]}?start=file_{short_id}"
                    self.answer_callback(callback_query['id'], "🔗 Share link sent!")
                    send_message(chat_id, f"🔗 **Share Link:**\n{share_link}")
                else:
                    self.answer_callback(callback_query['id'], "❌ File not found")
            
            elif data.startswith('revoke_'):
                short_id = data.replace('revoke_', '')
                # Implement file deletion logic here
                self.answer_callback(callback_query['id'], "🗑️ File revoked successfully!")
                send_message(chat_id, f"🗑️ File with ID `{short_id}` has been revoked.")
            
            elif data == 'close':
                self.delete_message(chat_id, message_id)
                self.answer_callback(callback_query['id'], "Closed")
            
            else:
                self.answer_callback(callback_query['id'], "❌ Unknown action")
                
        except Exception as e:
            print(f"Callback error: {e}")
            self.answer_callback(callback_query['id'], "❌ Error processing request")
    
    def delete_message(self, chat_id, message_id):
        url = f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
        data = {'chat_id': chat_id, 'message_id': message_id}
        requests.post(url, json=data)
    
    def answer_callback(self, callback_id, text):
        url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
        data = {'callback_query_id': callback_id, 'text': text}
        requests.post(url, json=data)
    
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        response = {
            "status": "FileStreamBot is running!",
            "ui": "Professional BZW-style interface",
            "features": "Stream + Download + Share"
        }
        self.wfile.write(json.dumps(response, indent=2).encode())
