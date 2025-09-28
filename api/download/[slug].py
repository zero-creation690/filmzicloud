import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote
import json
import redis

TOKEN = os.environ.get('TELEGRAM_TOKEN')
REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

def get_redis_client():
    return redis.Redis(
        host=REDIS_URL.replace('https://', '').split(':')[0],
        port=6379,
        password=REDIS_TOKEN,
        ssl=True,
        decode_responses=True
    )

def get_from_redis(short_id):
    """Get file mapping from Redis"""
    try:
        r = get_redis_client()
        key = f"file:{short_id}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"Redis get error: {e}")
        return None

def get_file_direct_url(file_id):
    """Get direct download URL from Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/getFile"
    data = {'file_id': file_id}
    response = requests.post(url, json=data)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('ok'):
            file_path = result['result']['file_path']
            return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Extract slug from path
            path = self.path.strip('/')
            if not path.startswith('api/download/'):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'Not found')
                return
            
            slug = path.split('api/download/')[-1]
            
            if not slug or '-' not in slug:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid download link')
                return
            
            # Parse filename and ID
            parts = slug.rsplit('-', 1)
            if len(parts) != 2:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid download link format')
                return
            
            filename_encoded, short_id = parts
            original_filename = unquote(filename_encoded)
            
            # Get file data from Redis
            file_data = get_from_redis(short_id)
            
            if not file_data:
                # File not found
                self.send_response(404)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>File Not Found - Filmzi Cloud</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 100px auto; padding: 20px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
                        .container {{ background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; backdrop-filter: blur(10px); }}
                        .error-icon {{ font-size: 80px; margin-bottom: 20px; }}
                        .btn {{ background: white; color: #667eea; padding: 15px 30px; text-decoration: none; border-radius: 10px; display: inline-block; margin-top: 20px; font-weight: bold; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-icon">❌</div>
                        <h1>File Not Found</h1>
                        <p>The download link is invalid or the file has been removed.</p>
                        <p><strong>File ID:</strong> {short_id}</p>
                        <a href="https://t.me/filmzicloud_bot" class="btn">Upload New File</a>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_content.encode())
                return
            
            # Get file info
            file_id = file_data.get('file_id')
            file_name = file_data.get('file_name', original_filename)
            file_size = file_data.get('file_size', 0)
            size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
            
            # Get REAL download URL from Telegram
            download_url = get_file_direct_url(file_id)
            
            if download_url:
                # Redirect to Telegram's CDN for direct download
                self.send_response(302)
                self.send_header('Location', download_url)
                self.send_header('Content-Disposition', f'attachment; filename="{file_name}"')
                self.send_header('Cache-Control', 'public, max-age=31536000')  # 1 year cache
                self.end_headers()
            else:
                # Fallback: Show beautiful download page
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Download {file_name} - Filmzi Cloud</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; color: white; }}
                        .container {{ background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; backdrop-filter: blur(10px); margin-top: 50px; }}
                        .file-icon {{ font-size: 60px; text-align: center; margin-bottom: 20px; }}
                        .filename {{ font-size: 24px; font-weight: bold; word-break: break-word; text-align: center; }}
                        .file-info {{ background: rgba(255,255,255,0.2); padding: 20px; border-radius: 10px; margin: 20px 0; }}
                        .btn {{ background: white; color: #667eea; padding: 18px 40px; text-decoration: none; border-radius: 12px; display: inline-block; font-size: 18px; font-weight: bold; margin: 10px; width: 200px; text-align: center; }}
                        .btn:hover {{ background: #f0f0f0; transform: translateY(-2px); }}
                        .features {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 30px 0; }}
                        .feature {{ background: rgba(255,255,255,0.1); padding: 15px; border-radius: 10px; text-align: center; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="file-icon">📁</div>
                        <div class="filename">{file_name}</div>
                        
                        <div class="file-info">
                            <div><strong>Size:</strong> {size_mb} MB</div>
                            <div><strong>File ID:</strong> {short_id}</div>
                            <div><strong>Status:</strong> Ready for download</div>
                        </div>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{download_url if download_url else '#'}" class="btn" download="{file_name}">
                                ⬇️ DOWNLOAD NOW
                            </a>
                        </div>
                        
                        <div class="features">
                            <div class="feature">🛡️ Permanent Storage</div>
                            <div class="feature">🔗 Never Expires</div>
                            <div class="feature">⚡ Fast Download</div>
                            <div class="feature">💾 2GB Support</div>
                        </div>
                        
                        <div style="text-align: center; margin-top: 30px;">
                            <p>Powered by <strong>Filmzi Cloud</strong></p>
                            <a href="https://t.me/filmzicloud_bot" style="color: white; text-decoration: underline;">Upload more files</a>
                        </div>
                    </div>
                    
                    <script>
                        // Auto-start download if possible
                        setTimeout(function() {{
                            const downloadBtn = document.querySelector('.btn');
                            if(downloadBtn.href && downloadBtn.href !== '#') {{
                                window.location.href = downloadBtn.href;
                            }}
                        }}, 1000);
                    </script>
                </body>
                </html>
                """
                
                self.wfile.write(html_content.encode())
                
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            error_html = f"""
            <html>
            <body style="font-family: Arial; text-align: center; margin: 100px auto; max-width: 500px; background: #f8f9fa; padding: 50px;">
                <div style="font-size: 80px;">😵</div>
                <h2 style="color: #ff4444;">Download Error</h2>
                <p>Error: {str(e)}</p>
                <p>Please try again or contact support.</p>
                <a href="https://t.me/filmzicloud_bot" style="background: #0088cc; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; display: inline-block; margin-top: 20px;">Go to Bot</a>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
