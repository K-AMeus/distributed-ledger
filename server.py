"""
server.py — HTTP server and request handlers for all endpoints.

Endpoints:
    GET  /addr              → return list of known peers
    GET  /getblocks         → return list of all block hashes
    GET  /getblocks/<hash>  → return block hashes after a given hash
    GET  /getdata/<hash>    → return a single block's content
    POST /inv               → receive a new transaction
    POST /block             → receive a new block
"""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import state
import broadcast


class NodeHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        """Override default logging to keep output clean."""
        print(f"  [←] {self.client_address[0]} {args[0]}")

    def send_json(self, data, status=200):
        """Helper to send a JSON response."""
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    # ----------------------------------------------------------
    # GET handlers
    # ----------------------------------------------------------

    def do_GET(self):
        path = self.path

        # GET /addr — return known peers
        if path == "/addr":
            with state.lock:
                result = list(state.peers)
            self.send_json(result)

        # GET /getblocks — return all block hashes
        elif path == "/getblocks":
            with state.lock:
                result = list(state.blocks.keys())
            self.send_json(result)

        # GET /getblocks/<hash> — return block hashes after given hash
        elif path.startswith("/getblocks/"):
            since_hash = path[len("/getblocks/"):]
            with state.lock:
                all_hashes = list(state.blocks.keys())
            if since_hash in all_hashes:
                idx = all_hashes.index(since_hash)
                result = all_hashes[idx + 1:]
            else:
                result = all_hashes
            self.send_json(result)

        # GET /getdata/<hash> — return a single block's content
        elif path.startswith("/getdata/"):
            h = path[len("/getdata/"):]
            with state.lock:
                block = state.blocks.get(h)
            if block is not None:
                self.send_json({"hash": h, "content": block})
            else:
                self.send_json({"error": "block not found"}, 404)

        else:
            self.send_json({"error": "unknown endpoint"}, 404)

    # ----------------------------------------------------------
    # POST handlers
    # ----------------------------------------------------------

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()

        try:
            data = json.loads(body)
        except Exception:
            self.send_json({"errcode": 1, "errmsg": "invalid JSON"}, 400)
            return

        path = self.path

        # POST /inv — receive a new transaction
        if path == "/inv":
            h = data.get("hash")
            content = data.get("content")

            if not h or not content:
                self.send_json({"errcode": 2, "errmsg": "missing hash or content"}, 400)
                return
            
            content_str = json.dumps(content, sort_keys=True) if isinstance(content, dict) else str(content)
            expected = hashlib.sha256(content_str.encode()).hexdigest()
            if expected != h:
                self.send_json({"errcode": 3, "errmsg": f"hash mismatch, expected {expected}"}, 400)
                return

            with state.lock:
                if h in state.transactions:
                    self.send_json({"status": "already known"})
                    return
                state.transactions[h] = content

            print(f"  [new transaction] {h[:8]}... : {content}")
            self.send_json(1)

            # Forward to peers in background
            threading.Thread(
                target=broadcast.broadcast_transaction,
                args=(h, content),
                daemon=True
            ).start()

        # POST /block — receive a new block
        elif path == "/block":
            h = data.get("hash")
            content = data.get("content")

            if not h or not content:
                self.send_json({"errcode": 2, "errmsg": "missing hash or content"}, 400)
                return

            with state.lock:
                if h in state.blocks:
                    self.send_json({"errcode": 1, "errmsg": "already known"})
                    return

                # Check all transactions exist in mempool
                tx_list = content.get("transactions", [])
                for tx in tx_list:
                    tx_hash = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
                    if tx_hash not in state.transactions:
                        self.send_json({"errcode": 4, "errmsg": f"unknown transaction {tx_hash[:8]}"}, 400)
                        return

                # Get previous block hash (last block in chain)
                prev_hash = data.get("prev_hash") or (list(state.blocks.keys())[-1] if state.blocks else "0" * 64)

                # Recompute hash using content + prev_hash
                chain_content = {"content": content, "prev_hash": prev_hash}
                chain_str = json.dumps(chain_content, sort_keys=True)
                expected = hashlib.sha256(chain_str.encode()).hexdigest()
                if expected != h:
                    self.send_json({"errcode": 3, "errmsg": f"hash mismatch, expected {expected}"}, 400)
                    return

                state.blocks[h] = {"content": content, "prev_hash": prev_hash}

                # Clear confirmed transactions from mempool
                for tx in tx_list:
                    tx_hash = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
                    state.transactions.pop(tx_hash, None)
                    print(f"  [mempool] confirmed tx {tx_hash[:8]}...")

            print(f"  [new block] {h[:8]}... with {len(tx_list)} transactions")
            self.send_json(1)

            # Forward to peers in background
            threading.Thread(
                target=broadcast.broadcast_block,
                args=(h, content, prev_hash),
                daemon=True
            ).start()

        else:
            self.send_json({"error": "unknown endpoint"}, 404)


def run_server(port: int):
    """Start the HTTP server on the given port."""
    server = HTTPServer(("0.0.0.0", port), NodeHandler)
    print(f"\n[server] node started on port {port}")
    print(f"[server] listening on http://0.0.0.0:{port}")
    print("[server] press Ctrl+C to stop\n")
    server.serve_forever()