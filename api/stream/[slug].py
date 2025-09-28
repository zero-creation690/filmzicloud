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
                    <title>Stream Not Found - Filmzi Cloud</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
                        .container {{ background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; backdrop-filter: blur(10px); text-align: center; max-width: 500px; border: 1px solid rgba(255,255,255,0.2); }}
                        .error-icon {{ font-size: 80px; margin-bottom: 20px; color: #ff6b6b; }}
                        .btn {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 10px; display: inline-block; margin: 10px; font-weight: bold; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-icon">❌</div>
                        <h1>Stream Not Available</h1>
                        <p style="margin-bottom: 20px; opacity: 0.8;">The streaming link is invalid or the file has been removed.</p>
                        <a href="{BASE_URL}/api/download/{filename_encoded}-{short_id}" class="btn">⬇️ Try Download Instead</a>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_content.encode())
                return
            
            file_id = file_data.get('file_id')
            file_name = file_data.get('file_name', original_filename)
            
            stream_url = get_file_direct_url(file_id)
            
            # Check if file is video/audio
            mime_type = file_data.get('mime_type', '')
            is_video = mime_type.startswith('video')
            is_audio = mime_type.startswith('audio')
            
            if not is_video and not is_audio:
                # Redirect to download
                self.send_response(302)
                self.send_header('Location', f"{BASE_URL}/api/download/{filename_encoded}-{short_id}")
                self.end_headers()
                return
            
            if stream_url:
                # Show streaming page with Plyr player
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                player_type = 'video' if is_video else 'audio'
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Stream {file_name} - Filmzi Cloud</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css" />
                    <style>
                        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; }}
                        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
                        .header {{ text-align: center; margin-bottom: 30px; }}
                        .player-container {{ background: rgba(0,0,0,0.3); padding: 20px; border-radius: 15px; margin-bottom: 20px; }}
                        .file-info {{ background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; margin: 20px 0; }}
                        .btn {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 10px; display: inline-block; margin: 10px; font-weight: bold; }}
                        .download-btn {{ background: linear-gradient(135deg, #00c853 0%, #64dd17 100%); }}
                        .controls {{ text-align: center; margin: 20px 0; }}
                        .plyr {{ border-radius: 10px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>🎬 Filmzi Cloud Player</h1>
                            <p style="opacity: 0.8; margin-top: 10px;">Professional streaming experience</p>
                        </div>
                        
                        <div class="player-container">
                            <{player_type} id="player" controls crossorigin playsinline>
                                <source src="{stream_url}" type="{player_type}/mp4">
                                Your browser doesn't support HTML5 {player_type}.
                            </{player_type}>
                        </div>
                        
                        <div class="file-info">
                            <h3>📁 {file_name}</h3>
                            <p><strong>Streaming:</strong> Direct from Telegram Cloud</p>
                        </div>
                        
                        <div class="controls">
                            <a href="{stream_url}" class="btn download-btn" download="{file_name}">⬇️ Download File</a>
                            <a href="{BASE_URL}" class="btn">🏠 Home</a>
                        </div>
                    </div>
                    
                    <script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>
                    <script>
                        const player = new Plyr('#player', {{
                            ratio: '16:9',
                            autoplay: true,
                            muted: false,
                            controls: ['play', 'progress', 'current-time', 'mute', 'volume', 'settings', 'fullscreen'],
                            settings: ['quality', 'speed'],
                            quality: {{ default: 0, options: [{{name: 'Auto', value: 0}}] }},
                            speed: {{ selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2] }}
                        }});
                        
                        player.on('error', event => {{
                            console.error('Player error:', event);
                            alert('Streaming error. Please try downloading the file instead.');
                        }});
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
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; margin: 100px auto; max-width: 500px; background: #1a1a2e; color: white; padding: 50px;">
                <div style="font-size: 80px; color: #ff6b6b;">😵</div>
                <h2 style="color: #ff6b6b;">Streaming Error</h2>
                <p>Error: {str(e)}</p>
                <a href="{BASE_URL}/api/download/{filename_encoded}-{short_id}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; display: inline-block;">Try Download Instead</a>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
