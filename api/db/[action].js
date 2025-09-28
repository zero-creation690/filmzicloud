// api/db/[action].js - Optional database backup for file mappings
// This creates a backup storage system using Telegram as a database

const TOKEN = process.env.TELEGRAM_TOKEN;
const DB_CHANNEL_ID = process.env.DB_CHANNEL_ID || process.env.CHANNEL_ID; // Separate DB channel or same channel
const ADMIN_CHAT_ID = process.env.ADMIN_CHAT_ID; // Optional: your chat ID for notifications

export default async function handler(req, res) {
  const { action } = req.query;

  // Only allow POST requests for security
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    switch (action) {
      case 'save':
        return await saveFileMapping(req, res);
      case 'get':
        return await getFileMapping(req, res);
      case 'list':
        return await listAllMappings(req, res);
      case 'cleanup':
        return await cleanupOldMappings(req, res);
      default:
        return res.status(400).json({ error: 'Invalid action' });
    }
  } catch (error) {
    console.error('Database operation error:', error);
    return res.status(500).json({ error: 'Database operation failed' });
  }
}

async function saveFileMapping(req, res) {
  const { shortId, fileId, filename, size, userId, username } = req.body;
  
  if (!shortId || !fileId || !filename) {
    return res.status(400).json({ error: 'Missing required fields' });
  }

  const mappingData = {
    id: shortId,
    file_id: fileId,
    filename: filename,
    size: size || 0,
    user_id: userId,
    username: username,
    timestamp: Math.floor(Date.now() / 1000),
    created: new Date().toISOString()
  };

  // Save to database channel with multiple formats for redundancy
  const dbEntries = [
    `DB_ENTRY:${shortId}:${JSON.stringify(mappingData)}`,
    `${shortId}|${fileId}|${filename}|${size}|${userId}|${username}|${mappingData.timestamp}`,
    `SEARCH_${shortId}_${filename.toLowerCase().replace(/[^a-z0-9]/g, '_')}_${fileId}`
  ];

  let savedCount = 0;
  for (const entry of dbEntries) {
    try {
      const saveResp = await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: DB_CHANNEL_ID,
          text: entry,
          disable_notification: true
        })
      });
      
      if (saveResp.ok) savedCount++;
    } catch (e) {
      console.error(`Failed to save DB entry ${savedCount + 1}:`, e);
    }
  }

  return res.json({
    success: true,
    saved_entries: savedCount,
    mapping_id: shortId
  });
}

async function getFileMapping(req, res) {
  const { shortId } = req.body;
  
  if (!shortId) {
    return res.status(400).json({ error: 'Missing shortId' });
  }

  // Search for the mapping
  let foundMapping = null;
  let offset = -1;
  let attempts = 0;
  const maxAttempts = 100; // Unlimited search

  while (!foundMapping && attempts < maxAttempts) {
    try {
      const searchUrl = offset === -1 
        ? `https://api.telegram.org/bot${TOKEN}/getUpdates?limit=100&allowed_updates=["message"]`
        : `https://api.telegram.org/bot${TOKEN}/getUpdates?offset=${offset}&limit=100&allowed_updates=["message"]`;
      
      const resp = await fetch(searchUrl);
      const json = await resp.json();
      
      if (!json.ok || !json.result?.length) break;

      for (const update of json.result) {
        const message = update.message;
        if (message?.chat?.id == DB_CHANNEL_ID && message.text) {
          const text = message.text;
          
          // Check for DB entry format
          if (text.startsWith(`DB_ENTRY:${shortId}:`)) {
            try {
              const jsonStr = text.replace(`DB_ENTRY:${shortId}:`, '');
              foundMapping = JSON.parse(jsonStr);
              break;
            } catch (e) { /* ignore */ }
          }
          
          // Check for pipe format
          if (text.startsWith(`${shortId}|`)) {
            const parts = text.split('|');
            if (parts.length >= 4) {
              foundMapping = {
                id: shortId,
                file_id: parts[1],
                filename: parts[2],
                size: parts[3] ? parseInt(parts[3]) : null,
                user_id: parts[4] ? parseInt(parts[4]) : null,
                username: parts[5] || null,
                timestamp: parts[6] ? parseInt(parts[6]) : null
              };
              break;
            }
          }
        }
        offset = Math.max(offset, update.update_id + 1);
      }

      if (json.result.length < 100) break;
      attempts++;
      
    } catch (searchError) {
      console.error('Search error:', searchError);
      break;
    }
  }

  if (foundMapping) {
    return res.json({
      success: true,
      mapping: foundMapping,
      found_after_attempts: attempts + 1
    });
  } else {
    return res.status(404).json({
      success: false,
      error: 'Mapping not found',
      searched_attempts: attempts
    });
  }
}

async function listAllMappings(req, res) {
  const mappings = [];
  let offset = -1;
  let attempts = 0;
  const maxAttempts = 50;

  while (attempts < maxAttempts) {
    try {
      const searchUrl = offset === -1 
        ? `https://api.telegram.org/bot${TOKEN}/getUpdates?limit=100&allowed_updates=["message"]`
        : `https://api.telegram.org/bot${TOKEN}/getUpdates?offset=${offset}&limit=100&allowed_updates=["message"]`;
      
      const resp = await fetch(searchUrl);
      const json = await resp.json();
      
      if (!json.ok || !json.result?.length) break;

      for (const update of json.result) {
        const message = update.message;
        if (message?.chat?.id == DB_CHANNEL_ID && message.text) {
          const text = message.text;
          
          if (text.startsWith('DB_ENTRY:')) {
            try {
              const parts = text.split(':');
              if (parts.length >= 3) {
                const shortId = parts[1];
                const jsonStr = text.replace(`DB_ENTRY:${shortId}:`, '');
                const mapping = JSON.parse(jsonStr);
                mappings.push(mapping);
              }
            } catch (e) { /* ignore malformed entries */ }
          }
        }
        offset = Math.max(offset, update.update_id + 1);
      }

      if (json.result.length < 100) break;
      attempts++;
      
    } catch (error) {
      console.error('List error:', error);
      break;
    }
  }

  return res.json({
    success: true,
    total_mappings: mappings.length,
    mappings: mappings.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0)),
    searched_attempts: attempts
  });
}

async function cleanupOldMappings(req, res) {
  const { days_old = 365 } = req.body; // Default: cleanup files older than 1 year
  const cutoffTimestamp = Math.floor(Date.now() / 1000) - (days_old * 24 * 60 * 60);
  
  // This is a placeholder - in a real implementation, you'd want to be more careful
  // about deleting messages from Telegram
  
  return res.json({
    success: true,
    message: `Cleanup functionality disabled for safety. Cutoff would be: ${new Date(cutoffTimestamp * 1000).toISOString()}`,
    cutoff_timestamp: cutoffTimestamp
  });
}
