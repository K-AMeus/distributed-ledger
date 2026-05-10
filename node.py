"""
node.py — Main entrypoint. Starts the P2P node.

Usage:
    python node.py <port> [ip] [config_file]

Examples:
    python node.py 5001
    python node.py 5001 192.168.1.10
    python node.py 5001 127.0.0.1 network.json
"""

import sys
import time
import threading

import state
import config
import discovery
import server
import consensus


def background_loop():
    """Peer discovery + block sync + consensus, repeated every 5 s."""
    time.sleep(1)  # Let the HTTP server start first
    while True:
        discovery.discover_peers()
        discovery.sync_blocks()
        consensus.run_consensus_round()
        time.sleep(5)


def main():
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [ip] [config_file]")
        sys.exit(1)

    state.MY_PORT = int(sys.argv[1])
    state.MY_IP = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    config_file = sys.argv[3] if len(sys.argv) > 3 else "network.json"

    config.load_config(config_file)

    threading.Thread(target=background_loop, daemon=True).start()

    try:
        server.run_server(state.MY_PORT)
    except KeyboardInterrupt:
        print("\n[server] stopped")


if __name__ == "__main__":
    main()
