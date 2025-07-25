#!/usr/bin/env python3
import http.server
import socketserver
import os
import json
import sys
import traceback
from datetime import datetime

PORT = int(os.environ.get('PORT', 3030))
DIRECTORY = 'public'

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        print(f"{datetime.now().isoformat()} - {format % args}", flush=True)

    def do_GET(self):
        print(f"Request: {self.path}", flush=True)

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
            print("Health check served", flush=True)
            return

        if self.path == '/':
            self.path = '/index.html'

        super().do_GET()

def main():
    print("=== Frontend Server Starting ===", flush=True)

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"Script directory: {script_dir}", flush=True)
        os.chdir(script_dir)

        print(f"Working directory: {os.getcwd()}", flush=True)
        print(f"Directory contents:", flush=True)
        for item in os.listdir('.'):
            print(f"  {item}", flush=True)

        if not os.path.exists(DIRECTORY):
            print(f"ERROR: Directory '{DIRECTORY}' not found!", flush=True)
            sys.exit(1)

        print(f"Contents of {DIRECTORY}:", flush=True)
        for item in os.listdir(DIRECTORY):
            print(f"  {item}", flush=True)

        print(f"Starting server on 0.0.0.0:{PORT}", flush=True)

        with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
            print(f"Server running on http://0.0.0.0:{PORT}", flush=True)
            httpd.serve_forever()

    except Exception as e:
        print(f"Error: {e}", flush=True)
        print(f"Traceback:", flush=True)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()