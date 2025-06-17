#!/usr/bin/env python3
import http.server
import socketserver
import os
import json
from datetime import datetime

PORT = int(os.environ.get('PORT', 3000))
DIRECTORY = 'public'

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        print(f"{datetime.now().isoformat()} - {format % args}")

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            response = {
                'status': 'ok',
                'service': 'network-scanner-frontend',
                'timestamp': datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
            return
        super().do_GET()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print(f"Starting frontend server on port {PORT}")
    print(f"Serving static files from: {os.path.abspath(DIRECTORY)}")

    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"Frontend server running on http://0.0.0.0:{PORT}")
        print(f"Access the app at: http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()