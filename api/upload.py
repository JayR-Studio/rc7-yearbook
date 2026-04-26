from http.server import BaseHTTPRequestHandler
import json
import os
from vercel.blob import BlobClient


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            filename = self.headers.get("x-vercel-filename", "profile-image.jpg")
            content_length = int(self.headers.get("content-length", 0))
            file_bytes = self.rfile.read(content_length)

            client = BlobClient(token=os.environ.get("BLOB_READ_WRITE_TOKEN"))

            blob = client.put(
                filename,
                file_bytes,
                access="public",
                add_random_suffix=True
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            self.wfile.write(json.dumps({
                "url": blob.url
            }).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            self.wfile.write(json.dumps({
                "error": str(e)
            }).encode())