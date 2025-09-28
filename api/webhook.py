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
        # Store permanently (no expiration)
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

def delete_file(short_id, user_id):
    try:
        r = get_redis_client()
        key = f"file:{short_id}"
        
        # Check if user owns this file
        file_data = get_from_redis(short_id)
        if file_data and file_data.get('user_id') == user_id:
            r.delete(key)
            # Remove from user's file list
            user_key = f"user:{user_id}:files"
            r.srem(user_key, short_id)
            return True
        return False
    except Exception as e:
        print(f"Redis error: {e}")
        return False

def create_file_keyboard(files):
    """Create inline keyboard for file management"""
    keyboard = []
    for file_data in files[:10]:  # Show last 10 files
        file_name = file_data.get('file_name', 'Unknown')
        short_id = file_data.get('short_id')
        # Shorten filename for button
        btn_text = file_name[:20] + "..." if len(file_name) > 20 else file_name
        keyboard.append([{
            "text": f"📁 {btn_text}",
            "callback_data": f"file_{short_id}"
        }])
    
    # Add navigation buttons if needed
    if len(files) > 10:
        keyboard.append([{"text": "⬅️ Previous", "callback_data": "prev_page"}, 
                        {"text": "Next ➡️", "callback_data": "next_page"}])
    
    keyboard.append([{"text": "❌ Close", "callback_data": "close_files"}])
    
    return {"inline_keyboard": keyboard}

def create_file_actions_keyboard(short_id):
    """Create action buttons for a specific file"""
    return {
        "inline_keyboard": [
            [{"text": "🔗 Get Download Link", "callback_data": f"link_{short_id}"}],
            [{"text": "🗑️ Delete File", "callback_data": f"delete_{short_id}"}],
            [{"text": "⬅️ Back to Files", "callback_data": "back_to_files"}]
        ]
    }

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            update = json.loads(post_data.decode('utf-8'))
            
            # Handle callback queries (button clicks)
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
            
            # Handle /start command
            if message.get('text', '').startswith('/start'):
                welcome_text = """
👋 **Welcome to Filmzi Cloud!**

📁 **Send me any file (up to 2GB) and I'll give you a PERMANENT download link!**

✨ **Features:**
• 🛡️ Files stored forever in Telegram Cloud
• 🔗 **REAL** permanent download links
• 💾 Support for files up to 2GB
• ⚡ Fast downloads from Telegram's servers
• 📊 File management with /files command

**Commands:**
/files - View and manage your uploaded files
/help - Get help

**Just send me a file to get started!**
                """
                send_message(chat_id, welcome_text, parse_mode="Markdown")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
                return
            
            # Handle /files command
            if message.get('text', '').startswith('/files'):
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
                
                files_text += "Click on a file below to manage it:"
                
                keyboard = create_file_keyboard(user_files)
                send_message(chat_id, files_text, parse_mode="Markdown", reply_markup=keyboard)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
                return
            
            # Handle /help command
            if message.get('text', '').startswith('/help'):
                help_text = """
❓ **Filmzi Cloud Help**

**How to use:**
1. Send me any file (document, video, audio, photo)
2. I'll store it permanently in Telegram Cloud
3. You'll get a **permanent download link**

**Commands:**
/start - Start the bot
/files - Manage your uploaded files
/help - This help message

**File Limits:**
• Maximum file size: 2GB
• Supported formats: All file types
• Links: Never expire

**Need help?** Just send me a file and I'll handle the rest!
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
                send_message(chat_id, "❌ Please send a file (document, video, audio, or photo).\n\nUse /help for instructions.")
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
            size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
            
            # Get direct download URL
            download_url = get_file_direct_url(file_id)
            
            if not download_url:
                send_message(chat_id, "❌ Failed to get file URL from Telegram. Please try again.")
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
            
            # Build REAL permanent download link
            domain = os.environ.get('VERCEL_URL', 'filmzicloud.vercel.app')
            if not domain.startswith('http'):
                domain = f"https://{domain}"
            
            # Clean filename for URL
            clean_name = file_name.replace(' ', '_')
            encoded_name = quote(clean_name)
            download_link = f"{domain}/api/download/{encoded_name}-{short_id}"
            
            # Send success message
            success_text = f"""
✅ **File Uploaded Successfully!**

