"""
client.py — HTTP client helpers for communicating with other nodes.
"""

import json
import time
from urllib.request import urlopen, Request
from urllib.error import URLError


def http_get(url: str):
    for attempt in range(3):
        try:
            with urlopen(url, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == 2:
                print(f"  [GET error] {url} → {e}")
            time.sleep(0.3)
    return None


def http_post(url: str, data: dict):
    for attempt in range(3):
        try:
            body = json.dumps(data).encode()
            req = Request(url, data=body, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == 2:
                print(f"  [POST error] {url} → {e}")
            time.sleep(0.3)
    return None