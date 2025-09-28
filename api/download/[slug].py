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

def get_file_download_url(file_id):
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
                self.send_response(404)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>File Not Found</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 100px auto; padding: 20px; text-align: center; }}
                        .error {{ color: #ff4444; font-size: 24px; }}
                    </style>
                </head>
                <body>
                    <div class="error">❌ File Not Found</div>
                    <p>The download link is invalid or the file has been removed.</p>
                    <p>File ID: {short_id}</p>
                    <p><a href="/">Upload a new file</a></p>
                </body>
                </html>
                """
                self.wfile.write(html_content.encode())
                return
            
            # Get the actual download URL from Telegram
            file_id = file_data.get('file_id')
            download_url = get_file_download_url(file_id)
            
            if download_url:
                # Redirect to Telegram's CDN for direct download
                self.send_response(302)
                self.send_header('Location', download_url)
                self.send_header('Content-Disposition', f'attachment; filename="{original_filename}"')
                self.send_header('Cache-Control', 'public, max-age=31536000')  # 1 year cache
                self.end_headers()
            else:
                # Fallback: Serve download page with info
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                file_size = file_data.get('file_size', 0)
                size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 'Unknown'
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Download {original_filename}</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                        .container {{ background: #f0f8ff; padding: 30px; border-radius: 15px; text-align: center; }}
                        .filename {{ font-size: 20px; font-weight: bold; color: #333; }}
                        .info {{ margin: 15px 0; color: #666; }}
                        .btn {{ background: #0088cc; color: white; padding: 15px 30px; text-decoration: none; 
                                border-radius: 8px; display: inline-block; font-size: 18px; margin: 10px; }}
                        .btn:hover {{ background: #006699; }}
                        .features {{ background: white; padding: 15px; border-radius: 8px; margin: 20px 0; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>📁 Download Ready</h1>
                        <div class="filename">{original_filename}</div>
                        <div class="info">Size: {size_mb} MB</div>
                        <div class="info">File ID: {short_id}</div>
                        
                        <div class="features">
                            <h3>🛡️ Filmzi Cloud Features</h3>
                            <p>✅ Permanent Storage</p>
                            <p>✅ Never-expiring Links</p>
                            <p>✅ Fast Download</p>
                        </div>
                        
                        {f'<a href="{download_url if download_url else "#"}" class="btn" download="{original_filename}">⬇️ Download Now</a>' if download_url else '<p class="btn" style="background: #ff4444;">Download temporarily unavailable</p>'}
                        
                        <p style="margin-top: 20px;">
                            <a href="/" style="color: #0088cc;">Upload another file</a>
                        </p>
                    </div>
                </body>
                </html>
                """
                
                self.wfile.write(html_content.encode())
                
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            error_html = f"""
            <html>
            <body style="font-family: Arial; text-align: center; margin: 100px auto; max-width: 500px;">
                <h2 style="color: #ff4444;">Download Error</h2>
                <p>Error: {str(e)}</p>
                <p>Please try again or contact support.</p>
                <p><a href="/">Go back</a></p>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())

    def do_HEAD(self):
        """Handle HEAD requests for link checking"""
        try:
            path = self.path.strip('/')
            if path.startswith('api/download/'):
                slug = path.split('api/download/')[-1]
                if slug and '-' in slug:
                    parts = slug.rsplit('-', 1)
                    if len(parts) == 2:
                        short_id = parts[1]
                        file_data = get_from_redis(short_id)
                        if file_data:
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/octet-stream')
                            self.end_headers()
                            return
            
            self.send_response(404)
            self.end_headers()
        except:
            self.send_response(500)
            self.end_headers()
