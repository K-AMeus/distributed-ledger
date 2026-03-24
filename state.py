"""
state.py — Global node state shared across all modules.

All mutable state lives here so every module reads/writes
the same data. The lock must be held whenever reading or
writing peers, blocks, or transactions.
"""

import threading

# ── Identity ────────────────────────────────────────────────
# Set once at startup from the command line argument.
MY_PORT: int = None
MY_IP: str = "127.0.0.1"

# ── Network ─────────────────────────────────────────────────
# Set of peer addresses this node knows about.
# Format: "ip:port"  e.g. "127.0.0.1:5002"
peers: set = set()

# ── Ledger ──────────────────────────────────────────────────
# Blocks received and stored by this node.
# Key:   sha-256 hex hash of the block content
# Value: block content string
blocks: dict = {}

# Transactions waiting to be included in a block.
# Key:   sha-256 hex hash of the transaction content
# Value: transaction content string
transactions: dict = {}

# ── Concurrency ─────────────────────────────────────────────
# Must be acquired before reading or writing peers/blocks/transactions
# to avoid race conditions between the HTTP server thread and
# background discovery/broadcast threads.
lock = threading.Lock()


def my_addr() -> str:
    """Returns this node's own address in ip:port format."""
    return f"{MY_IP}:{MY_PORT}"