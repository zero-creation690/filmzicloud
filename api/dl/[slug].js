// api/dl/[slug].js
const TOKEN = process.env.TELEGRAM_TOKEN;
const CHANNEL_ID = process.env.CHANNEL_ID;

// Enhanced cache with longer duration
const mappingCache = new Map();
const CACHE_DURATION = 60 * 60 * 1000; // 1 hour cache

async function findFileMapping(shortId) {
  console.log(`🔍 Searching for file ID: ${shortId}`);
  
  // Check cache first
  const cached = mappingCache.get(shortId);
  if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
    console.log(`✅ Found in cache: ${shortId}`);
    return cached.data;
  }

  try {
    // Method 1: Search using getUpdates (more reliable)
    let offset = -1;
    let foundMapping = null;
    let searchAttempts = 0;
    const maxSearchAttempts = 20;

    while (!foundMapping && searchAttempts < maxSearchAttempts) {
      const getUpdatesUrl = offset === -1 
        ? `https://api.telegram.org/bot${TOKEN}/getUpdates?limit=100&allowed_updates=["message"]`
        : `https://api.telegram.org/bot${TOKEN}/getUpdates?offset=${offset}&limit=100&allowed_updates=["message"]`;
      
      const resp = await fetch(getUpdatesUrl);
      const json = await resp.json();
      
      if (!json.ok || !json.result?.length) {
        console.log(`❌ getUpdates failed or no results: ${json.description || 'No data'}`);
        break;
      }

      console.log(`📨 Checking ${json.result.length} updates, attempt ${searchAttempts + 1}`);

      for (const update of json.result) {
        const message = update.message;
        if (message?.chat?.id == CHANNEL_ID && message.text) {
          const text = message.text;
          
          // Method 1: Look for new JSON format
          if (text.startsWith(`FILE_MAP_${shortId}:`)) {
            try {
              const jsonStr = text.replace(`FILE_MAP_${shortId}:`, '');
              const mappingData = JSON.parse(jsonStr);
              console.log(`✅ Found JSON mapping for ${shortId}:`, mappingData);
              foundMapping = mappingData;
              break;
            } catch (parseErr) {
              console.log(`⚠️ JSON parse error for ${shortId}:`, parseErr.message);
            }
          }
          
          // Method 2: Look for pipe-separated format (backup)
          if (text.startsWith(shortId + "|")) {
            const parts = text.split("|");
            if (parts.length >= 3) {
              foundMapping = {
                id: shortId,
                file_id: parts[1],
                filename: parts[2],
                size: parts[3] ? parseInt(parts[3]) : null,
                timestamp: parts[4] ? parseInt(parts[4]) : null
              };
              console.log(`✅ Found pipe mapping for ${shortId}:`, foundMapping);
              break;
            }
          }
        }
        offset = Math.max(offset, update.update_id + 1);
      }

      if (json.result.length < 100) break; // No more results
      searchAttempts++;
    }

    if (foundMapping) {
      // Cache the successful result
      mappingCache.set(shortId, {
        data: foundMapping,
        timestamp: Date.now()
      });
      return foundMapping;
    }

    // Method 2: Try using getChatHistory as fallback
    console.log(`🔄 Trying getChatHistory fallback for ${shortId}`);
    
    try {
      const historyResp = await fetch(`https://api.telegram.org/bot${TOKEN}/getChatHistory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: CHANNEL_ID,
          limit: 100
        })
      });
      
      if (historyResp.ok) {
        const historyJson = await historyResp.json();
        if (historyJson.result) {
          for (const message of historyJson.result) {
            if (message.text && message.text.includes(shortId)) {
              console.log(`📋 Found in history: ${message.text}`);
              // Process the same way as above
              if (message.text.startsWith(`FILE_MAP_${shortId}:`)) {
                try {
                  const jsonStr = message.text.replace(`FILE_MAP_${shortId}:`, '');
                  foundMapping = JSON.parse(jsonStr);
                  break;
                } catch (e) { /* ignore */ }
              } else if (message.text.startsWith(shortId + "|")) {
                const parts = message.text.split("|");
                if (parts.length >= 3) {
                  foundMapping = {
                    id: shortId,
                    file_id: parts[1],
                    filename: parts[2],
                    size: parts[3] ? parseInt(parts[3]) : null,
                    timestamp: parts[4] ? parseInt(parts[4]) : null
                  };
                  break;
                }
              }
            }
          }
        }
      }
    } catch (historyErr) {
      console.log(`⚠️ getChatHistory failed:`, historyErr.message);
    }

    if (foundMapping) {
      mappingCache.set(shortId, {
        data: foundMapping,
        timestamp: Date.now()
      });
      console.log(`✅ Found via fallback method:`, foundMapping);
      return foundMapping;
    }

    console.log(`❌ No mapping found for ${shortId} after all methods`);
    return null;

  } catch (error) {
    console.error(`❌ Error searching for ${shortId}:`, error);
    return null;
  }
}

export default async function handler(req, res) {
  const { slug } = req.query;
  
  // Handle HEAD requests (for link previews)
  if (req.method === 'HEAD') {
    res.status(200).end();
    return;
  }
  
  // Handle OPTIONS requests (CORS preflight)
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Range, Content-Range');
    res.status(200).end();
    return;
  }
  
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

  console.log(`📥 Download request: slug=${slug}, shortId=${shortId}, fileName=${fileName}`);

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
          <div class="error">The file ID "${shortId}" is invalid.</div>
          <p>File IDs should be 6 digits long. Please check your download link.</p>
        </div>
      </body>
      </html>
    `);
  }

  try {
    // Find the file mapping with enhanced search
    const mappingData = await findFileMapping(shortId);
    
    if (!mappingData) {
      console.log(`❌ File mapping not found for ID: ${shortId}`);
      
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
            .info { color: #666; margin: 15px 0; background: #f8f9fa; padding: 10px; border-radius: 5px; }
            .suggestion { background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }
            .debug { background: #fff3cd; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 12px; color: #856404; }
          </style>
        </head>
        <body>
          <div class="container">
            <div class="logo">🎬 Filmzi Cloud</div>
            <h1>File Not Found</h1>
            <div class="error">The requested file could not be located in our storage system.</div>
            
            <div class="info">
              <strong>Search Details:</strong><br>
              File ID: <code>${shortId}</code><br>
              Requested Name: <code>${fileName}</code><br>
              Channel ID: <code>${CHANNEL_ID}</code>
            </div>
            
            <div class="suggestion">
              <strong>Troubleshooting:</strong><br>
              • Verify the download link is complete and correct<br>
              • Check if the file was recently uploaded (may take a moment to index)<br>
              • Contact the person who shared this link<br>
              • Try generating a new link if you have the original file
            </div>
            
            <div class="debug">
              <strong>For Support:</strong> Reference ID ${shortId} - ${new Date().toISOString()}
            </div>
          </div>
        </body>
        </html>
      `);
    }

    const fileId = mappingData.file_id;
    const originalFilename = mappingData.filename || fileName;
    
    console.log(`✅ Found mapping for ${shortId}:`, {
      file_id: fileId,
      filename: originalFilename,
      size: mappingData.size
    });

    // Get file information from Telegram
    const getFileResponse = await fetch(`https://api.telegram.org/bot${TOKEN}/getFile?file_id=${fileId}`);
    const getFileJson = await getFileResponse.json();
    
    if (!getFileJson.ok) {
      console.error(`❌ Telegram getFile error for ${shortId}:`, getFileJson);
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
            <p>The file exists in our records but Telegram couldn't provide access.</p>
            <p><strong>Possible causes:</strong><br>
            • File was deleted from Telegram<br>
            • Temporary Telegram server issue<br>
            • File ID has expired</p>
            <small>Telegram Error: ${getFileJson.description || 'Unknown error'}</small>
          </div>
        </body>
        </html>
      `);
    }

    const filePath = getFileJson.result.file_path;
    const telegramFileUrl = `https://api.telegram.org/file/bot${TOKEN}/${filePath}`;
    
    console.log(`📥 Downloading from Telegram: ${originalFilename} (${mappingData.size || 'unknown'} bytes)`);

    // Prepare headers for the Telegram request
    const telegramHeaders = {};
    const range = req.headers.range;
    if (range) {
      telegramHeaders['Range'] = range;
      console.log(`📊 Range request: ${range}`);
    }

    // Fetch the file from Telegram
    const fileResponse = await fetch(telegramFileUrl, {
      headers: telegramHeaders
    });
    
    if (!fileResponse.ok) {
      console.error(`❌ Telegram file fetch failed for ${shortId}: ${fileResponse.status} ${fileResponse.statusText}`);
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
            <div class="error">Unable to download the file from Telegram servers.</div>
            <p>Status: ${fileResponse.status} ${fileResponse.statusText}</p>
            <p>Please try again in a few moments. If the problem persists, the file may no longer be available on Telegram's servers.</p>
          </div>
        </body>
        </html>
      `);
    }

    // Set response headers for automatic download
    const contentType = fileResponse.headers.get('content-type') || 'application/octet-stream';
    const contentLength = fileResponse.headers.get('content-length');
    
    // Ensure proper filename encoding
    const safeFilename = originalFilename.replace(/[^\w\s.-]/g, '_');
    
    // Force download headers - these make the browser download automatically
    res.setHeader('Content-Type', 'application/octet-stream'); // Force download instead of preview
    res.setHeader('Content-Disposition', `attachment; filename="${safeFilename}"; filename*=UTF-8''${encodeURIComponent(originalFilename)}`);
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate'); // Prevent caching issues
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Download-Options', 'noopen');
    res.setHeader('X-Powered-By', 'Filmzi Cloud Storage');
    res.setHeader('X-File-ID', shortId);
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Range, Content-Range');
    
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
      
      console.log(`📊 Serving partial content: ${start}-${end}/${contentLength}`);
    } else {
      res.setHeader('Accept-Ranges', 'bytes');
    }

    // Stream the file to the client with better error handling
    let bytesTransferred = 0;
    
    if (fileResponse.body) {
      const reader = fileResponse.body.getReader();
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          bytesTransferred += value.length;
          
          if (!res.write(value)) {
            // If write buffer is full, wait for drain
            await new Promise((resolve, reject) => {
              res.once('drain', resolve);
              res.once('error', reject);
            });
          }
        }
        
        console.log(`✅ Successfully served ${originalFilename} (${bytesTransferred} bytes) for ID: ${shortId}`);
        
      } catch (streamError) {
        console.error(`❌ Streaming error for ${shortId}:`, streamError);
        if (!res.headersSent) {
          res.status(500).send('File streaming interrupted');
        }
      } finally {
        reader.releaseLock();
      }
    }
    
    res.end();

  } catch (error) {
    console.error(`❌ Download handler error for ${shortId}:`, error);
    
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
            <small>Error ID: ${Date.now()} | File ID: ${shortId}</small>
          </div>
        </body>
        </html>
      `);
    }
  }
}
