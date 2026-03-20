"""
config.py — Load node configuration from a shared network.json file.

Expected config format:
{
    "nodes": [
        {"port": 5001, "peers": ["127.0.0.1:5002", "127.0.0.1:5003"]},
        {"port": 5002, "peers": ["127.0.0.1:5001"]},
        {"port": 5003, "peers": ["127.0.0.1:5001"]}
    ]
}
"""

import json
import state


def load_config(path: str):
    """
    Load network config file and populate initial peers for this node.
    Finds this node's entry by matching the port.
    If the file does not exist, the node starts with no peers.
    """
    try:
        with open(path) as f:
            config = json.load(f)

        # Find this node's entry by port
        node_config = None
        for node in config.get("nodes", []):
            if node["port"] == state.MY_PORT:
                node_config = node
                break

        if node_config is None:
            print(f"[config] port {state.MY_PORT} not found in {path}, starting with no peers")
            return

        for p in node_config.get("peers", []):
            if p != state.my_addr():
                state.peers.add(p)

        print(f"[config] loaded {path}")
        print(f"[config] initial peers: {state.peers}")

    except FileNotFoundError:
        print(f"[config] {path} not found, starting with no peers")