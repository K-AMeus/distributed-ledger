"""
discovery.py — Peer discovery and block synchronisation.

discover_peers():
    BFS walk starting from known peers using GET /addr.

sync_blocks():
    Downloads blocks from peers that are missing from our block_store.
    Uses state.add_block() so the canonical chain is updated correctly
    whenever a peer's blocks form a longer chain.
"""

import state
from client import http_get


def discover_peers():
    print("\n[peer discovery] starting...")

    visited = {state.my_addr()}

    with state.lock:
        queue = list(state.peers)

    while queue:
        peer = queue.pop(0)

        if peer in visited:
            continue
        visited.add(peer)

        print(f"  [/addr] asking {peer}")
        result = http_get(f"http://{peer}/addr")

        if result is None:
            continue

        with state.lock:
            for p in result:
                if p == state.my_addr():
                    continue
                if p not in state.peers:
                    state.peers.add(p)
                    print(f"  [new peer] {p}")
                if p not in visited:
                    queue.append(p)

    with state.lock:
        print(f"[peer discovery] done. peers={state.peers}\n")


def sync_blocks():
    """
    Download blocks from all peers that we don't yet have in our block_store.
    Blocks are added via state.add_block() which automatically updates the
    canonical chain if a longer chain is found.
    """
    print("[block sync] starting...")

    with state.lock:
        current_peers = list(state.peers)
        known = set(state.block_store.keys())

    for peer in current_peers:
        result = http_get(f"http://{peer}/getblocks")
        if not result:
            continue

        for h in result:
            if h in known:
                continue
            block_data = http_get(f"http://{peer}/getdata/{h}")
            if not block_data or "content" not in block_data:
                continue
            block = block_data["content"]
            content = block.get("content")
            prev_hash = block.get("prev_hash", state.GENESIS_PREV)
            if content is None:
                continue
            with state.lock:
                state.add_block(h, content, prev_hash)
            known.add(h)
            print(f"  [synced] {h[:8]}... from {peer}")

    with state.lock:
        print(f"[block sync] done. chain={state.chain_height()} store={len(state.block_store)}\n")
