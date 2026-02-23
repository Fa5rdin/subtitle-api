import json
import subprocess
import tempfile
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence logs

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        video_id = params.get('videoId', [None])[0]
        if not video_id:
            self.wfile.write(json.dumps({'error': 'Missing videoId'}).encode())
            return

        url = f'https://www.youtube.com/watch?v={video_id}'

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Use yt-dlp to list all subtitle info
                result = subprocess.run([
                    'yt-dlp',
                    '--list-subs',
                    '--no-download',
                    '--skip-download',
                    url
                ], capture_output=True, text=True, timeout=30)

                output = result.stdout + result.stderr

                # Also get JSON info for title and subtitle URLs
                info_result = subprocess.run([
                    'yt-dlp',
                    '--dump-json',
                    '--skip-download',
                    url
                ], capture_output=True, text=True, timeout=30)

                if info_result.returncode != 0:
                    self.wfile.write(json.dumps({'error': 'Could not fetch video info', 'tracks': []}).encode())
                    return

                info = json.loads(info_result.stdout)
                title = info.get('title', '')

                tracks = []

                # Get manual subtitles
                subtitles = info.get('subtitles', {})
                for lang_code, formats in subtitles.items():
                    lang_name = lang_code
                    # Try to get a readable name
                    for fmt in formats:
                        if fmt.get('name'):
                            lang_name = fmt['name']
                            break
                    # Get the srv3/xml url
                    url_to_use = None
                    for fmt in formats:
                        if fmt.get('ext') in ['srv3', 'srv2', 'srv1', 'ttml', 'vtt']:
                            url_to_use = fmt.get('url')
                            break
                    if not url_to_use and formats:
                        url_to_use = formats[0].get('url')

                    if url_to_use:
                        tracks.append({
                            'lang': lang_name,
                            'langCode': lang_code,
                            'baseUrl': url_to_use,
                            'isAuto': False
                        })

                # Get auto-generated subtitles
                auto_subs = info.get('automatic_captions', {})
                for lang_code, formats in auto_subs.items():
                    # Only include if not already in manual subs
                    if lang_code not in subtitles:
                        url_to_use = None
                        for fmt in formats:
                            if fmt.get('ext') in ['srv3', 'srv2', 'srv1', 'ttml', 'vtt']:
                                url_to_use = fmt.get('url')
                                break
                        if not url_to_use and formats:
                            url_to_use = formats[0].get('url')

                        if url_to_use:
                            tracks.append({
                                'lang': lang_code,
                                'langCode': lang_code,
                                'baseUrl': url_to_use,
                                'isAuto': True
                            })

                self.wfile.write(json.dumps({
                    'tracks': tracks,
                    'title': title
                }).encode())

        except Exception as e:
            self.wfile.write(json.dumps({'error': str(e), 'tracks': []}).encode())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'Server running on port {port}')
    server.serve_forever()