📁 **File:** `{file_name}`
📊 **Size:** {size_mb} MB
🆔 **ID:** `{short_id}`

🔗 **Permanent Download Link:**
`{download_link}`

💡 **Use /files to manage your files**
🛡️ **Link never expires - stored forever!**
            """
            
            send_message(chat_id, success_text, parse_mode="Markdown")
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            
        except Exception as e:
            print(f"Webhook error: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            
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
            
            # Handle file selection
            if data.startswith('file_'):
                short_id = data.replace('file_', '')
                file_data = get_from_redis(short_id)
                
                if file_data and file_data.get('user_id') == user_id:
                    file_name = file_data.get('file_name', 'Unknown')
                    file_size = file_data.get('file_size', 0)
                    size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
                    
                    file_info = f"""
📁 **File Selected**

**Name:** `{file_name}`
**Size:** {size_mb} MB
**ID:** `{short_id}`
**Uploaded:** Ready

Choose an action below:
                    """
                    
                    keyboard = create_file_actions_keyboard(short_id)
                    self.edit_message(chat_id, message_id, file_info, keyboard)
                else:
                    self.answer_callback(callback_query['id'], "❌ File not found or access denied")
            
            # Handle get link
            elif data.startswith('link_'):
                short_id = data.replace('link_', '')
                file_data = get_from_redis(short_id)
                
                if file_data and file_data.get('user_id') == user_id:
                    file_name = file_data.get('file_name', 'Unknown')
                    domain = os.environ.get('VERCEL_URL', 'filmzicloud.vercel.app')
                    if not domain.startswith('http'):
                        domain = f"https://{domain}"
                    
                    clean_name = file_name.replace(' ', '_')
                    encoded_name = quote(clean_name)
                    download_link = f"{domain}/api/download/{encoded_name}-{short_id}"
                    
                    link_text = f"""
🔗 **Download Link**

**File:** `{file_name}`
**Link:** `{download_link}`

⚠️ **This link is PERMANENT and will never expire!**
                    """
                    
                    self.answer_callback(callback_query['id'], "Link generated below!")
                    send_message(chat_id, link_text, parse_mode="Markdown")
                else:
                    self.answer_callback(callback_query['id'], "❌ File not found")
            
            # Handle delete file
            elif data.startswith('delete_'):
                short_id = data.replace('delete_', '')
                
                if delete_file(short_id, user_id):
                    self.answer_callback(callback_query['id'], "✅ File deleted successfully!")
                    send_message(chat_id, f"🗑️ File with ID `{short_id}` has been permanently deleted.")
                else:
                    self.answer_callback(callback_query['id'], "❌ Failed to delete file")
            
            # Handle back to files
            elif data == 'back_to_files':
                user_files = get_user_files(user_id)
                if user_files:
                    files_text = f"📁 **Your Files ({len(user_files)}):**\n\n"
                    for i, file_data in enumerate(user_files[:5], 1):
                        file_name = file_data.get('file_name', 'Unknown')
                        file_size = file_data.get('file_size', 0)
                        size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
                        short_id = file_data.get('short_id')
                        
                        files_text += f"{i}. **{file_name}**\n"
                        files_text += f"   📊 {size_mb} MB | 🆔 `{short_id}`\n\n"
                    
                    files_text += "Click on a file to manage it:"
                    
                    keyboard = create_file_keyboard(user_files)
                    self.edit_message(chat_id, message_id, files_text, keyboard)
                else:
                    self.edit_message(chat_id, message_id, "📁 You have no files uploaded.")
            
            # Handle close
            elif data == 'close_files':
                self.delete_message(chat_id, message_id)
                self.answer_callback(callback_query['id'], "Closed file manager")
            
            else:
                self.answer_callback(callback_query['id'], "❌ Unknown action")
                
        except Exception as e:
            print(f"Callback error: {e}")
            self.answer_callback(callback_query['id'], "❌ Error processing request")
    
    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        """Edit message text"""
        url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        requests.post(url, json=data)
    
    def delete_message(self, chat_id, message_id):
        """Delete a message"""
        url = f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
        data = {'chat_id': chat_id, 'message_id': message_id}
        requests.post(url, json=data)
    
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
            "features": "Permanent download links, File management, 2GB support"
        }
        self.wfile.write(json.dumps(response, indent=2).encode())
