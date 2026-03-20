"""
node.py — Main entrypoint. Starts the P2P node.

Usage:
    python node.py <port> [config_file]

Examples:
    python node.py 5001
    python node.py 5001 config_5001.json
"""

import sys
import time
import threading

import state
import config
import discovery
import server


def startup_tasks():
    """Run peer discovery and block sync after server has started."""
    time.sleep(1)  # Wait for server to be ready
    discovery.discover_peers()
    discovery.sync_blocks()


def main():
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [config_file]")
        sys.exit(1)

    # Set this node's port
    state.MY_PORT = int(sys.argv[1])
    config_file = sys.argv[2] if len(sys.argv) > 2 else "network.json"

    # Load config (initial peers)
    config.load_config(config_file)

    # Run discovery and sync in background after server starts
    threading.Thread(target=startup_tasks, daemon=True).start()

    # Start HTTP server (blocking)
    try:
        server.run_server(state.MY_PORT)
    except KeyboardInterrupt:
        print("\n[server] stopped")


if __name__ == "__main__":
    main()