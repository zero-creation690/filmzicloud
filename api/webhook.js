// api/webhook.js
const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;
const BASE_URL = process.env.BASE_URL || '';

function randomId() {
  return Math.floor(100000 + Math.random() * 900000); // random 6-digit for better uniqueness
}

function getFileExtension(fileName) {
  if (!fileName) return '';
  const lastDot = fileName.lastIndexOf('.');
  return lastDot > 0 ? fileName.substring(lastDot) : '';
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).send('❌ Method not allowed');

  const update = req.body;
  const message = update.message;
  if (!message) return res.status(200).send('No message');

  const chatId = message.chat.id;
  const userId = message.from.id;
  const userName = message.from.first_name || message.from.username || 'User';

  // ✅ Handle /start command
  if (message.text && message.text.startsWith('/start')) {
    const welcomeText = `🎬 *Welcome to Filmzi Cloud Storage!*

👋 Hello *${userName}*!

📁 *How it works:*
• Send me any file (video, document, audio, photo)
• Get a permanent download link instantly
• Your files stay available forever ♾️
• No file size limits (up to Telegram's 2GB)

🔒 *Features:*
• Permanent storage - links work for years
• Fast download speeds
• No registration required
• Secure cloud storage

📤 *Just send me a file to get started!*

Powered by *Filmzi Cloud* ⚡`;

    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: welcomeText,
        parse_mode: "Markdown"
      })
    });
    return res.status(200).send('ok');
  }

  // ✅ Handle file uploads (all types including photos)
  let fileObj = message.document || message.video || message.audio || message.voice || 
                message.video_note || (message.photo ? message.photo[message.photo.length - 1] : null);
  
  if (!fileObj) {
    // Handle text messages with helpful response
    if (message.text && !message.text.startsWith('/')) {
      await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          chat_id: chatId,
          text: "📤 Please send me a file to generate a download link!\n\n💡 Supported: Videos, Documents, Audio, Photos, Voice messages",
          parse_mode: "Markdown"
        })
      });
    }
    return res.status(200).send('No file found');
  }

  try {
    // Send "processing" message to user
    const processingMsg = await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: "⏳ Processing your file... Please wait!",
        parse_mode: "Markdown"
      })
    });
    const processingJson = await processingMsg.json();

    // Forward original message to storage channel
    const fwd = await fetch(`https://api.telegram.org/bot${TOKEN}/forwardMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: CHANNEL_ID,
        from_chat_id: chatId,
        message_id: message.message_id
      })
    });
    const fwdJson = await fwd.json();

    if (!fwdJson.ok) {
      throw new Error(`Failed to forward message: ${fwdJson.description}`);
    }

    // Generate unique identifiers
    const shortId = randomId();
    const timestamp = Math.floor(Date.now() / 1000);
    const fileId = fileObj.file_id;
    
    // Get proper filename with extension
    let fileName = fileObj.file_name || `file_${shortId}`;
    
    // Handle different file types
    if (message.photo) {
      fileName = `photo_${shortId}.jpg`;
    } else if (message.voice) {
      fileName = `voice_${shortId}.ogg`;
    } else if (message.video_note) {
      fileName = `video_note_${shortId}.mp4`;
    } else if (!fileObj.file_name) {
      // Add appropriate extension based on mime_type
      const mimeType = fileObj.mime_type || '';
      if (mimeType.includes('video')) fileName += '.mp4';
      else if (mimeType.includes('audio')) fileName += '.mp3';
      else if (mimeType.includes('image')) fileName += '.jpg';
    }

    const fileSize = fileObj.file_size || 0;
    const fileSizeMB = (fileSize / (1024 * 1024)).toFixed(2);

    // Store mapping with metadata in channel
    const mappingData = {
      id: shortId,
      file_id: fileId,
      filename: fileName,
      size: fileSize,
      timestamp: timestamp,
      user_id: userId,
      username: userName,
      message_id: fwdJson.result.message_id
    };

    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: CHANNEL_ID,
        reply_to_message_id: fwdJson.result.message_id,
        text: `MAPPING:${JSON.stringify(mappingData)}`,
        parse_mode: "HTML"
      })
    });

    // Generate permanent download link
    const base = BASE_URL || `https://${req.headers.host}`;
    const downloadLink = `${base}/api/dl/${encodeURIComponent(fileName)}-${shortId}`;

    // Delete processing message
    await fetch(`https://api.telegram.org/bot${TOKEN}/deleteMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        message_id: processingJson.result.message_id
      })
    });

    // Send success message with download link
    const successText = `✅ *File uploaded successfully!*

📁 *File:* ${fileName}
📊 *Size:* ${fileSizeMB} MB
🔗 *Download Link:* ${downloadLink}

🛡️ *Permanent Storage Features:*
• Link works forever (even after 1+ years)
• Fast download speeds
• No expiration date
• Stored securely in Filmzi Cloud

💾 *Your file is now permanently stored!*`;

    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: successText,
        parse_mode: "Markdown",
        reply_markup: {
          inline_keyboard: [[
            {
              text: "🔗 Open Download Link",
              url: downloadLink
            }
          ]]
        }
      })
    });

    return res.status(200).send('ok');

  } catch (err) {
    console.error('Webhook error:', err);
    
    // Send error message to user
    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: `❌ *Upload Failed*\n\nSorry, there was an error processing your file. Please try again.\n\n*Error:* ${err.message}`,
        parse_mode: "Markdown"
      })
    });
    
    return res.status(500).send('Server error');
  }
}
