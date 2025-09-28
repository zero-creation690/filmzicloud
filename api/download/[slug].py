import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote
import json
import redis

TOKEN = os.environ.get('TELEGRAM_TOKEN')
REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')
BASE_URL = os.environ.get('BASE_URL', 'https://filmzicloud.vercel.app')

def get_redis_client():
    return redis.Redis(
        host=REDIS_URL.replace('https://', '').split(':')[0],
        port=6379,
        password=REDIS_TOKEN,
        ssl=True,
        decode_responses=True
    )

def get_from_redis(short_id):
    try:
        r = get_redis_client()
        key = f"file:{short_id}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        return None

def get_file_direct_url(file_id):
    url = f"https://api.telegram.org/bot{TOKEN}/getFile"
    data = {'file_id': file_id}
    response = requests.post(url, json=data)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('ok'):
            file_path = result['result']['file_path']
            return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    return None

def format_file_size(bytes_size):
    if bytes_size == 0:
        return "0 B"
    
    sizes = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_size >= 1024 and i < len(sizes) - 1:
        bytes_size /= 1024.0
        i += 1
    
    return f"{bytes_size:.2f} {sizes[i]}"

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
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
            
            parts = slug.rsplit('-', 1)
            if len(parts) != 2:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid download link format')
                return
            
            filename_encoded, short_id = parts
            original_filename = unquote(filename_encoded)
            
            file_data = get_from_redis(short_id)
            
            if not file_data:
                self.send_response(404)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>File Not Found - FileStreamBot</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
                        .container {{ background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; backdrop-filter: blur(10px); text-align: center; max-width: 500px; border: 1px solid rgba(255,255,255,0.2); }}
                        .error-icon {{ font-size: 80px; margin-bottom: 20px; color: #ff6b6b; }}
                        h1 {{ font-size: 28px; margin-bottom: 15px; color: #ff6b6b; }}
                        .btn {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 10px; display: inline-block; margin: 10px; font-weight: bold; border: none; cursor: pointer; transition: transform 0.2s; }}
                        .btn:hover {{ transform: translateY(-2px); }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-icon">❌</div>
                        <h1>File Not Found</h1>
                        <p style="margin-bottom: 20px; opacity: 0.8;">The download link is invalid or the file has been removed.</p>
                        <p style="margin-bottom: 20px;"><strong>File ID:</strong> {short_id}</p>
                        <a href="{BASE_URL}" class="btn">🔄 Go to FileStreamBot</a>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_content.encode())
                return
            
            file_id = file_data.get('file_id')
            file_name = file_data.get('file_name', original_filename)
            file_size = file_data.get('file_size', 0)
            size_readable = format_file_size(file_size)
            
            download_url = get_file_direct_url(file_id)
            
            if download_url:
                # Redirect to Telegram's CDN for direct download
                self.send_response(302)
                self.send_header('Location', download_url)
                self.send_header('Content-Disposition', f'attachment; filename="{file_name}"')
                self.send_header('Cache-Control', 'public, max-age=31536000')
                self.end_headers()
            else:
                # Show beautiful download page
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Download {file_name} - FileStreamBot</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
                        .container {{ background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; backdrop-filter: blur(10px); text-align: center; max-width: 600px; border: 1px solid rgba(255,255,255,0.2); }}
                        .file-icon {{ font-size: 80px; margin-bottom: 20px; color: #4ecdc4; }}
                        .filename {{ font-size: 22px; font-weight: bold; word-break: break-word; margin: 20px 0; color: #fff; }}
                        .file-info {{ background: rgba(255,255,255,0.15); padding: 20px; border-radius: 10px; margin: 20px 0; text-align: left; }}
                        .btn {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 18px 40px; text-decoration: none; border-radius: 12px; display: inline-block; font-size: 18px; font-weight: bold; margin: 10px; border: none; cursor: pointer; transition: transform 0.2s; }}
                        .btn:hover {{ transform: translateY(-2px); }}
                        .stream-btn {{ background: linear-gradient(135deg, #00c853 0%, #64dd17 100%); }}
                        .features {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 30px 0; }}
                        .feature {{ background: rgba(255,255,255,0.1); padding: 15px; border-radius: 10px; font-size: 14px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="file-icon">📥</div>
                        <div class="filename">{file_name}</div>
                        
                        <div class="file-info">
                            <div><strong>Size:</strong> {size_readable}</div>
                            <div><strong>Type:</strong> Download</div>
                            <div><strong>Status:</strong> Ready for download</div>
                        </div>
                        
                        <div style="margin: 30px 0;">
                            <a href="{download_url}" class="btn" download="{file_name}">
                                ⬇️ DOWNLOAD NOW
                            </a>
                        </div>
                        
                        <div class="features">
                            <div class="feature">🛡️ Permanent Storage</div>
                            <div class="feature">🔗 Never Expires</div>
                            <div class="feature">⚡ Fast Download</div>
                            <div class="feature">💾 2GB Support</div>
                        </div>
                        
                        <div style="margin-top: 30px; opacity: 0.8;">
                            <p>Powered by <strong>FileStreamBot</strong></p>
                            <a href="{BASE_URL}" style="color: #4ecdc4; text-decoration: none;">Upload more files</a>
                        </div>
                    </div>
                    
                    <script>
                        // Auto-start download after 1 second
                        setTimeout(function() {{
                            window.location.href = "{download_url}";
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
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; margin: 100px auto; max-width: 500px; background: #1a1a2e; color: white; padding: 50px;">
                <div style="font-size: 80px; color: #ff6b6b;">😵</div>
                <h2 style="color: #ff6b6b; margin-bottom: 20px;">Download Error</h2>
                <p style="margin-bottom: 20px;">Error: {str(e)}</p>
                <p style="margin-bottom: 30px;">Please try again or contact support.</p>
                <a href="{BASE_URL}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; display: inline-block;">Go to FileStreamBot</a>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
