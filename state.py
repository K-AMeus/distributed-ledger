"""
state.py — Global node state shared across all modules.

block_store holds ALL known blocks (main chain + forks).
blocks is the canonical chain (ordered genesis → tip, insertion order).
When a new block creates a longer chain, blocks is rebuilt from block_store.

On a chain reorg, transactions from orphaned blocks are returned to the
mempool so they can be included in future blocks.
"""

import hashlib
import json
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


def _tx_hash(tx: dict) -> str:
    return hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()


def _block_txs(block_hash_: str) -> list:
    block = block_store.get(block_hash_)
    if not block:
        return []
    return block.get("content", {}).get("transactions", []) or []


def _reconcile_mempool(old_chain: list, new_chain: list) -> None:
    """
    Bitcoin-style reorg handling for the mempool.

    Whenever the canonical chain changes from old_chain to new_chain:
      - Transactions in blocks that were on the old chain but not the new
        chain ("orphaned" blocks) are restored to the mempool, so they can
        be mined into future blocks.
      - Transactions in blocks that are newly part of the canonical chain
        are removed from the mempool (in case they were sitting there).

    A tx restored from an orphaned block is skipped if the same tx already
    appears in the new canonical chain, otherwise it would be confirmed
    once and also be a "pending" duplicate. Caller must hold state.lock.
    """
    old_set = set(old_chain)
    new_set = set(new_chain)
    orphaned = [h for h in old_chain if h not in new_set]
    connected = [h for h in new_chain if h not in old_set]

    if not orphaned and not connected:
        return

    # All tx hashes that are confirmed in the new canonical chain.
    new_chain_tx_hashes = set()
    for bh in new_chain:
        for tx in _block_txs(bh):
            new_chain_tx_hashes.add(_tx_hash(tx))

    restored = 0
    for bh in orphaned:
        for tx in _block_txs(bh):
            txh = _tx_hash(tx)
            if txh in new_chain_tx_hashes:
                continue  # already confirmed in the winning chain
            if txh in transactions:
                continue  # already pending
            transactions[txh] = tx
            restored += 1

    removed = 0
    for bh in connected:
        for tx in _block_txs(bh):
            if transactions.pop(_tx_hash(tx), None) is not None:
                removed += 1

    if orphaned or restored or removed:
        print(
            f"  [reorg] orphaned_blocks={len(orphaned)} "
            f"restored_txs={restored} removed_txs={removed}"
        )


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
            old_chain = list(blocks.keys())
            blocks = {bh: block_store[bh] for bh in new_chain}
            _reconcile_mempool(old_chain, new_chain)
            return True

    return False


def adopt_chain(hashes: list, allow_equal: bool = False) -> bool:
    """
    Replace the canonical chain with the given list of hashes if all hashes
    are present in block_store and either:
      - the new chain is strictly longer than the current one, OR
      - allow_equal=True and the new chain has the same length but a
        lexicographically smaller tip hash (tie-breaking rule).
    Caller must hold state.lock. Returns True if adopted.
    """
    global blocks

    new_len = len(hashes)
    cur_len = chain_height()

    if new_len < cur_len:
        return False
    if new_len == cur_len:
        if not allow_equal:
            return False
        # Tie-break: only replace if new tip is lexicographically smaller
        new_tip = hashes[-1]
        our_tip = chain_tip() or ""
        if new_tip >= our_tip:
            return False

    new_blocks = {}
    for h in hashes:
        if h not in block_store:
            return False
        new_blocks[h] = block_store[h]

    old_chain = list(blocks.keys())
    blocks = new_blocks
    _reconcile_mempool(old_chain, hashes)
    print(f"  [chain] reorg: height={len(blocks)}, tip={list(blocks.keys())[-1][:8]}...")
    return True
