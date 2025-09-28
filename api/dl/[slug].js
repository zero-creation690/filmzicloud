import { Redis } from "@upstash/redis";

const TOKEN = process.env.TELEGRAM_TOKEN;
const redis = new Redis({
  url: process.env.UPSTASH_REDIS_URL,
  token: process.env.UPSTASH_REDIS_TOKEN
});

export default async function handler(req, res) {
  const { slug } = req.query;
  if (!slug) return res.status(400).send('Missing slug');

  const parts = slug.split("-");
  const shortId = parts.pop();
  const fileName = decodeURIComponent(parts.join("-"));

  try {
    // ✅ Fetch file mapping from Redis
    const data = await redis.get(shortId);
    if (!data) return res.status(404).send('File not found');

    const { fileId } = JSON.parse(data);

    // ✅ Get Telegram file path
    const gf = await fetch(`https://api.telegram.org/bot${TOKEN}/getFile?file_id=${fileId}`);
    const gfJson = await gf.json();
    if (!gfJson.ok) return res.status(502).send('Could not get file path');

    const file_path = gfJson.result.file_path;
    const fileUrl = `https://api.telegram.org/file/bot${TOKEN}/${file_path}`;

    // Proxy streaming with range support
    const headers = {};
    if (req.headers.range) headers['range'] = req.headers.range;

    const upstream = await fetch(fileUrl, { headers });
    res.status(upstream.status);
    upstream.headers.forEach((v, k) => res.setHeader(k, v));
    res.setHeader("Content-Disposition", `attachment; filename="${encodeURIComponent(fileName)}"`);

    if (!upstream.body) return res.end();
    upstream.body.pipe(res);
  } catch (err) {
    console.error('dl error', err);
    return res.status(500).send('Download error');
  }
}
