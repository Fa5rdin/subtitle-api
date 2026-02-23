import os
import json
import subprocess
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

        if parsed.path != "/subtitles":
            self.send_json(404, {"error": "Not found"})
            return

        url = params.get("url", [None])[0]
        if not url:
            self.send_json(400, {"error": "Missing url parameter"})
            return

        print(f"Fetching subtitles for: {url}")

        try:
            cmd = [
                "yt-dlp",
                "--no-warnings",
                "--skip-download",
                "--write-auto-sub",
                "--write-sub",
                "--dump-json",
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            print(f"Return code: {result.returncode}")
            print(f"Stderr: {result.stderr[:500]}")
            
            if result.returncode != 0:
                self.send_json(500, {
                    "error": "yt-dlp failed",
                    "details": result.stderr[:300]
                })
                return

            if not result.stdout.strip():
                self.send_json(500, {"error": "No output from yt-dlp"})
                return

            info = json.loads(result.stdout.strip().split('\n')[0])
            
            subtitles = info.get("subtitles", {})
            auto_captions = info.get("automatic_captions", {})
            
            tracks = []
            
            # Manual subtitles
            for lang, formats in subtitles.items():
                for fmt in formats:
                    if fmt.get("ext") in ["vtt", "srt"]:
                        tracks.append({
                            "lang": lang,
                            "ext": fmt.get("ext"),
                            "url": fmt.get("url", ""),
                            "name": info.get("subtitles_name", {}).get(lang, lang),
                            "type": "manual"
                        })
                        break

            # Auto-generated captions  
            for lang, formats in auto_captions.items():
                for fmt in formats:
                    if fmt.get("ext") == "vtt":
                        tracks.append({
                            "lang": lang,
                            "ext": "vtt",
                            "url": fmt.get("url", ""),
                            "name": lang,
                            "type": "auto"
                        })
                        break

            print(f"Found {len(tracks)} tracks")
            
            self.send_json(200, {
                "title": info.get("title", ""),
                "tracks": tracks
            })

        except subprocess.TimeoutExpired:
            self.send_json(500, {"error": "Timeout - video took too long"})
        except json.JSONDecodeError as e:
            self.send_json(500, {"error": f"JSON parse error: {str(e)}"})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

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
