"""
consensus.py — Longest-chain consensus algorithm.

Each node periodically asks all known peers for their chain length.
If any peer has a strictly longer chain, we download their full chain
(fetching any blocks we don't yet have) and adopt it as our canonical chain.

Tie-breaking rule (equal-length chains): when two chains have the same
height, prefer the one whose tip hash is lexicographically smaller.
This is deterministic and requires no extra messages.
"""

import state
from client import http_get


def _get_peer_chain_length(peer: str) -> int:
    result = http_get(f"http://{peer}/chainlen")
    if isinstance(result, int):
        return result
    return 0


def _download_block(peer: str, block_hash: str) -> bool:
    """Fetch one block from peer and insert it into block_store (no mempool check)."""
    data = http_get(f"http://{peer}/getdata/{block_hash}")
    if not data or "content" not in data:
        return False

    block = data["content"]
    content = block.get("content")
    prev_hash = block.get("prev_hash", state.GENESIS_PREV)

    if not content:
        return False

    with state.lock:
        state.add_block(block_hash, content, prev_hash)
    return True


def sync_from_peer(peer: str) -> bool:
    """
    Download and adopt a peer's chain if it is longer than ours, or if it
    has the same length but a lexicographically smaller tip hash (tie-break).
    Returns True if our canonical chain was updated.
    """
    their_len = _get_peer_chain_length(peer)
    with state.lock:
        our_len = state.chain_height()
        our_tip = state.chain_tip() or ""

    if their_len < our_len:
        return False  # Strictly shorter, nothing to do

    # Fetch their chain hash list (needed for both the tie-break check and adoption)
    their_hashes = http_get(f"http://{peer}/getblocks")
    if not their_hashes:
        return False

    their_tip = their_hashes[-1]
    is_tiebreak = False

    if their_len == our_len:
        if their_tip >= our_tip:
            return False  # Same length, our tip is already ≤ theirs — keep ours
        is_tiebreak = True
        print(
            f"  [consensus] tie at height={our_len}: "
            f"peer tip={their_tip[:16]}... < ours={our_tip[:16]}..., breaking tie"
        )
    else:
        print(f"  [consensus] peer {peer} has chain len={their_len} (ours={our_len}), syncing...")

    # Download any blocks we don't yet have, in chain order
    for h in their_hashes:
        with state.lock:
            already_have = h in state.block_store
        if not already_have:
            _download_block(peer, h)

    # Try to adopt their chain
    with state.lock:
        adopted = state.adopt_chain(their_hashes, allow_equal=is_tiebreak)

    if adopted:
        verb = "tie-break adopted" if is_tiebreak else "adopted"
        print(f"  [consensus] {verb} chain from {peer} (height={their_len})")
    else:
        print(f"  [consensus] could not adopt chain from {peer} (missing blocks?)")

    return adopted


def run_consensus_round():
    """
    One consensus round: compare our chain against all known peers.
    Adopts the longest chain found.
    """
    with state.lock:
        current_peers = list(state.peers)

    if not current_peers:
        return

    updated = False
    for peer in current_peers:
        if sync_from_peer(peer):
            updated = True

    if not updated:
        with state.lock:
            h = state.chain_height()
        print(f"  [consensus] already at longest known chain (height={h})")
