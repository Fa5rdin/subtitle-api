import os
import json
import subprocess
import tempfile
import glob
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
                # Only manual subtitles + original language auto-caption
                original_lang = info.get("language", "en") or "en"
                
                for lang, formats in subtitles.items():
                    for fmt in formats:
                        if fmt.get("ext") == "vtt":
                            tracks.append({"lang": lang, "ext": "vtt", "url": fmt.get("url", ""), "name": fmt.get("name", lang), "type": "manual"})
                            break
                
                # Add auto-caption only for the video's original language
                if original_lang in auto_captions:
                    for fmt in auto_captions[original_lang]:
                        if fmt.get("ext") == "vtt":
                            tracks.append({"lang": original_lang, "ext": "vtt", "url": fmt.get("url", ""), "name": fmt.get("name", original_lang) + " (Auto)", "type": "auto"})
                            break
                self.send_json(200, {"title": info.get("title", ""), "tracks": tracks})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        if parsed.path == "/download":
            video_url = params.get("url", [None])[0]
            lang = params.get("lang", ["en"])[0]
            fmt = params.get("format", ["vtt"])[0]
            if not video_url:
                self.send_json(400, {"error": "Missing url"})
                return
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = subprocess.run([
                        "yt-dlp",
                        "--no-warnings",
                        "--skip-download",
                        "--write-auto-sub",
                        "--write-sub",
                        "--sub-lang", lang,
                        "--sub-format", "vtt",
                        "--convert-subs", "vtt",
                        "-o", f"{tmpdir}/sub",
                        video_url
                    ], capture_output=True, text=True, timeout=60)

                    files = glob.glob(f"{tmpdir}/*.vtt")
                    if not files:
                        self.send_json(404, {"error": "No subtitle file found", "stderr": result.stderr[:200]})
                        return

                    content = open(files[0], encoding="utf-8").read()

                    if fmt == "txt":
                        import re
                        blocks = content.strip().split('\n\n')
                        result = []
                        seen_texts = set()
                        for block in blocks:
                            blines = block.strip().split('\n')
                            timestamp_line = None
                            text_lines = []
                            for line in blines:
                                if '-->' in line:
                                    timestamp_line = line.split('-->')[0].strip()
                                elif not line.startswith('WEBVTT') and not line.startswith('Kind:') and not line.startswith('Language:'):
                                    clean = re.sub(r'<[^>]+>', '', line).strip()
                                    if clean and clean != ' ':
                                        text_lines.append(clean)
                            if not text_lines or not timestamp_line:
                                continue
                            text = text_lines[-1]
                            if text in seen_texts:
                                continue
                            seen_texts.add(text)
                            try:
                                parts = timestamp_line.split(':')
                                h, m, s = int(parts[0]), int(parts[1]), int(float(parts[2]))
                                total_mins = h * 60 + m
                                ts = f"[{total_mins:02d}:{s:02d}]"
                            except:
                                ts = f"[{timestamp_line}]"
                            result.append(f"{ts} {text}")
                        content = '\n'.join(result)

                    body = content.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Disposition", f'attachment; filename="subtitles_{lang}.{fmt}"')
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
