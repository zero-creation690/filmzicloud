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
    """Generate a random 8-digit ID"""
    return random.randint(10000000, 99999999)

def send_message(chat_id, text, parse_mode=None):
    """Send message via Telegram Bot API"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    data = {
        'chat_id': chat_id,
        'text': text
    }
    
    if parse_mode:
        data['parse_mode'] = parse_mode
    
    response = requests.post(url, json=data)
    return response.json()

def get_file_url(file_id):
    """Get file URL from Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/getFile"
    data = {'file_id': file_id}
    response = requests.post(url, json=data)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('ok'):
            file_path = result['result']['file_path']
            return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    return None

def copy_message_to_channel(chat_id, message_id, caption=None):
    """Copy message to channel (works for files up to 2GB)"""
    url = f"https://api.telegram.org/bot{TOKEN}/copyMessage"
    
    data = {
        'chat_id': CHANNEL_ID,
        'from_chat_id': chat_id,
        'message_id': message_id
    }
    
    if caption:
        data['caption'] = caption
    
    response = requests.post(url, json=data)
    return response.json()

def save_to_redis(short_id, file_data):
    """Save file mapping to Redis"""
    try:
        r = get_redis_client()
        key = f"file:{short_id}"
        # Store with no expiration (permanent)
        r.set(key, json.dumps(file_data))
        return True
    except Exception as e:
        print(f"Redis save error: {e}")
        return False

def get_from_redis(short_id):
    """Get file mapping from Redis"""
    try:
        r = get_redis_client()
        key = f"file:{short_id}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"Redis get error: {e}")
        return None

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            update = json.loads(post_data.decode('utf-8'))
            
            message = update.get('message')
            if not message:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'No message')
                return
            
            chat_id = message['chat']['id']
            message_id = message['message_id']
            
            # Handle /start command
            if message.get('text', '').startswith('/start'):
                first_name = message.get('from', {}).get('first_name', 'friend')
                response_text = (f"👋 Hello *{first_name}*!\n\n"
                               f"📂 Send me any file (up to 2GB) and I'll give you a *PERMANENT* download link ⚡\n\n"
                               f"🛡️ Files stored forever in *Filmzi Cloud*!\n"
                               f"🔗 Links never expire!\n"
                               f"💾 Supports files up to *2GB*\n"
                               f"💾 *Redis-powered permanent storage!*")
                
                send_message(chat_id, response_text, parse_mode="Markdown")
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
                send_message(chat_id, "❌ Please send a file (document, video, audio, or photo).")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'No file found')
                return
            
            # Handle photo array (take the largest one)
            if isinstance(file_obj, list):
                file_obj = max(file_obj, key=lambda x: x.get('file_size', 0))
            
            file_id = file_obj['file_id']
            file_name = file_obj.get('file_name') or file_obj.get('file_unique_id', f'file_{random_id()}')
            
            # Add proper extension for photos
            if message.get('photo') and not '.' in file_name:
                file_name += '.jpg'
            
            short_id = str(random_id())
            
            # Get file size for display
            file_size = file_obj.get('file_size', 0)
            size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
            
            # Create caption for the file
            caption = f"📁 {file_name}\n💾 {size_mb} MB\n🆔 {short_id}"
            
            # Store file in channel
            storage_result = copy_message_to_channel(chat_id, message_id, caption)
            
            if not storage_result.get('ok'):
                # Fallback: try forwardMessage
                try:
                    forward_url = f"https://api.telegram.org/bot{TOKEN}/forwardMessage"
                    forward_data = {
                        'chat_id': CHANNEL_ID,
                        'from_chat_id': chat_id,
                        'message_id': message_id
                    }
                    forward_response = requests.post(forward_url, json=forward_data)
                    storage_result = forward_response.json()
                except Exception as e:
                    send_message(chat_id, f"❌ Failed to store file: {str(e)}")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'Storage failed')
                    return
            
            if not storage_result.get('ok'):
                error_desc = storage_result.get('description', 'Unknown error')
                send_message(chat_id, f"❌ Failed to store file: {error_desc}")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Storage failed')
                return
            
            channel_msg_id = storage_result['result']['message_id']
            
            # Get file URL for permanent access
            file_url = get_file_url(file_id)
            
            # Prepare file data for Redis
            file_data = {
                'file_id': file_id,
                'file_name': file_name,
                'file_size': file_size,
                'file_url': file_url,
                'channel_msg_id': channel_msg_id,
                'timestamp': int(os.times().elapsed),
                'short_id': short_id
            }
            
            # Save to Redis (permanent storage)
            redis_success = save_to_redis(short_id, file_data)
            
            if not redis_success:
                send_message(chat_id, "❌ Failed to create permanent storage. Please try again.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Redis storage failed')
                return
            
            # Build REAL permanent download link
            domain = os.environ.get('VERCEL_URL', 'your-app.vercel.app')
            if not domain.startswith('http'):
                domain = f"https://{domain}"
            
            # Clean filename for URL
            clean_name = file_name.replace(' ', '_').replace('(', '').replace(')', '')
            encoded_name = quote(clean_name)
            download_link = f"{domain}/api/download/{encoded_name}-{short_id}"
            
            # Send success response to user
            response_text = (f"✅ *PERMANENT* link created!\n\n"
                            f"📁 *File:* `{file_name}`\n"
                            f"📊 *Size:* {size_mb} MB\n"
                            f"🔗 *Download:* `{download_link}`\n\n"
                            f"🛡️ *Stored FOREVER in Redis Cloud!*\n"
                            f"⚡ *Link NEVER expires!*\n"
                            f"💾 *File ID:* `{short_id}`")
            
            send_message(chat_id, response_text, parse_mode="Markdown")
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            
        except Exception as e:
            print(f"Webhook error: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            
            try:
                send_message(chat_id, f"❌ Server error: {str(e)}")
            except:
                pass
            
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'Server error: {str(e)}'.encode())
    
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        response = {
            "status": "Filmzi Cloud Bot is running!",
            "storage": "Redis-powered permanent storage",
            "features": "Permanent download links, 2GB file support"
        }
        self.wfile.write(json.dumps(response, indent=2).encode())
