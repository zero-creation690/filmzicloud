from http.server import BaseHTTPRequestHandler
import json
import os
import random
import requests
from urllib.parse import urlencode, quote

# Environment variables
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')

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

def save_file_mapping(channel_msg_id, short_id, file_id, file_name):
    """Save file mapping as reply in channel"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    mapping_data = f"📁 FILE_MAPPING\nID: {short_id}\nFile: {file_name}\nMsgID: {channel_msg_id}"
    
    data = {
        'chat_id': CHANNEL_ID,
        'text': mapping_data,
        'reply_to_message_id': channel_msg_id
    }
    
    response = requests.post(url, json=data)
    return response.json()

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
                               f"💾 Supports files up to *2GB*")
                
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
            
            # METHOD 1: Try copyMessage first (works for most files)
            storage_result = copy_message_to_channel(chat_id, message_id, caption)
            
            if not storage_result.get('ok'):
                # METHOD 2: Try forwardMessage for smaller files
                try:
                    forward_url = f"https://api.telegram.org/bot{TOKEN}/forwardMessage"
                    forward_data = {
                        'chat_id': CHANNEL_ID,
                        'from_chat_id': chat_id,
                        'message_id': message_id
                    }
                    forward_response = requests.post(forward_url, json=forward_data)
                    storage_result = forward_response.json()
                    
                    # If forward worked, edit the message to add caption
                    if storage_result.get('ok'):
                        channel_msg_id = storage_result['result']['message_id']
                        edit_url = f"https://api.telegram.org/bot{TOKEN}/editMessageCaption"
                        edit_data = {
                            'chat_id': CHANNEL_ID,
                            'message_id': channel_msg_id,
                            'caption': caption
                        }
                        requests.post(edit_url, json=edit_data)
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
            
            # Now get the file URL (after successful storage)
            file_url = get_file_url(file_id)
            
            if not file_url:
                # If we can't get direct URL, we'll use the file_id for download
                file_url = f"File ID: {file_id}"
            
            # Save file mapping
            mapping_result = save_file_mapping(channel_msg_id, short_id, file_id, file_name)
            
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
                            f"🛡️ *Stored FOREVER in Filmzi Cloud!*\n"
                            f"⚡ *Link NEVER expires!*")
            
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
            "endpoint": "POST /api/webhook for Telegram updates"
        }
        self.wfile.write(json.dumps(response, indent=2).encode())
