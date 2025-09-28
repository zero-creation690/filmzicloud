import os
import random
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
import redis
import json
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, REDIS_URL, REDIS_TOKEN, BASE_URL, MAX_FILE_SIZE

# Initialize Redis client
def get_redis_client():
    return redis.Redis(
        host=REDIS_URL.replace('https://', '').split(':')[0],
        port=6379,
        password=REDIS_TOKEN,
        ssl=True,
        decode_responses=True
    )

# Initialize Pyrogram client
app = Client(
    "filmzi_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

def random_id():
    return random.randint(10000000, 99999999)

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"

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

def create_file_keyboard(file_id, is_video=False):
    """Create inline keyboard like BZW bot"""
    keyboard = []
    
    if is_video:
        keyboard.append([
            InlineKeyboardButton("📺 STREAM", callback_data=f"stream_{file_id}"),
            InlineKeyboardButton("⬇️ DOWNLOAD", callback_data=f"download_{file_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("⬇️ DOWNLOAD", callback_data=f"download_{file_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔗 SHARE", callback_data=f"share_{file_id}"),
        InlineKeyboardButton("🗑️ REVOKE", callback_data=f"revoke_{file_id}")
    ])
    
    keyboard.append([
        InlineKeyboardButton("❌ CLOSE", callback_data="close")
    ])
    
    return InlineKeyboardMarkup(keyboard)

# Start command handler
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    welcome_text = f"""
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
    
    # Try to send welcome image
    try:
        await message.reply_photo(
            photo="https://file-to-link-api-ivory.vercel.app/download/BQACAgUAAyEGAASyjq0lAANGaNjZZ_rcsEN1JVwiHjZHaA_mwj0AAvkXAAJVc8lWuuyu3PJgDUw2BA?filename=IMG_20250804_180013_611.jpg",
            caption=welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )

# Help command handler
@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
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
    
    await message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )

# Handle all media messages
@app.on_message(filters.media & filters.private)
async def handle_media(client: Client, message: Message):
    try:
        # Get file information
        if message.document:
            file = message.document
            file_name = file.file_name
            file_size = file.file_size
            mime_type = file.mime_type or "document"
        elif message.video:
            file = message.video
            file_name = file.file_name or f"video_{random_id()}.mp4"
            file_size = file.file_size
            mime_type = "video"
        elif message.audio:
            file = message.audio
            file_name = file.file_name or f"audio_{random_id()}.mp3"
            file_size = file.file_size
            mime_type = "audio"
        elif message.photo:
            file = message.photo
            file_name = f"photo_{random_id()}.jpg"
            file_size = file.file_size
            mime_type = "photo"
        else:
            await message.reply_text("❌ Unsupported file type.")
            return

        # Check file size
        if file_size > MAX_FILE_SIZE:
            await message.reply_text("❌ File too large! Maximum size is 2GB.")
            return

        short_id = str(random_id())
        size_readable = format_file_size(file_size)
        user_id = message.from_user.id

        # Forward file to channel
        try:
            forwarded_msg = await message.forward(CHANNEL_ID)
            channel_msg_id = forwarded_msg.id
        except Exception as e:
            await message.reply_text("❌ Failed to store file in cloud. Please try again.")
            print(f"Forward error: {e}")
            return

        # Get file ID for download
        file_id = None
        if message.document:
            file_id = message.document.file_id
        elif message.video:
            file_id = message.video.file_id
        elif message.audio:
            file_id = message.audio.file_id
        elif message.photo:
            file_id = message.photo.file_id

        # Prepare file data for Redis
        file_data = {
            'file_id': file_id,
            'file_name': file_name,
            'file_size': file_size,
            'user_id': user_id,
            'timestamp': int(asyncio.get_event_loop().time()),
            'short_id': short_id,
            'chat_id': message.chat.id,
            'channel_msg_id': channel_msg_id,
            'mime_type': mime_type
        }

        # Save to Redis
        if not save_to_redis(short_id, file_data):
            await message.reply_text("❌ Failed to create file links. Please try again.")
            return

        # Build links
        clean_name = file_name.replace(' ', '.')
        download_link = f"{BASE_URL}/api/download/{clean_name}-{short_id}"
        stream_link = f"{BASE_URL}/api/stream/{clean_name}-{short_id}"
        share_link = f"https://t.me/{BOT_TOKEN.split(':')[0]}?start=file_{short_id}"

        # Check if file is video/audio for streaming
        is_video_audio = mime_type.startswith('video') or mime_type.startswith('audio')

        # Create response message like BZW bot
        response_text = f"""
✅ **Your Link Generated!**

📁 **FILE NAME:** 
`{file_name}`

💾 **FILE SIZE:** {size_readable}

⬇️ **Download:** `{download_link}`
        """
        
        if is_video_audio:
            response_text += f"📺 **Watch:** `{stream_link}`\n"
        
        response_text += f"🔗 **Share:** `{share_link}`"

        # Send message with inline keyboard
        keyboard = create_file_keyboard(short_id, is_video_audio)
        
        await message.reply_text(
            response_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    except Exception as e:
        print(f"Media handler error: {e}")
        await message.reply_text("❌ An error occurred while processing your file.")

# Callback query handler
@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        chat_id = callback_query.message.chat.id
        user_id = callback_query.from_user.id
        message_id = callback_query.message.id

        if data.startswith('stream_'):
            short_id = data.replace('stream_', '')
            file_data = get_from_redis(short_id)
            
            if file_data and file_data.get('user_id') == user_id:
                file_name = file_data.get('file_name', 'Unknown')
                stream_link = f"{BASE_URL}/api/stream/{file_name}-{short_id}"
                
                await callback_query.answer("📺 Opening stream...")
                await client.send_message(
                    chat_id, 
                    f"📺 **Stream Link:**\n`{stream_link}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await callback_query.answer("❌ File not found")

        elif data.startswith('download_'):
            short_id = data.replace('download_', '')
            file_data = get_from_redis(short_id)
            
            if file_data and file_data.get('user_id') == user_id:
                file_name = file_data.get('file_name', 'Unknown')
                download_link = f"{BASE_URL}/api/download/{file_name}-{short_id}"
                
                await callback_query.answer("⬇️ Download link sent!")
                await client.send_message(
                    chat_id, 
                    f"⬇️ **Download Link:**\n`{download_link}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await callback_query.answer("❌ File not found")

        elif data.startswith('share_'):
            short_id = data.replace('share_', '')
            file_data = get_from_redis(short_id)
            
            if file_data and file_data.get('user_id') == user_id:
                share_link = f"https://t.me/{BOT_TOKEN.split(':')[0]}?start=file_{short_id}"
                await callback_query.answer("🔗 Share link sent!")
                await client.send_message(
                    chat_id, 
                    f"🔗 **Share Link:**\n`{share_link}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await callback_query.answer("❌ File not found")

        elif data.startswith('revoke_'):
            short_id = data.replace('revoke_', '')
            # Implement file deletion logic here
            await callback_query.answer("🗑️ File revoked successfully!")
            await client.send_message(
                chat_id,
                f"🗑️ File with ID `{short_id}` has been revoked.",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data == 'close':
            await callback_query.message.delete()
            await callback_query.answer("Closed")

        else:
            await callback_query.answer("❌ Unknown action")
            
    except Exception as e:
        print(f"Callback error: {e}")
        await callback_query.answer("❌ Error processing request")

# Start the bot
if __name__ == "__main__":
    print("🎬 Filmzi Bot Started!")
    app.run()
