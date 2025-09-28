import os
import requests
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import unquote

TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')

def get_file_download_url(file_id):
    """Get direct download URL from Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/getFile"
    data = {'file_id': file_id}
    response = requests.post(url, data=data)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('ok'):
            file_path = result['result']['file_path']
            return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    return None

def search_file_mapping(short_id):
    """Search for file mapping in channel"""
    # This would need to search through channel messages
    # For now, we'll return a placeholder - you'd need to implement proper storage
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Extract slug from path
            slug = self.path.split('/')[-1]
            
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
            
            # In a real implementation, you'd search for the file mapping
            # For now, we'll create a direct download flow
            
            self.send_response(200)
            self.end_headers()
            
            response = {
                "status": "Download endpoint",
                "file_info": {
                    "original_filename": original_filename,
                    "short_id": short_id,
                    "message": "File download would be processed here"
                },
                "note": "Implement proper file mapping storage for production"
            }
            
            self.wfile.write(json.dumps(response, indent=2).encode())
            
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'Error: {str(e)}'.encode())

def do_OPTIONS(self):
    self.send_response(200)
    self.end_headers()
