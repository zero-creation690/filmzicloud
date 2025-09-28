import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote
import json

TOKEN = os.environ.get('TELEGRAM_TOKEN')

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
            
            # For demo purposes, we'll create a file_id based on the short_id
            # In production, you'd lookup the actual file_id from your storage
            demo_file_id = f"AgAC{short_id}"  # This is just a demo format
            
            # Get actual download URL from Telegram
            download_url = get_file_download_url(demo_file_id)
            
            if download_url:
                # Redirect to Telegram's CDN
                self.send_response(302)
                self.send_header('Location', download_url)
                self.send_header('Content-Disposition', f'attachment; filename="{original_filename}"')
                self.end_headers()
            else:
                # Fallback: Show download page with instructions
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Download {original_filename}</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                        .container {{ background: #f5f5f5; padding: 20px; border-radius: 10px; }}
                        .btn {{ background: #0088cc; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h2>📁 Download File</h2>
                        <p><strong>Filename:</strong> {original_filename}</p>
                        <p><strong>File ID:</strong> {short_id}</p>
                        <p>This is a permanent download link stored in Telegram's cloud.</p>
                        
                        <div style="margin-top: 20px;">
                            <p>To implement full functionality:</p>
                            <ol>
                                <li>Store file mappings in a database</li>
                                <li>Implement channel message parsing</li>
                                <li>Add proper file_id lookup</li>
                            </ol>
                        </div>
                        
                        <p style="margin-top: 20px;">
                            <a href="/" class="btn">Upload Another File</a>
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
            <body>
                <h2>Download Error</h2>
                <p>Error: {str(e)}</p>
                <p>Please check the download link and try again.</p>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
