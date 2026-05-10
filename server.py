"""
server.py — HTTP server and request handlers.

Endpoints:
    GET  /addr              → list of known peers
    GET  /getblocks         → canonical chain hashes (genesis → tip)
    GET  /getblocks/<hash>  → canonical chain hashes after a given hash
    GET  /getdata/<hash>    → single block content (searched in block_store)
    GET  /chainlen          → integer length of canonical chain
    GET  /status            → debug info (chain height, block_store size, peers)
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
        pass  # suppress default HTTP server logging

    def send_json(self, data, status=200):
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

        if path == "/addr":
            with state.lock:
                result = list(state.peers)
            self.send_json(result)

        elif path == "/getblocks":
            with state.lock:
                result = list(state.blocks.keys())
            self.send_json(result)

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

        elif path.startswith("/getdata/"):
            h = path[len("/getdata/"):]
            with state.lock:
                # Search block_store so we can serve fork blocks too
                block = state.block_store.get(h)
            if block is not None:
                self.send_json({"hash": h, "content": block})
            else:
                self.send_json({"error": "block not found"}, 404)

        elif path == "/chainlen":
            with state.lock:
                result = state.chain_height()
            self.send_json(result)

        elif path == "/status":
            with state.lock:
                result = {
                    "port": state.MY_PORT,
                    "chain_height": state.chain_height(),
                    "block_store_size": len(state.block_store),
                    "mempool_size": len(state.transactions),
                    "peers": list(state.peers),
                    "chain_tip": state.chain_tip(),
                    "chain": list(state.blocks.keys()),
                }
            self.send_json(result)

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

            print(f"  [new tx] {h[:8]}... : {content}")
            self.send_json(1)

            threading.Thread(
                target=broadcast.broadcast_transaction,
                args=(h, content),
                daemon=True,
            ).start()

        # POST /block — receive a new block
        elif path == "/block":
            h = data.get("hash")
            content = data.get("content")
            prev_hash = data.get("prev_hash", state.GENESIS_PREV)

            if not h or not content:
                self.send_json({"errcode": 2, "errmsg": "missing hash or content"}, 400)
                return

            # Verify hash integrity
            chain_content = {"content": content, "prev_hash": prev_hash}
            expected = hashlib.sha256(json.dumps(chain_content, sort_keys=True).encode()).hexdigest()
            if expected != h:
                self.send_json({"errcode": 3, "errmsg": f"hash mismatch, expected {expected}"}, 400)
                return

            with state.lock:
                if h in state.block_store:
                    self.send_json({"status": "already known"})
                    return

                # Check that every transaction in this block was pre-announced
                tx_list = content.get("transactions", [])
                for tx in tx_list:
                    tx_hash = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
                    if tx_hash not in state.transactions:
                        self.send_json({"errcode": 4, "errmsg": f"unknown transaction {tx_hash[:8]}"}, 400)
                        return

                chain_updated = state.add_block(h, content, prev_hash)

                if chain_updated:
                    # Remove confirmed transactions from mempool
                    for tx in tx_list:
                        tx_hash = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
                        state.transactions.pop(tx_hash, None)
                    print(f"  [new block] {h[:8]}... height={state.block_store[h]['height']} txs={len(tx_list)}")
                else:
                    # Block was stored but didn't extend the canonical chain (fork)
                    print(f"  [fork block] {h[:8]}... stored but not on main chain")

            self.send_json(1)

            # Broadcast regardless — let peers decide what to do with it
            threading.Thread(
                target=broadcast.broadcast_block,
                args=(h, content, prev_hash),
                daemon=True,
            ).start()

        # POST /addpeer — manually add a peer to this node's known set
        elif path == "/addpeer":
            addr = data.get("addr")
            if not addr:
                self.send_json({"errcode": 2, "errmsg": "missing addr"}, 400)
                return
            with state.lock:
                if addr != state.my_addr():
                    state.peers.add(addr)
            print(f"  [peer added] {addr}")
            self.send_json({"status": "ok", "peers": list(state.peers)})

        else:
            self.send_json({"error": "unknown endpoint"}, 404)


def run_server(port: int):
    server = HTTPServer(("0.0.0.0", port), NodeHandler)
    print(f"\n[server] node started on port {port}")
    print(f"[server] listening on http://0.0.0.0:{port}")
    print("[server] press Ctrl+C to stop\n")
    server.serve_forever()
