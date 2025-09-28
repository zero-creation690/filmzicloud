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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            path = self.path.strip('/')
            if not path.startswith('api/stream/'):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'Not found')
                return
            
            slug = path.split('api/stream/')[-1]
            
            if not slug or '-' not in slug:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid stream link')
                return
            
            parts = slug.rsplit('-', 1)
            if len(parts) != 2:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid stream link format')
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
                    <title>File Not Found - Filmzi Cloud</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #ff6b6b 0%, #feca57 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; color: white; }}
                        .container {{ background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; backdrop-filter: blur(10px); text-align: center; max-width: 500px; }}
                        .error-icon {{ font-size: 80px; margin-bottom: 20px; }}
                        .btn {{ background: white; color: #ff6b6b; padding: 15px 30px; text-decoration: none; border-radius: 10px; display: inline-block; margin: 10px; font-weight: bold; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-icon">❌</div>
                        <h1>Stream Not Available</h1>
                        <p>The streaming link is invalid or the file has been removed.</p>
                        <p><strong>File ID:</strong> {short_id}</p>
                        <a href="{BASE_URL}/api/download/{filename_encoded}-{short_id}" class="btn">⬇️ Try Download Instead</a>
                        <a href="https://t.me/filmzicloud_bot" class="btn">🤖 Open Bot</a>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_content.encode())
                return
            
            file_id = file_data.get('file_id')
            file_name = file_data.get('file_name', original_filename)
            file_size = file_data.get('file_size', 0)
            size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
            
            stream_url = get_file_direct_url(file_id)
            
            # Check if file is streamable (video/audio)
            file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
            streamable_extensions = ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'webm', 'mp3', 'wav', 'aac', 'ogg']
            
            if file_ext not in streamable_extensions:
                # Not streamable, redirect to download
                self.send_response(302)
                self.send_header('Location', f"{BASE_URL}/api/download/{filename_encoded}-{short_id}")
                self.end_headers()
                return
            
            if stream_url:
                # Show streaming page with video player
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Stream {file_name} - Filmzi Cloud</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; }}
                        .container {{ max-width: 1000px; margin: 0 auto; }}
                        .player-container {{ background: rgba(0,0,0,0.3); padding: 20px; border-radius: 15px; margin-bottom: 20px; }}
                        video {{ width: 100%; border-radius: 10px; }}
                        .file-info {{ background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; margin: 20px 0; }}
                        .btn {{ background: white; color: #1e3c72; padding: 15px 30px; text-decoration: none; border-radius: 10px; display: inline-block; margin: 10px; font-weight: bold; }}
                        .controls {{ text-align: center; margin: 20px 0; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1 style="text-align: center; margin-bottom: 30px;">🎬 Filmzi Cloud Stream</h1>
                        
                        <div class="player-container">
                            <video controls autoplay playsinline>
                                <source src="{stream_url}" type="video/mp4">
                                <source src="{stream_url}" type="video/webm">
                                <source src="{stream_url}" type="video/ogg">
                                Your browser does not support the video tag.
                            </video>
                        </div>
                        
                        <div class="file-info">
                            <h3>📁 {file_name}</h3>
                            <p><strong>Size:</strong> {size_mb} MB</p>
                            <p><strong>Quality:</strong> Auto (Original)</p>
                            <p><strong>Streaming:</strong> Direct from Telegram Cloud</p>
                        </div>
                        
                        <div class="controls">
                            <a href="{stream_url}" class="btn" download="{file_name}">⬇️ Download File</a>
                            <a href="{BASE_URL}" class="btn">🏠 Home</a>
                            <a href="https://t.me/filmzicloud_bot" class="btn">🤖 Upload More</a>
                        </div>
                        
                        <div style="text-align: center; margin-top: 40px; opacity: 0.8;">
                            <p>Powered by <strong>Filmzi Cloud</strong> - Permanent streaming solutions</p>
                        </div>
                    </div>
                    
                    <script>
                        // Auto fullscreen for mobile
                        if (window.innerWidth < 768) {{
                            const video = document.querySelector('video');
                            video.addEventListener('click', function() {{
                                if (video.requestFullscreen) {{
                                    video.requestFullscreen();
                                }} else if (video.webkitRequestFullscreen) {{
                                    video.webkitRequestFullscreen();
                                }}
                            }});
                        }}
                    </script>
                </body>
                </html>
                """
                
                self.wfile.write(html_content.encode())
            else:
                # Fallback to download
                self.send_response(302)
                self.send_header('Location', f"{BASE_URL}/api/download/{filename_encoded}-{short_id}")
                self.end_headers()
                
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            error_html = f"""
            <html>
            <body style="font-family: Arial; text-align: center; margin: 100px auto; max-width: 500px; background: #f8f9fa; padding: 50px;">
                <div style="font-size: 80px;">😵</div>
                <h2 style="color: #ff4444;">Streaming Error</h2>
                <p>Error: {str(e)}</p>
                <p>Please try the download link instead.</p>
                <a href="{BASE_URL}/api/download/{filename_encoded}-{short_id}" style="background: #0088cc; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; display: inline-block; margin-top: 20px;">Try Download Instead</a>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
