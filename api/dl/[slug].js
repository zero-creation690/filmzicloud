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
    // Method 1: Use getChatHistory to get ALL channel messages (most reliable)
    console.log(`📋 Using getChatHistory to search for ${shortId}...`);
    
    let foundMapping = null;
    let lastMessageId = 0; // Start from the latest message
    let batchCount = 0;
    let totalMessagesChecked = 0;
    const maxBatches = 1000; // Prevent infinite loops
    const messagesPerBatch = 100;

    while (!foundMapping && batchCount < maxBatches) {
      try {
        // Get messages from the channel
        const historyUrl = `https://api.telegram.org/bot${TOKEN}/getChatHistory`;
        const historyBody = {
          chat_id: CHANNEL_ID,
          limit: messagesPerBatch,
          offset_id: lastMessageId
        };

        const historyResp = await fetch(historyUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(historyBody)
        });

        const historyJson = await historyResp.json();

        if (!historyJson.ok) {
          console.log(`❌ getChatHistory failed: ${historyJson.description}`);
          
          // Fallback to getUpdates method
          return await searchUsingUpdates(shortId);
        }

        const messages = historyJson.result?.messages || [];
        if (messages.length === 0) {
          console.log(`📝 No more messages to check after ${totalMessagesChecked} messages`);
          break;
        }

        console.log(`📨 Batch ${batchCount + 1}: Checking ${messages.length} messages (total: ${totalMessagesChecked + messages.length})`);
        totalMessagesChecked += messages.length;

        // Search through messages for our mapping
        for (const message of messages) {
          if (!message.text) continue;
          
          const text = message.text;

          // Method 1: Look for JSON format
          if (text.startsWith(`FILE_MAP_${shortId}:`)) {
            try {
              const jsonStr = text.replace(`FILE_MAP_${shortId}:`, '');
              foundMapping = JSON.parse(jsonStr);
              console.log(`✅ Found JSON mapping for ${shortId} after ${totalMessagesChecked} messages:`, foundMapping);
              break;
            } catch (parseErr) {
              console.log(`⚠️ JSON parse error for ${shortId}:`, parseErr.message);
            }
          }

          // Method 2: Look for pipe format
          if (text.startsWith(`${shortId}|`)) {
            const parts = text.split('|');
            if (parts.length >= 3) {
              foundMapping = {
                id: shortId,
                file_id: parts[1],
                filename: parts[2],
                size: parts[3] ? parseInt(parts[3]) : null,
                timestamp: parts[4] ? parseInt(parts[4]) : null
              };
              console.log(`✅ Found pipe mapping for ${shortId} after ${totalMessagesChecked} messages:`, foundMapping);
              break;
            }
          }

          // Method 3: Look for database entry format
          if (text.startsWith(`DB_ENTRY:${shortId}:`)) {
            try {
              const jsonStr = text.replace(`DB_ENTRY:${shortId}:`, '');
              foundMapping = JSON.parse(jsonStr);
              console.log(`✅ Found DB mapping for ${shortId} after ${totalMessagesChecked} messages:`, foundMapping);
              break;
            } catch (parseErr) {
              console.log(`⚠️ DB parse error for ${shortId}:`, parseErr.message);
            }
          }

          // Update lastMessageId for pagination
          if (message.message_id < lastMessageId || lastMessageId === 0) {
            lastMessageId = message.message_id;
          }
        }

        if (foundMapping) break;

        // If we got fewer messages than requested, we've reached the end
        if (messages.length < messagesPerBatch) {
          console.log(`📝 Reached end of channel history after ${totalMessagesChecked} messages`);
          break;
        }

        batchCount++;

        // Small delay to avoid rate limiting
        if (batchCount % 10 === 0) {
          console.log(`⏸️ Brief pause after ${batchCount} batches...`);
          await new Promise(resolve => setTimeout(resolve, 200));
        }

      } catch (batchError) {
        console.error(`❌ Error in batch ${batchCount}:`, batchError);
        break;
      }
    }

    if (foundMapping) {
      // Cache the successful result
      mappingCache.set(shortId, {
        data: foundMapping,
        timestamp: Date.now()
      });
      console.log(`✅ SUCCESS: Found mapping after checking ${totalMessagesChecked} messages in ${batchCount} batches`);
      return foundMapping;
    }

    console.log(`❌ EXHAUSTIVE SEARCH COMPLETE: No mapping found for ${shortId} after checking ${totalMessagesChecked} messages`);
    
    // Last resort: try the updates method
    console.log(`🔄 Trying fallback search methods...`);
    return await searchUsingUpdates(shortId);

  } catch (error) {
    console.error(`❌ Critical error searching for ${shortId}:`, error);
    return await searchUsingUpdates(shortId);
  }
}

