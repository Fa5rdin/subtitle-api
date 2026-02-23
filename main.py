import os
import json
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 8080))

class SubtitleHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/subtitles":
            url = params.get("url", [None])[0]
            if not url:
                self.respond(400, {"error": "Missing url parameter"})
                return

            try:
                result2 = subprocess.run(
                    ["yt-dlp", "-j", "--skip-download", url],
                    capture_output=True, text=True, timeout=30
                )

                if result2.returncode != 0:
                    self.respond(500, {"error": "Failed to fetch video info", "details": result2.stderr})
                    return

                info = json.loads(result2.stdout)
                subtitles = info.get("subtitles", {})
                auto_captions = info.get("automatic_captions", {})

                tracks = []
                for lang, formats in subtitles.items():
                    for fmt in formats:
                        tracks.append({
                            "lang": lang,
                            "ext": fmt.get("ext", "vtt"),
                            "url": fmt.get("url", ""),
                            "name": fmt.get("name", lang),
                            "type": "manual"
                        })

                for lang, formats in auto_captions.items():
                    for fmt in formats:
                        if fmt.get("ext") in ["vtt", "srv1", "srv2", "srv3", "json3"]:
                            tracks.append({
                                "lang": lang,
                                "ext": fmt.get("ext", "vtt"),
                                "url": fmt.get("url", ""),
                                "name": fmt.get("name", lang),
                                "type": "auto"
                            })
                            break

                self.respond(200, {
                    "title": info.get("title", ""),
                    "tracks": tracks
                })

            except subprocess.TimeoutExpired:
                self.respond(500, {"error": "Request timed out"})
            except Exception as e:
                self.respond(500, {"error": str(e)})
        else:
            self.respond(404, {"error": "Not found"})

    def respond(self, code, data):
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
    print(f"Server running on port {PORT}")
    server = HTTPServer(("0.0.0.0", PORT), SubtitleHandler)
    server.serve_forever()
