import { Redis } from "@upstash/redis";

const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;
const BASE_URL = process.env.BASE_URL || '';
const redis = new Redis({
  url: process.env.UPSTASH_REDIS_URL,
  token: process.env.UPSTASH_REDIS_TOKEN
});

function randomId() {
  return Math.floor(10000 + Math.random() * 90000); // random 5-digit
}

// Escape MarkdownV2 special characters
function escapeMarkdownV2(text = "") {
  return text.replace(/[_*[\]()~`>#+\-=|{}.!]/g, "\\$&");
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).send('❌ Method not allowed');

  const update = req.body;
  console.log("Received update:", JSON.stringify(update));

  const message = update.message;
  if (!message) return res.status(200).send('No message');

  const chatId = message.chat.id;

  // ✅ Handle /start
  if (message.text && message.text.startsWith('/start')) {
    try {
      const name = escapeMarkdownV2(message.from.first_name || "friend");
      await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          chat_id: chatId,
          text: `👋 Hello *${name}*!\n\n📂 Send me any file and I’ll give you a permanent download link ⚡\n\n🛡️ Stored safely in *Filmzi Cloud*!`,
          parse_mode: "MarkdownV2"
        })
      });
      console.log("/start message sent to", chatId);
      return res.status(200).end();
    } catch (err) {
      console.error("Error sending /start message:", err);
      return res.status(500).send("Server error");
    }
  }

  // ✅ Handle file upload
  const fileObj = message.document || message.video || message.audio || null;
  if (!fileObj) return res.status(200).send('No file found');

  try {
    // Forward file to channel (permanent storage)
    const fwd = await fetch(`https://api.telegram.org/bot${TOKEN}/forwardMessage`, {
      method: 'POST',
      body: new URLSearchParams({
        chat_id: CHANNEL_ID,
        from_chat_id: chatId,
        message_id: message.message_id
      })
    });
    const fwdJson = await fwd.json();
    if (!fwdJson.ok) throw new Error(JSON.stringify(fwdJson));

    const fileId = fileObj.file_id;
    const fileName = fileObj.file_name || 'file';
    const shortId = randomId();

    // Save in Redis
    await redis.set(shortId, JSON.stringify({ fileId, fileName }));

    // Build permanent link
    const base = BASE_URL || `https://${req.headers.host}`;
    const link = `${base}/dl/${encodeURIComponent(fileName)}-${shortId}`;

    // Reply to user
    await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        chat_id: chatId,
        text: `✅ Your link is ready!\n\n🎬 *File:* ${escapeMarkdownV2(fileName)}\n🔗 *Download:* ${link}\n\n⚡ Stored safely in Filmzi Cloud!`,
        parse_mode: "MarkdownV2"
      })
    });

    console.log("File processed and link sent to", chatId);
    return res.status(200).end();
  } catch (err) {
    console.error('Webhook file handling error:', err);
    return res.status(500).send('Server error');
  }
}
