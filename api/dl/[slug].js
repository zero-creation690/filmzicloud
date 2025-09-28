// api/dl/[slug].js
const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;

// Cache for file mappings to reduce API calls
const mappingCache = new Map();
const CACHE_DURATION = 30 * 60 * 1000; // 30 minutes

async function findFileMapping(shortId) {
  // Check cache first
  const cacheKey = shortId;
  const cached = mappingCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
    return cached.data;
  }

  let offset = 0;
  const limit = 100;
  let attempts = 0;
  const maxAttempts = 50; // Prevent infinite loops

  while (attempts < maxAttempts) {
    try {
      const resp = await fetch(`https://api.telegram.org/bot${TOKEN}/getUpdates?offset=${offset}&limit=${limit}`);
      const json = await resp.json();
      
      if (!json.ok || !json.result.length) break;

      for (const update of json.result) {
        const message = update.message;
        if (message && message.chat && message.chat.id == CHANNEL_ID) {
          const text = message.text || "";
          
          // Look for mapping data
          if (text.startsWith('MAPPING:')) {
            try {
              const mappingStr = text.replace('MAPPING:', '');
              const mappingData = JSON.parse(mappingStr);
              
              if (mappingData.id == shortId) {
                // Cache the result
                mappingCache.set(cacheKey, {
                  data: mappingData,
                  timestamp: Date.now()
                });
                return mappingData;
              }
            } catch (parseErr) {
              // Handle old format: "shortId|fileId|filename"
              if (text.startsWith(shortId + "|")) {
                const parts = text.split("|");
                if (parts.length >= 3) {
                  const legacyMapping = {
                    id: shortId,
                    file_id: parts[1],
                    filename: parts[2],
                    size: null,
                    timestamp: null
                  };
                  mappingCache.set(cacheKey, {
                    data: legacyMapping,
                    timestamp: Date.now()
                  });
                  return legacyMapping;
                }
              }
            }
          }
        }
        offset = Math.max(offset, update.update_id + 1);
      }

      if (json.result.length < limit) break;
      attempts++;
      
    } catch (apiErr) {
      console.error('API Error:', apiErr);
      break;
    }
  }

  return null;
}

