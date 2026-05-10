"""
demo.py -- Full demonstration: divergence + consensus.

PART 1 -- Task 1: reproduce the exact assignment scenario
  S1 sends T1 to S2 (not S3)
  S2 sends T2 to S3 (not S1)
  S3 sends T3 to S1 (not S2)
  Result: S1=(T1,T3)  S2=(T1,T2)  S3=(T2,T3)
  Each node mines a block -> three incompatible height-1 chains (divergence).

PART 2 -- Task 2a: equal-length tie, consensus CANNOT resolve
  Nodes are connected. All chains are height=1.
  Longest-chain rule needs a STRICTLY longer chain, so nobody switches.

PART 3 -- Task 2b: one chain grows longer, consensus SUCCEEDS
  S1 receives a new transaction and mines a second block (height=2).
  S2 and S3 detect the longer chain and adopt it -> all nodes agree.

Run:
    python demo.py
"""

import hashlib
import json
import subprocess
import sys
import time
from urllib.request import urlopen, Request

PORTS = [5001, 5002, 5003]
NAMES = ["S1", "S2", "S3"]
procs = {}
GENESIS = "0" * 64


# -- HTTP helpers --------------------------------------------------------------

def http_get(port, path):
    try:
        resp = urlopen(f"http://127.0.0.1:{port}{path}", timeout=3)
        return json.loads(resp.read())
    except Exception:
        return None


