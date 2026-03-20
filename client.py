"""
client.py — HTTP client helpers for communicating with other nodes.
"""

import json
from urllib.request import urlopen, Request
from urllib.error import URLError


def http_get(url: str):
    """
    Sends a GET request and returns the response as parsed JSON.
    Returns None if the request fails.
    """
    try:
        with urlopen(url, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [GET error] {url} → {e}")
        return None


def http_post(url: str, data: dict):
    """
    Sends a POST request with JSON body and returns the response as parsed JSON.
    Returns None if the request fails.
    """
    try:
        body = json.dumps(data).encode()
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [POST error] {url} → {e}")
        return None