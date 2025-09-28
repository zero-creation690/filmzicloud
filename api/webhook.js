import { Redis } from '@upstash/redis';

const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;
const BASE_URL = process.env.BASE_URL || '';
const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL,
  token: process.env.UPSTASH_REDIS_REST_TOKEN
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

  // /start message
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
    return res.status(200).send('ok');
  }

  // Handle file upload
  const fileObj = message.document || message.video || message.audio;
  if (!fileObj) return res.status(200).send('No file found');

  try {
    // Forward to channel (permanent storage)
    const fwd = await fetch(`https://api.telegram.org/bot${TOKEN}/forwardMessage`, {
      method: 'POST',
      body: new URLSearchParams({
        chat_id: CHANNEL_ID,
        from_chat_id: chatId,
        message_id: message.message_id
      })
    });
    const fwdJson = await fwd.json();

    const fileId = fileObj.file_id;
    const fileName = fileObj.file_name || 'file';
    const shortId = randomId();

    // Save mapping in Redis: shortId => { fileId, fileName }
    await redis.set(`file:${shortId}`, JSON.stringify({ fileId, fileName }));

    // Build permanent link
    const link = `${BASE_URL}/dl/${encodeURIComponent(fileName)}-${shortId}`;

    // Reply back to user
    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        chat_id: chatId,
        text: `✅ Your link is ready!\n\n🎬 *File:* ${fileName}\n🔗 *Download:* ${link}\n\n⚡ Stored safely in Filmzi Cloud!`,
        parse_mode: "Markdown"
      })
    });

    return res.status(200).send('ok');
  } catch (err) {
    console.error('webhook error', err);
    return res.status(500).send('Server error');
  }
}