def http_post(port, path, data):
    try:
        body = json.dumps(data).encode()
        req = Request(
            f"http://127.0.0.1:{port}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        return json.loads(urlopen(req, timeout=3).read())
    except Exception as e:
        return f"ERROR: {e}"


def wait_for_server(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/addr", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def tx_hash(content):
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def block_hash(content, prev_hash):
    return hashlib.sha256(
        json.dumps({"content": content, "prev_hash": prev_hash}, sort_keys=True).encode()
    ).hexdigest()


# -- Node helpers --------------------------------------------------------------

def start_node(port):
    p = subprocess.Popen(
        [sys.executable, "node.py", str(port), "127.0.0.1", "nonexistent.json"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs[port] = p
    if not wait_for_server(port):
        print(f"  WARNING: node :{port} did not respond within 10 s")


def stop_all():
    for p in procs.values():
        p.terminate()
    procs.clear()
    print("  [cleanup] all nodes stopped.")


def add_peer(port, peer_port):
    http_post(port, "/addpeer", {"addr": f"127.0.0.1:{peer_port}"})


def connect_all():
    for p in PORTS:
        for q in PORTS:
            if p != q:
                add_peer(p, q)


# -- Transaction / block helpers -----------------------------------------------

def make_tx(sender, receiver, amount):
    content = {"sender": sender, "receiver": receiver, "amount": amount}
    return tx_hash(content), content


def store_local(port, h, content):
    """Store a transaction in a node's mempool WITHOUT broadcasting."""
    return http_post(port, "/inv_local", {"hash": h, "content": content})


def send_tx(port, sender, receiver, amount):
    """Send a transaction via normal /inv (will broadcast to known peers)."""
    content = {"sender": sender, "receiver": receiver, "amount": amount}
    h = tx_hash(content)
    r = http_post(port, "/inv", {"hash": h, "content": content})
    return h, content, r


def mine_block(port, prev_hash=None):
    """Mine a block using the node's current mempool."""
    mempool = http_get(port, "/mempool") or []
    if not mempool:
        return None, "mempool empty"
    if prev_hash is None:
        chain = http_get(port, "/getblocks") or []
        prev_hash = chain[-1] if chain else GENESIS
    content = {"transactions": mempool, "timestamp": int(time.time())}
    h = block_hash(content, prev_hash)
    r = http_post(port, "/block", {"hash": h, "content": content, "prev_hash": prev_hash})
    return h, r


# -- Reporting -----------------------------------------------------------------

def print_mempools(label=""):
    if label:
        print(f"\n{'-'*62}\n  {label}\n{'-'*62}")
    for i, port in enumerate(PORTS):
        txs = http_get(port, "/mempool") or []
        print(f"  {NAMES[i]} (:{port}) mempool ({len(txs)} tx):")
        for tx in txs:
            print(f"    {tx}")


def print_chains(label=""):
    if label:
        print(f"\n{'-'*62}\n  {label}\n{'-'*62}")
    for i, port in enumerate(PORTS):
        s = http_get(port, "/status") or {}
        tip = (s.get("chain_tip") or "none")[:16] + "..."
        chain = s.get("chain", [])
        print(f"  {NAMES[i]} (:{port})  height={s.get('chain_height', 0)}  store={s.get('block_store_size', 0)}  tip={tip}")
        for j, bh in enumerate(chain):
            print(f"           block[{j}] = {bh[:24]}...")


def all_agree():
    chains = [tuple(http_get(p, "/getblocks") or []) for p in PORTS]
    return len(set(chains)) == 1


# =============================================================================
# PART 1 -- Task 1: create divergent ledgers (exact assignment scenario)
# =============================================================================

print("\n" + "=" * 62)
print("  PART 1 -- Task 1: create divergent ledgers")
print("=" * 62)
print("""
  Assignment scenario:
    S1 sends T1 to S2 (not S3)
    S2 sends T2 to S3 (not S1)
    S3 sends T3 to S1 (not S2)

  Expected mempools:
    S1: (T1, T3)    S2: (T1, T2)    S3: (T2, T3)
""")

print("  Starting 3 isolated nodes (no peers)...")
for port in PORTS:
    start_node(port)
print(f"  Nodes: S1=:{PORTS[0]}  S2=:{PORTS[1]}  S3=:{PORTS[2]}\n")

# Create the three transactions
h_t1, t1 = make_tx("S1", "S2", 10)
h_t2, t2 = make_tx("S2", "S3", 20)
h_t3, t3 = make_tx("S3", "S1", 30)

print("  Transactions:")
print(f"    T1 = {t1}  hash={h_t1[:16]}...")
print(f"    T2 = {t2}  hash={h_t2[:16]}...")
print(f"    T3 = {t3}  hash={h_t3[:16]}...")

# Selective delivery via /inv_local (no broadcasting)
print("\n  Selective delivery via POST /inv_local (no flood):")
store_local(PORTS[0], h_t1, t1);  print(f"    T1 -> S1 (creator)")
store_local(PORTS[1], h_t1, t1);  print(f"    T1 -> S2 (target)")
store_local(PORTS[1], h_t2, t2);  print(f"    T2 -> S2 (creator)")
store_local(PORTS[2], h_t2, t2);  print(f"    T2 -> S3 (target)")
store_local(PORTS[2], h_t3, t3);  print(f"    T3 -> S3 (creator)")
store_local(PORTS[0], h_t3, t3);  print(f"    T3 -> S1 (target)")

print_mempools("Mempools after selective delivery")

# Verify
s1_txs = {tx["sender"] + tx["receiver"] for tx in (http_get(PORTS[0], "/mempool") or [])}
s2_txs = {tx["sender"] + tx["receiver"] for tx in (http_get(PORTS[1], "/mempool") or [])}
s3_txs = {tx["sender"] + tx["receiver"] for tx in (http_get(PORTS[2], "/mempool") or [])}
ok = (s1_txs == {"S1S2", "S3S1"} and s2_txs == {"S1S2", "S2S3"} and s3_txs == {"S2S3", "S3S1"})
print(f"\n  Assignment scenario reproduced correctly: {'YES' if ok else 'NO'}")

input("\n  [Press Enter to mine a block on each node -> divergent ledgers...]")

# Each node mines with its local mempool
print("\n  Mining (each node uses its own mempool):")
bh1, r = mine_block(PORTS[0]);  print(f"    S1 mined: {(bh1 or '?')[:24]}...")
bh2, r = mine_block(PORTS[1]);  print(f"    S2 mined: {(bh2 or '?')[:24]}...")
bh3, r = mine_block(PORTS[2]);  print(f"    S3 mined: {(bh3 or '?')[:24]}...")

print_chains("Chains after mining -- all different blocks on the same genesis")
all_diff = len({bh1, bh2, bh3}) == 3
print(f"\n  All three blocks different: {'YES -- ledgers have diverged!' if all_diff else 'NO'}")

input("\n  [Press Enter to connect nodes and attempt consensus (Part 2)...]")

# =============================================================================
# PART 2 -- Task 2a: equal-length tie, consensus cannot resolve
# =============================================================================

print("\n" + "=" * 62)
print("  PART 2 -- Task 2a: connecting nodes, equal-length tie")
print("=" * 62)
print("""
  All chains are height=1. Longest-chain rule only fires when a peer
  has a STRICTLY longer chain. Nobody switches -> inconsistency persists.
""")

print("  Connecting all nodes via /addpeer...")
connect_all()

print("  Waiting 15 s for consensus rounds to run...")
time.sleep(15)

print_chains("After first consensus round")

if all_agree():
    print("\n  Nodes happen to agree (rare for equal-length chains).")
else:
    print("""
  FAIL (expected): nodes still disagree.

    Each node downloaded the others' blocks (store=3) but kept its own
    block as canonical -- because no chain is strictly longer.
    This is the known limitation of the longest-chain algorithm.
""")

input("\n  [Press Enter to break the tie (Part 3 -- consensus succeeds)...]")

# =============================================================================
# PART 3 -- Task 2b: S1 mines a second block, consensus resolves
# =============================================================================

print("\n" + "=" * 62)
print("  PART 3 -- Task 2b: one chain grows longer, consensus SUCCEEDS")
print("=" * 62)
print("""
  We send a new transaction directly to S1 and let it mine a second block
  (height=2). S2 and S3 will detect the longer chain and adopt it.
""")

h_t4, t4, r = send_tx(PORTS[0], "S1", "S2", 99)
print(f"  T4 -> S1  {t4}  result={r}")

bh_new, r = mine_block(PORTS[0])
if bh_new:
    print(f"  S1 mined block 2: {bh_new[:24]}...  result={r}")
    print_chains("After S1 mines block 2  (S1=height 2, others still height 1)")
else:
    print(f"  Mining failed: {r}")

print("\n  Waiting 15 s for the next consensus round...")
time.sleep(15)

print_chains("After second consensus round")

if all_agree():
    chains = [http_get(p, "/getblocks") or [] for p in PORTS]
    tip = (chains[0][-1] if chains[0] else "?")[:24]
    print(f"""
  OK  All nodes now agree (height=2, tip={tip}...)

    All three nodes show the SAME two block hashes -- proof they are
    on the same chain.  S2 and S3 did NOT mine new blocks; they
    REPLACED their own height-1 chain with S1's height-2 chain.
    That replacement is what brought their height from 1 to 2.

    What happened:
      1. S2 and S3 asked each peer: GET /chainlen
      2. S1 replied with 2; S2 and S3 had 1 -> strictly longer -> sync
      3. S2 and S3 downloaded S1's two blocks via GET /getdata/<hash>
      4. Both discarded their old block and adopted S1's chain
""")
else:
    print("""
  Nodes still disagree after the second round.
  Possible cause: consensus background timer hasn't fired yet.
  Waiting an extra 15 s...
""")
    time.sleep(15)
    print_chains("After extra wait")
    if all_agree():
        print("\n  OK  All nodes agree now.")
    else:
        print("\n  Still disagreeing -- inspect manually:")
        for i, port in enumerate(PORTS):
            print(f"    http://127.0.0.1:{port}/status")

# =============================================================================
# Summary
# =============================================================================

print("\n" + "=" * 62)
print("  SUMMARY")
print("=" * 62)
print("""
  Algorithm: longest-chain consensus (consensus.py + state.py)
  ------------------------------------------------------------
  Every 10 s each node:
    1. Discovers peers via GET /addr
    2. Downloads missing blocks from peers
    3. Asks each peer: GET /chainlen
       If peer length > ours -> download and adopt their chain

  Works when:  chains have DIFFERENT lengths
  Fails when:  all chains are the same length (tie, as shown in Part 2)

  Fix for the tie (not implemented):
    When lengths are equal, prefer the chain whose tip hash is
    lexicographically smaller -- deterministic, no extra messages.
""")

print(f"  Nodes still live for inspection:")
for i, port in enumerate(PORTS):
    print(f"    http://127.0.0.1:{port}/status")

input("\n  [Press Enter to stop all nodes and exit...]")
stop_all()
