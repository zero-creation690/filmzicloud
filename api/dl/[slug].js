// api/dl/[slug].js
const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;

export default async function handler(req, res) {
  const { slug } = req.query;
  if (!slug) return res.status(400).send('Missing slug');

  const parts = slug.split("-");
  const shortId = parts.pop();
  const fileName = decodeURIComponent(parts.join("-"));

  try {
    // Get channel messages (search mapping)
    const resp = await fetch(`https://api.telegram.org/bot${TOKEN}/getUpdates`);
    const json = await resp.json();

    let fileId = null;
    for (const upd of json.result) {
      if (upd.message && upd.message.chat.id == CHANNEL_ID) {
        const txt = upd.message.text || "";
        if (txt.startsWith(shortId + "|")) {
          fileId = txt.split("|")[1];
          break;
        }
      }
    }

    if (!fileId) return res.status(404).send('File not found');

    // Ask Telegram for file path
    const gf = await fetch(`https://api.telegram.org/bot${TOKEN}/getFile?file_id=${fileId}`);
    const gfJson = await gf.json();
    if (!gfJson.ok) return res.status(502).send('Could not get file');

    const file_path = gfJson.result.file_path;
    const fileUrl = `https://api.telegram.org/file/bot${TOKEN}/${file_path}`;

    // Proxy with streaming + range support
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
