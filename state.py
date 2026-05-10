"""
state.py — Global node state shared across all modules.

block_store holds ALL known blocks (main chain + forks).
blocks is the canonical chain (ordered genesis → tip, insertion order).
When a new block creates a longer chain, blocks is rebuilt from block_store.
"""

import threading
from typing import Optional

MY_PORT: int = None
MY_IP: str = "127.0.0.1"

peers: set = set()

# All known blocks including forks.
# hash -> {"content": ..., "prev_hash": ..., "height": int}
block_store: dict = {}

# Canonical chain only (ordered dict, genesis first).
# hash -> {"content": ..., "prev_hash": ..., "height": int}
blocks: dict = {}

# Transactions waiting to be confirmed (mempool).
transactions: dict = {}

lock = threading.Lock()

GENESIS_PREV = "0" * 64


def my_addr() -> str:
    return f"{MY_IP}:{MY_PORT}"


def chain_height() -> int:
    return len(blocks)


def chain_tip() -> Optional[str]:
    if not blocks:
        return None
    return list(blocks.keys())[-1]


def _compute_height(prev_hash: str) -> Optional[int]:
    if prev_hash == GENESIS_PREV:
        return 1
    parent = block_store.get(prev_hash)
    if parent:
        return parent["height"] + 1
    return None  # unknown parent


def _build_chain(tip_hash: str) -> Optional[list]:
    """Follow prev_hash links from tip back to genesis. Returns ordered list or None."""
    result = []
    h = tip_hash
    seen = set()
    while h != GENESIS_PREV:
        if h in seen or h not in block_store:
            return None
        seen.add(h)
        result.append(h)
        h = block_store[h]["prev_hash"]
    result.reverse()
    return result


def add_block(h: str, content: dict, prev_hash: str) -> bool:
    """
    Add a block to block_store. If it creates a longer chain than the current
    canonical chain, rebuild blocks to reflect the new chain.
    Caller must hold state.lock. Returns True if canonical chain was updated.
    """
    global blocks

    if h in block_store:
        return False  # Already known

    height = _compute_height(prev_hash)
    if height is None:
        return False  # Unknown parent — can't link into chain

    block_store[h] = {"content": content, "prev_hash": prev_hash, "height": height}

    if height > chain_height():
        new_chain = _build_chain(h)
        if new_chain:
            blocks = {bh: block_store[bh] for bh in new_chain}
            return True

    return False


def adopt_chain(hashes: list) -> bool:
    """
    Replace the canonical chain with the given list of hashes if:
      - all hashes are present in block_store, AND
      - the new chain is strictly longer than the current one.
    Caller must hold state.lock. Returns True if adopted.
    """
    global blocks

    if len(hashes) <= chain_height():
        return False

    new_blocks = {}
    for h in hashes:
        if h not in block_store:
            return False
        new_blocks[h] = block_store[h]

    blocks = new_blocks
    print(f"  [chain] reorg: height={len(blocks)}, tip={list(blocks.keys())[-1][:8]}...")
    return True
