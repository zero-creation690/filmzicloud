import { Redis } from "@upstash/redis";

// ---- Directly set your bot token and channel ID ----
const TOKEN = "8314502536:AAFLGwBTzCXPxvBPC5oMIiSKVyDaY5sm5mY";
const CHANNEL_ID = "-1002995694885";
const BASE_URL = "https://filmzicloud.vercel.app";

// ---- Redis connection ----
const redis = new Redis({
  url: "https://together-spaniel-13493.upstash.io",
  token: "ATS1AAIncDJmMTE3M2ZmZGRjYTU0NGEwOGExODRjYTA2YjUwM2UwZnAyMTM0OTM"
});

function randomId() {
  return Math.floor(10000 + Math.random() * 90000); // random 5-digit
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).send('❌ Method not allowed');

  const update = req.body;
  const message = update.message;
  if (!message) return res.status(200).send('No message');

  const chatId = message.chat.id;

  // Handle /start
  if (message.text && message.text.startsWith('/start')) {
    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        chat_id: chatId,
        text: `👋 Hello *${message.from.first_name || "friend"}*!\n\n📂 Send me any file and I’ll give you a permanent download link ⚡\n\n🛡️ Stored safely in *Filmzi Cloud*!`,
        parse_mode: "Markdown"
      })
    });
    return res.status(200).end();
  }

  // Handle file upload
  const fileObj = message.document || message.video || message.audio || null;
  if (!fileObj) return res.status(200).send('No file found');

  try {
    // Forward to channel (optional)
    await fetch(`https://api.telegram.org/bot${TOKEN}/forwardMessage`, {
      method: 'POST',
      body: new URLSearchParams({
        chat_id: CHANNEL_ID,
        from_chat_id: chatId,
        message_id: message.message_id
      })
    });

    const fileId = fileObj.file_id;
    const fileName = fileObj.file_name || 'file';
    const shortId = randomId();

    // Save in Redis
    await redis.set(shortId, JSON.stringify({ fileId, fileName }));

    const link = `${BASE_URL}/dl/${encodeURIComponent(fileName)}-${shortId}`;

    // Reply to user
    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        chat_id: chatId,
        text: `✅ Your link is ready!\n\n🎬 *File:* ${fileName}\n🔗 *Download:* ${link}\n\n⚡ Stored safely in Filmzi Cloud!`,
        parse_mode: "Markdown"
      })
    });

    return res.status(200).end();
  } catch (err) {
    console.error('Webhook error:', err);
    return res.status(500).send('Server error');
  }
}