async function searchUsingUpdates(shortId) {
  console.log(`🔄 Fallback: Using getUpdates method for ${shortId}...`);
  
  try {
    // Clear any pending updates first
    await fetch(`https://api.telegram.org/bot${TOKEN}/getUpdates?offset=-1&limit=1`);
    
    let foundMapping = null;
    let offset = 0;
    let attempts = 0;
    const maxAttempts = 100;

    while (!foundMapping && attempts < maxAttempts) {
      const updatesUrl = `https://api.telegram.org/bot${TOKEN}/getUpdates?offset=${offset}&limit=100&allowed_updates=["message"]`;
      
      const resp = await fetch(updatesUrl);
      const json = await resp.json();
      
      if (!json.ok || !json.result?.length) {
        console.log(`❌ getUpdates batch ${attempts} failed or empty`);
        break;
      }

      console.log(`📨 Updates batch ${attempts}: checking ${json.result.length} updates`);

      for (const update of json.result) {
        const message = update.message;
        if (message?.chat?.id == CHANNEL_ID && message.text) {
          const text = message.text;
          
          if (text.includes(shortId)) {
            console.log(`🎯 Found message containing ${shortId}: ${text.substring(0, 100)}...`);
            
            // Parse the mapping
            if (text.startsWith(`FILE_MAP_${shortId}:`)) {
              try {
                const jsonStr = text.replace(`FILE_MAP_${shortId}:`, '');
                foundMapping = JSON.parse(jsonStr);
                break;
              } catch (e) { /* ignore */ }
            } else if (text.startsWith(`${shortId}|`)) {
              const parts = text.split('|');
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
        
        offset = Math.max(offset, update.update_id + 1);
      }

      if (foundMapping || json.result.length < 100) break;
      attempts++;
    }

    if (foundMapping) {
      mappingCache.set(shortId, {
        data: foundMapping,
        timestamp: Date.now()
      });
      console.log(`✅ Found via fallback method:`, foundMapping);
    }

    return foundMapping;
    
  } catch (error) {
    console.error(`❌ Fallback search error:`, error);
    return null;
  }
}

// Add OPTIONS handler for CORS
export default async function handler(req, res) {
  const { slug } = req.query;
  
  // Handle preflight requests
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Range, Content-Range');
    return res.status(200).end();
  }
  
  // Handle HEAD requests
  if (req.method === 'HEAD') {
    return res.status(200).end();
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

  console.log(`📥 Download request: slug=${slug}, shortId=${shortId}, fileName=${fileName}, channelId=${CHANNEL_ID}`);

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
      console.log(`❌ File mapping not found for ID: ${shortId} in channel: ${CHANNEL_ID}`);
      
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
            <h1>🔍 Advanced File Search Failed</h1>
            <div class="error">Exhaustive search completed - file mapping not found</div>
            
            <div class="info">
              <strong>Search Details:</strong><br>
              File ID: <code>${shortId}</code><br>
              Requested Name: <code>${fileName}</code><br>
              Channel ID: <code>${CHANNEL_ID}</code><br>
              Search Methods: getChatHistory + getUpdates + Cache
            </div>
            
            <div class="suggestion">
              <strong>🚨 Possible Issues:</strong><br>
              • File was never uploaded to the bot<br>
              • Bot doesn't have admin access to the storage channel<br>
              • File was uploaded to a different channel<br>
              • The file ID was typed incorrectly<br>
              • File mapping was corrupted during save
            </div>
            
            <div class="debug">
              <strong>🔧 For Bot Owner - Debug Steps:</strong><br>
              1. Check if bot is admin in channel ${CHANNEL_ID}<br>
              2. Manually search channel for "${shortId}"<br>
              3. Verify TOKEN and CHANNEL_ID in environment<br>
              4. Check bot logs during file upload<br>
              5. Test with a new file upload
            </div>
            
            <div class="debug">
              <strong>Support Reference:</strong> ${shortId} - ${new Date().toISOString()}
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
