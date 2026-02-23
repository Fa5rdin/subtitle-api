import os
import json
import subprocess
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 8080))

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/health":
            self.send_json(200, {"status": "ok"})
            return

        if parsed.path == "/subtitles":
            url = params.get("url", [None])[0]
            if not url:
                self.send_json(400, {"error": "Missing url parameter"})
                return

            print(f"Fetching subtitles for: {url}")
            try:
                result = subprocess.run(
                    ["yt-dlp", "--no-warnings", "--skip-download", "--dump-json", url],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    self.send_json(500, {"error": "yt-dlp failed", "details": result.stderr[:300]})
                    return

                info = json.loads(result.stdout.strip().split('\n')[0])
                subtitles = info.get("subtitles", {})
                auto_captions = info.get("automatic_captions", {})
                tracks = []

                for lang, formats in subtitles.items():
                    for fmt in formats:
                        if fmt.get("ext") == "vtt":
                            tracks.append({"lang": lang, "ext": "vtt", "url": fmt.get("url", ""), "name": lang, "type": "manual"})
                            break

                for lang, formats in auto_captions.items():
                    for fmt in formats:
                        if fmt.get("ext") == "vtt":
                            tracks.append({"lang": lang, "ext": "vtt", "url": fmt.get("url", ""), "name": lang, "type": "auto"})
                            break

                self.send_json(200, {"title": info.get("title", ""), "tracks": tracks})

            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        if parsed.path == "/proxy":
            sub_url = params.get("url", [None])[0]
            fmt = params.get("format", ["vtt"])[0]
            if not sub_url:
                self.send_json(400, {"error": "Missing url"})
                return
            try:
                req = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read().decode("utf-8")

                if fmt == "txt":
                    # Strip VTT formatting to plain text
                    lines = content.split('\n')
                    text_lines = []
                    skip = True
                    for line in lines:
                        line = line.strip()
                        if line == "WEBVTT":
                            skip = False
                            continue
                        if '-->' in line or line == '' or line.startswith('NOTE') or line.isdigit():
                            continue
                        if not skip:
                            text_lines.append(line)
                    content = '\n'.join(text_lines)

                body = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Disposition", f'attachment; filename="subtitles.{fmt}"')
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        self.send_json(404, {"error": "Not found"})

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")

if __name__ == "__main__":
    print(f"Server starting on port {PORT}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
