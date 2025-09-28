// api/webhook.js
const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;
const BASE_URL = process.env.BASE_URL || '';

function randomId() {
  return Math.floor(100000 + Math.random() * 900000); // random 6-digit for better uniqueness
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

    // Generate unique identifiers FIRST
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

    // Create mapping data
    const mappingData = {
      id: shortId,
      file_id: fileId,
      filename: fileName,
      size: fileSize,
      timestamp: timestamp,
      user_id: userId,
      username: userName,
      original_message_id: message.message_id
    };

    // Method 1: Send file mapping message FIRST (this ensures it exists)
    const mappingMsg = await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: CHANNEL_ID,
        text: `FILE_MAP_${shortId}:${JSON.stringify(mappingData)}`,
        parse_mode: "HTML"
      })
    });
    const mappingMsgJson = await mappingMsg.json();

    if (!mappingMsgJson.ok) {
      throw new Error(`Failed to save file mapping: ${mappingMsgJson.description}`);
    }

    // Method 2: Also send a simple format for backup
    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: CHANNEL_ID,
        text: `${shortId}|${fileId}|${fileName}|${fileSize}|${timestamp}`,
        parse_mode: "HTML"
      })
    });

    // Method 3: Forward the original message for backup
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

    // If forward worked, link it to the mapping
    if (fwdJson.ok) {
      await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          chat_id: CHANNEL_ID,
          reply_to_message_id: fwdJson.result.message_id,
          text: `LINKED_TO_${shortId}`,
          parse_mode: "HTML"
        })
      });
    }

    // Method 4: Additional database backup (optional but recommended)
    try {
      const dbBackup = await fetch(`${BASE_URL || `https://${req.headers.host}`}/api/db/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shortId: shortId,
          fileId: fileId,
          filename: fileName,
          size: fileSize,
          userId: userId,
          username: userName
        })
      });
      
      if (dbBackup.ok) {
        console.log(`✅ Database backup saved for ${shortId}`);
      }
    } catch (dbErr) {
      console.log(`⚠️ Database backup failed for ${shortId}:`, dbErr.message);
      // Don't fail the whole process if backup fails
    }

    // Method 5: Create searchable index entries
    const searchableEntries = [
      `INDEX_${shortId}_${fileName.toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
      `SIZE_${shortId}_${fileSize}`,
      `USER_${shortId}_${userId}`,
      `DATE_${shortId}_${timestamp}`
    ];

    for (const indexEntry of searchableEntries) {
      try {
        await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
          method: 'POST',
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            chat_id: CHANNEL_ID,
            text: `${indexEntry}=${fileId}`,
            disable_notification: true
          })
        });
      } catch (indexErr) {
        // Ignore index failures
      }
    }

    // Generate permanent download link
    const base = BASE_URL || `https://${req.headers.host}`;
    const downloadLink = `${base}/api/dl/${encodeURIComponent(fileName)}-${shortId}`;

    // Delete processing message
    try {
      await fetch(`https://api.telegram.org/bot${TOKEN}/deleteMessage`, {
        method: 'POST',
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          chat_id: chatId,
          message_id: processingJson.result.message_id
        })
      });
    } catch (e) {
      // Ignore delete errors
    }

    // Send success message with download link
    const successText = `✅ *File uploaded successfully!*

📁 *File:* ${fileName}
📊 *Size:* ${fileSizeMB} MB
🆔 *File ID:* ${shortId}

🔗 *Direct Download Link:*
\`${downloadLink}\`

🚀 *How to use:*
• Copy the link above
• Paste in any browser (Chrome, Safari, Firefox)
• File downloads automatically - no clicks needed!

🛡️ *Permanent Features:*
• Works forever (even after years)
• Direct download - no redirects
• Fast streaming from cloud
• No ads or wait times

💾 *Your file is permanently stored!*`;

    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: successText,
        parse_mode: "Markdown",
        reply_markup: {
          inline_keyboard: [
            [
              {
                text: "🔗 Copy Download Link",
                url: downloadLink
              }
            ],
            [
              {
                text: "📋 Share Link",
                switch_inline_query: downloadLink
              }
            ]
          ]
        }
      })
    });

    // Log successful upload
    console.log(`File uploaded successfully: ID=${shortId}, File=${fileName}, Size=${fileSizeMB}MB`);
    
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
