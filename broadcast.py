"""
broadcast.py — Broadcast new blocks and transactions to all known peers.
"""

import state
from client import http_post


def broadcast_transaction(h: str, content: str):
    """Send a new transaction to all known peers."""
    with state.lock:
        current_peers = list(state.peers)

    for peer in current_peers:
        print(f"  [→] sending transaction {h[:8]}... → {peer}")
        http_post(f"http://{peer}/inv", {"hash": h, "content": content})


def broadcast_block(h: str, content: str):
    """Send a new block to all known peers."""
    with state.lock:
        current_peers = list(state.peers)

    for peer in current_peers:
        print(f"  [→] sending block {h[:8]}... → {peer}")
        http_post(f"http://{peer}/block", {"hash": h, "content": content})