export default async function handler(req, res) {
  const { slug } = req.query;
  
  if (!slug) {
    return res.status(400).send(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Invalid Link - Filmzi Cloud</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
          body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
          .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
          .error { color: #e74c3c; font-size: 18px; margin: 20px 0; }
          .logo { font-size: 24px; font-weight: bold; color: #3498db; margin-bottom: 20px; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="logo">🎬 Filmzi Cloud</div>
          <h1>Invalid Download Link</h1>
          <div class="error">The download link is malformed or incomplete.</div>
          <p>Please check your link and try again.</p>
        </div>
      </body>
      </html>
    `);
  }

  // Parse slug to extract shortId and filename
  const parts = slug.split("-");
  const shortId = parts.pop();
  const fileName = decodeURIComponent(parts.join("-"));

  if (!shortId || shortId.length < 5) {
    return res.status(400).send(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Invalid File ID - Filmzi Cloud</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
          body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
          .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
          .error { color: #e74c3c; font-size: 18px; margin: 20px 0; }
          .logo { font-size: 24px; font-weight: bold; color: #3498db; margin-bottom: 20px; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="logo">🎬 Filmzi Cloud</div>
          <h1>Invalid File ID</h1>
          <div class="error">The file ID in your link is invalid.</div>
          <p>Please check your download link and try again.</p>
        </div>
      </body>
      </html>
    `);
  }

  try {
    console.log(`Looking for file with ID: ${shortId}, filename: ${fileName}`);
    
    // Find the file mapping
    const mappingData = await findFileMapping(shortId);
    
    if (!mappingData) {
      return res.status(404).send(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>File Not Found - Filmzi Cloud</title>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
            .container { max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .error { color: #e74c3c; font-size: 18px; margin: 20px 0; }
            .logo { font-size: 28px; font-weight: bold; color: #3498db; margin-bottom: 20px; }
            .info { color: #666; margin: 15px 0; }
            .suggestion { background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }
          </style>
        </head>
        <body>
          <div class="container">
            <div class="logo">🎬 Filmzi Cloud</div>
            <h1>File Not Found</h1>
            <div class="error">The requested file could not be located in our storage.</div>
            <div class="info">File ID: ${shortId}</div>
            <div class="info">Requested: ${fileName}</div>
            
            <div class="suggestion">
              <strong>Possible reasons:</strong><br>
              • The link may have been typed incorrectly<br>
              • The file might have been removed<br>
              • This is an old link format<br>
            </div>
            
            <p>Please check your link or contact the person who shared it with you.</p>
          </div>
        </body>
        </html>
      `);
    }

    const fileId = mappingData.file_id;
    const originalFilename = mappingData.filename || fileName;
    
    console.log(`Found file mapping:`, mappingData);

    // Get file information from Telegram
    const getFileResponse = await fetch(`https://api.telegram.org/bot${TOKEN}/getFile?file_id=${fileId}`);
    const getFileJson = await getFileResponse.json();
    
    if (!getFileJson.ok) {
      console.error('Telegram getFile error:', getFileJson);
      return res.status(502).send(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>File Access Error - Filmzi Cloud</title>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
            .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .error { color: #e74c3c; font-size: 18px; margin: 20px 0; }
            .logo { font-size: 24px; font-weight: bold; color: #3498db; margin-bottom: 20px; }
          </style>
        </head>
        <body>
          <div class="container">
            <div class="logo">🎬 Filmzi Cloud</div>
            <h1>File Access Error</h1>
            <div class="error">Unable to access the file from Telegram servers.</div>
            <p>Please try again in a few moments. If the problem persists, the file may have been removed by Telegram.</p>
            <small>Error: ${getFileJson.description || 'Unknown error'}</small>
          </div>
        </body>
        </html>
      `);
    }

    const filePath = getFileJson.result.file_path;
    const telegramFileUrl = `https://api.telegram.org/file/bot${TOKEN}/${filePath}`;
    
    console.log(`Downloading from Telegram: ${telegramFileUrl}`);

    // Prepare headers for the Telegram request
    const telegramHeaders = {};
    const range = req.headers.range;
    if (range) {
      telegramHeaders['Range'] = range;
    }

    // Fetch the file from Telegram
    const fileResponse = await fetch(telegramFileUrl, {
      headers: telegramHeaders
    });
    
    if (!fileResponse.ok) {
      console.error(`Telegram file fetch failed: ${fileResponse.status} ${fileResponse.statusText}`);
      return res.status(fileResponse.status).send(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>Download Error - Filmzi Cloud</title>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
            .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .error { color: #e74c3c; font-size: 18px; margin: 20px 0; }
            .logo { font-size: 24px; font-weight: bold; color: #3498db; margin-bottom: 20px; }
          </style>
        </head>
        <body>
          <div class="container">
            <div class="logo">🎬 Filmzi Cloud</div>
            <h1>Download Failed</h1>
            <div class="error">Unable to download the file at this time.</div>
            <p>Please try again later. If the problem continues, the file may no longer be available.</p>
          </div>
        </body>
        </html>
      `);
    }

    // Set response headers
    const contentType = fileResponse.headers.get('content-type') || 'application/octet-stream';
    const contentLength = fileResponse.headers.get('content-length');
    
    res.setHeader('Content-Type', contentType);
    res.setHeader('Content-Disposition', `attachment; filename="${originalFilename}"`);
    res.setHeader('Cache-Control', 'public, max-age=31536000'); // Cache for 1 year
    res.setHeader('X-Powered-By', 'Filmzi Cloud Storage');
    
    if (contentLength) {
      res.setHeader('Content-Length', contentLength);
    }

    // Handle range requests for streaming/partial content
    if (range && contentLength) {
      const parts = range.replace(/bytes=/, "").split("-");
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : parseInt(contentLength, 10) - 1;
      const chunksize = (end - start) + 1;
      
      res.status(206);
      res.setHeader('Content-Range', `bytes ${start}-${end}/${contentLength}`);
      res.setHeader('Accept-Ranges', 'bytes');
      res.setHeader('Content-Length', chunksize.toString());
    } else {
      res.setHeader('Accept-Ranges', 'bytes');
    }

    // Stream the file to the client
    if (fileResponse.body) {
      const reader = fileResponse.body.getReader();
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          if (!res.write(value)) {
            // If write buffer is full, wait for drain
            await new Promise(resolve => res.once('drain', resolve));
          }
        }
      } catch (streamError) {
        console.error('Streaming error:', streamError);
        if (!res.headersSent) {
          res.status(500).send('Streaming error');
        }
      } finally {
        reader.releaseLock();
      }
    }
    
    res.end();
    console.log(`Successfully served file: ${originalFilename} (ID: ${shortId})`);

  } catch (error) {
    console.error('Download handler error:', error);
    
    if (!res.headersSent) {
      return res.status(500).send(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>Server Error - Filmzi Cloud</title>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
            .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .error { color: #e74c3c; font-size: 18px; margin: 20px 0; }
            .logo { font-size: 24px; font-weight: bold; color: #3498db; margin-bottom: 20px; }
          </style>
        </head>
        <body>
          <div class="container">
            <div class="logo">🎬 Filmzi Cloud</div>
            <h1>Server Error</h1>
            <div class="error">An unexpected error occurred while processing your download.</div>
            <p>Please try again in a few moments. If the problem persists, please contact support.</p>
            <small>Error ID: ${Date.now()}</small>
          </div>
        </body>
        </html>
      `);
    }
  }
}
