import { Redis } from '@upstash/redis';
import fetch from 'node-fetch';

const TOKEN = process.env.TELEGRAM_TOKEN;
const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL,
  token: process.env.UPSTASH_REDIS_REST_TOKEN
});

export default async function handler(req, res) {
  const { shortId, fileName } = req.query;
  if (!shortId || !fileName) return res.status(400).send('Missing parameters');

  try {
    // Get file mapping
    const data = await redis.get(`file:${shortId}`);
    if (!data) return res.status(404).send('File not found');

    const { fileId } = data; // <-- Fix: no JSON.parse

    // Get Telegram file path
    const gf = await fetch(`https://api.telegram.org/bot${TOKEN}/getFile?file_id=${fileId}`);
    const gfJson = await gf.json();
    if (!gfJson.ok) return res.status(502).send('Could not get file from Telegram');

    const file_path = gfJson.result.file_path;
    const fileUrl = `https://api.telegram.org/file/bot${TOKEN}/${file_path}`;

    // Download as buffer (works for all sizes)
    const fileResp = await fetch(fileUrl);
    if (!fileResp.ok) return res.status(502).send('Failed to fetch file from Telegram');

    const buffer = await fileResp.arrayBuffer();

    res.setHeader('Content-Disposition', `attachment; filename="${encodeURIComponent(fileName)}"`);
    res.setHeader('Content-Type', 'application/octet-stream');
    res.status(200).send(Buffer.from(buffer));

  } catch (err) {
    console.error('Download error:', err);
    return res.status(500).send('Download error');
  }
}
