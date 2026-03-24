"""
discovery.py — Peer discovery and block synchronisation.

discover_peers():
    Walks the network using BFS starting from known peers.
    Asks each peer for their peer list via GET /addr.
    Stops when no new peers are found.
    Avoids infinite loops by tracking already-visited peers.

sync_blocks():
    After discovery, asks all known peers for their block hashes.
    Downloads any blocks this node is missing via GET /getdata/<hash>.
"""

import state
from client import http_get


def discover_peers():
    """
    BFS peer discovery.

    Start from the peers we already know (loaded from config),
    ask each one for their peers, add any new ones to the queue,
    and keep going until the queue is empty.

    We track 'visited' to avoid asking the same peer twice
    and to avoid asking ourselves (circular reference).
    """
    print("\n[peer discovery] starting...")

    # Mark ourselves as visited so we never add ourselves as a peer
    visited = {state.my_addr()}

    # Seed the queue with peers we already know
    with state.lock:
        queue = list(state.peers)

    while queue:
        peer = queue.pop(0)

        # Skip if we have already asked this peer
        if peer in visited:
            continue
        visited.add(peer)

        print(f"  [/addr] asking {peer}")
        result = http_get(f"http://{peer}/addr")

        # Peer is offline or returned an error — skip it
        if result is None:
            continue

        with state.lock:
            for p in result:
                # Never add ourselves
                if p == state.my_addr():
                    continue
                # Add to our peer list if new
                if p not in state.peers:
                    state.peers.add(p)
                    print(f"  [new peer] {p}")
                # Add to queue if we haven't visited it yet
                if p not in visited:
                    queue.append(p)

    with state.lock:
        print(f"[peer discovery] done. Known peers: {state.peers}\n")


def sync_blocks():
    """
    Block synchronisation.

    Ask every known peer for their list of block hashes.
    For each hash we don't have yet, fetch the full block content.
    This ensures a newly started node catches up with the network.
    """
    print("[block sync] starting...")

    with state.lock:
        current_peers = list(state.peers)
        known_hashes = set(state.blocks.keys())

    for peer in current_peers:
        # Get the list of block hashes this peer has
        result = http_get(f"http://{peer}/getblocks")
        if not result:
            continue

        for h in result:
            # Only fetch blocks we don't already have
            if h not in known_hashes:
                block_data = http_get(f"http://{peer}/getdata/{h}")
                if block_data and "content" in block_data:
                    with state.lock:
                        state.blocks[h] = block_data["content"]
                    known_hashes.add(h)
                    print(f"  [synced block] {h[:8]}... : {block_data['content']}")

    with state.lock:
        print(f"[block sync] done. Total blocks: {len(state.blocks)}\n")