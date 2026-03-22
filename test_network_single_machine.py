import hashlib, json, time, subprocess, sys, os
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE_PORT = 5001
NODES = []
procs = {}

def start_node(port):
    p = subprocess.Popen(
        [sys.executable, "node.py", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    procs[port] = p
    NODES.append(port)
    print(f"  [+] started node {port}")
    time.sleep(0.5)

def stop_node(port):
    if port in procs:
        procs[port].terminate()
        del procs[port]
        NODES.remove(port)
        print(f"  [-] stopped node {port}")

def ping(port):
    try:
        urlopen(f"http://127.0.0.1:{port}/addr", timeout=2)
        return True
    except:
        return False

def send_transaction(port, sender, receiver, amount):
    try:
        content = {"sender": sender, "receiver": receiver, "amount": amount}
        h = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        body = json.dumps({"hash": h, "content": content}).encode()
        req = Request(f"http://127.0.0.1:{port}/inv", data=body, headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=2).read().decode()
        return h, resp
    except Exception as e:
        return None, f"ERROR: {e}"

def send_block(port, transactions):
    try:
        content = {"transactions": transactions, "timestamp": int(time.time())}
        
        # Get current chain tip from node
        existing = get_blocks(port)
        prev_hash = existing[-1] if existing else "0" * 64

        # Hash = sha256(content + prev_hash)
        chain_content = {"content": content, "prev_hash": prev_hash}
        h = hashlib.sha256(json.dumps(chain_content, sort_keys=True).encode()).hexdigest()
        
        body = json.dumps({"hash": h, "content": content, "prev_hash": prev_hash}).encode()
        req = Request(f"http://127.0.0.1:{port}/block", data=body, headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=2).read().decode()
        return h, resp
    except Exception as e:
        return None, f"ERROR: {e}"

def get_blocks(port):
    try:
        return json.loads(urlopen(f"http://127.0.0.1:{port}/getblocks", timeout=2).read())
    except:
        return []

def report():
    print("\n  --- network status ---")
    for port in list(procs.keys()):
        blocks = get_blocks(port)
        alive = ping(port)
        print(f"  node {port}: {'UP' if alive else 'DOWN'} | blocks: {len(blocks)}")
    print()

# ── Test 1: start N nodes ────────────────────────────────────
print("\n=== TEST 1: starting 5 nodes ===")
for i in range(5):
    start_node(BASE_PORT + i)
time.sleep(2)
report()

# ── Test 2: send transactions ────────────────────────────────
print("=== TEST 2: sending 10 transactions to node 5001 ===")
txs = []
for i in range(10):
    content = {"sender": f"user{i}", "receiver": f"user{i+1}", "amount": round(i * 0.001, 4)}
    h, resp = send_transaction(BASE_PORT, f"user{i}", f"user{i+1}", round(i * 0.001, 4))
    if h:
        txs.append(content)
    print(f"  tx {i+1}: {resp}")
time.sleep(2)

# ── Test 3: send a block ─────────────────────────────────────
print("\n=== TEST 3: sending block with all transactions ===")
h, resp = send_block(BASE_PORT, txs)
print(f"  block response: {resp}")
time.sleep(2)
report()

# ── Test 4: kill 2 nodes ─────────────────────────────────────
print("=== TEST 4: killing nodes 5003 and 5004 ===")
stop_node(5003)
stop_node(5004)
time.sleep(1)
report()

# ── Test 5: send more transactions while nodes are down ──────
print("=== TEST 5: sending transactions while 2 nodes are down ===")
txs2 = []
for i in range(5):
    content = {"sender": f"alice{i}", "receiver": f"bob{i}", "amount": round(i * 0.002, 4)}
    h, resp = send_transaction(BASE_PORT, f"alice{i}", f"bob{i}", round(i * 0.002, 4))
    if h:
        txs2.append(content)
    print(f"  tx {i+1}: {resp}")
time.sleep(1)

h, resp = send_block(BASE_PORT, txs2)
print(f"  block response: {resp}")
time.sleep(2)
report()

# ── Test 6: add 3 new nodes ──────────────────────────────────
print("=== TEST 6: adding 3 new nodes ===")
for i in range(3):
    start_node(5010 + i)
time.sleep(3)
report()

# ── Test 7: stress test ──────────────────────────────────────
print("=== TEST 7: stress test — 50 transactions across all nodes ===")
alive_nodes = [p for p in procs.keys() if ping(p)]
print(f"  sending to {len(alive_nodes)} alive nodes")
start = time.time()
success = 0
txs3 = []
for i in range(50):
    port = alive_nodes[i % len(alive_nodes)]
    content = {"sender": f"s{i}", "receiver": f"r{i}", "amount": i * 0.0001}
    h, resp = send_transaction(port, f"s{i}", f"r{i}", i * 0.0001)
    if resp == "1":
        success += 1
        txs3.append(content)
elapsed = time.time() - start
print(f"  {success}/50 accepted in {elapsed:.2f}s ({50/elapsed:.1f} tx/s)")
time.sleep(2)

h, resp = send_block(BASE_PORT, txs3)
print(f"  block response: {resp}")
time.sleep(12)
report()

# ── Cleanup ──────────────────────────────────────────────────
print("=== cleanup: stopping all nodes ===")
for port in list(procs.keys()):
    stop_node(port)

print("\n=== done ===")