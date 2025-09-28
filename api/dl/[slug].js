const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;

export default async function handler(req, res) {
  const { slug } = req.query;
  if (!slug) return res.status(400).send('Missing slug');

  const parts = slug.split("-");
  const shortId = parts.pop();
  const fileName = decodeURIComponent(parts.join("-"));

  try {
    // ✅ Get recent messages from channel (to find mapping)
    const getMsgs = await fetch(`https://api.telegram.org/bot${TOKEN}/getUpdates?offset=-100`);
    const updates = await getMsgs.json();

    let fileId = null;

    if (updates.ok) {
      for (let u of updates.result.reverse()) {
        if (u.message?.chat?.id == Number(CHANNEL_ID) && u.message?.text?.startsWith(shortId + "|")) {
          const parts = u.message.text.split("|");
          if (parts[0] === shortId) {
            fileId = parts[1];
            break;
          }
        }
      }
    }

    if (!fileId) return res.status(404).send('File not found');

    // ✅ Get file path
    const gf = await fetch(`https://api.telegram.org/bot${TOKEN}/getFile?file_id=${fileId}`);
    const gfJson = await gf.json();
    if (!gfJson.ok) return res.status(502).send('Could not get file path');

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
