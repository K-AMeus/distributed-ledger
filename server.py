#!/usr/bin/env python3

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse
import sys
import json



known_addresses = [
    {"host": "127.0.0.1", "port": 8000},
    {"host": "127.0.0.1", "port": 8001},
    {"host": "127.0.0.1", "port": 8003},
]

def get_known_addresses():
    return known_addresses;


class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self): 

        parsed = urlparse.urlparse(self.path)      

        is_ok = True

        if parsed.path == "/addr":
            result = get_known_addresses()
            result = ",".join([f"{addr['host']}:{addr['port']}" for addr in result])
        else:
            is_ok = False
            self.send_response(404)
            self.end_headers()
            return

        if is_ok:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(result.encode("utf-8"))



    def do_POST(self):
        content_length_str = self.headers.get("Content-Length")
        if content_length_str is None:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Content-Length header is missing")
            return

        content_length = int(content_length_str)
        rawdata = self.rfile.read(content_length)
        body = rawdata.decode("utf-8")

        if self.path == "/addr":
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid JSON")
                return

            host = data.get("host")
            port = data.get("port")

            if not host or not port:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Missing "host" or "port"')
                return

            peer = {"host": host, "port": int(port)}

            if peer not in known_addresses:
                known_addresses.append(peer)

            out = json.dumps({
                "ok": True,
                "known_addresses": known_addresses
            })

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(out.encode("utf-8"))
            return



if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("\nUsage: ./server.py <port>\n")
        sys.exit(1)

    port = int(sys.argv[1])

    if port < 2000 or port > 65535:
        print("Port number must be between 1024 and 65535")
        sys.exit(1)


    server = HTTPServer(("", port), MyHandler)
    print(f"Server started on {port}")
    server.serve_forever()