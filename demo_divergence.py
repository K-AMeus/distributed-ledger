"""
demo_divergence.py - Demonstrates ledger divergence and consensus recovery.

PART 1 - Creating divergence (assignment: 20%)
  Three nodes start in complete isolation (no peers).
  Each node gets a unique transaction and builds its own block.
  Result: S1=[B1], S2=[B2], S3=[B3] -- three incompatible height-1 chains.

PART 2 - Equal-length fork: consensus CANNOT resolve (assignment: 30% failure case)
  We connect the nodes via /addpeer.  All three chains have height=1.
  The longest-chain rule needs a strictly longer chain to fire, so no node
  adopts another's chain -- the inconsistency remains.

PART 3 - One chain grows longer: consensus SUCCEEDS (assignment: 35%)
  S1 mines a second block (height=2).  After the next consensus round,
  S2 and S3 detect the longer chain, download S1's blocks and adopt them.

Run:
    python demo_divergence.py
"""

import hashlib
import json
import subprocess
import sys
import time
from urllib.request import urlopen, Request

PORTS = [5101, 5102, 5103]
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
        resp = urlopen(req, timeout=3)
        return json.loads(resp.read())
    except Exception as e:
        return f"ERROR: {e}"


def wait_for_server(port, timeout=10):
    """Poll GET /addr until the server responds or timeout expires."""
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


def send_tx(port, sender, receiver, amount):
    content = {"sender": sender, "receiver": receiver, "amount": amount}
    h = tx_hash(content)
    r = http_post(port, "/inv", {"hash": h, "content": content})
    return h, content, r


def send_block(port, transactions, prev_hash=GENESIS):
    content = {"transactions": transactions, "timestamp": int(time.time())}
    h = block_hash(content, prev_hash)
    r = http_post(port, "/block", {"hash": h, "content": content, "prev_hash": prev_hash})
    return h, r


def add_peer(port, peer_port):
    return http_post(port, "/addpeer", {"addr": f"127.0.0.1:{peer_port}"})


def connect_all():
    """Add every PORTS entry as a peer to every other."""
    for p in PORTS:
        for q in PORTS:
            if p != q:
                add_peer(p, q)


# -- Reporting -----------------------------------------------------------------

def print_status(label=""):
    if label:
        print(f"\n{'-'*62}")
        print(f"  {label}")
        print(f"{'-'*62}")
    for i, port in enumerate(PORTS):
        s = http_get(port, "/status")
        if not s:
            print(f"  S{i+1} :{port}  UNREACHABLE")
            continue
        chain = s.get("chain", [])
        tip = (s.get("chain_tip") or "none")[:12] + "..."
        print(f"  S{i+1} :{port}  height={s['chain_height']}  store={s['block_store_size']}  tip={tip}")
        for j, bh in enumerate(chain):
            print(f"         block[{j}] = {bh[:20]}...")


def all_agree():
    chains = []
    for port in PORTS:
        c = http_get(port, "/getblocks")
        if c is None:
            return False
        chains.append(tuple(c))
    return len(set(chains)) == 1


# -- Node lifecycle ------------------------------------------------------------

def start_node(port):
    """Start node with no initial peers (isolated) and wait until it is ready."""
    p = subprocess.Popen(
        [sys.executable, "node.py", str(port), "127.0.0.1", "nonexistent.json"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs[port] = p
    if not wait_for_server(port):
        print(f"  WARNING: node :{port} did not respond within 10 s -- demo may fail")


def stop_all():
    for p in procs.values():
        p.terminate()
    procs.clear()
    print("  [cleanup] all nodes stopped.")


# =============================================================================
# PART 1 -- Divergence
# =============================================================================

print("\n" + "=" * 62)
print("  PART 1  --  Creating divergent ledgers")
print("=" * 62)
print("""
  S1, S2, S3 start with NO peers (completely isolated).
  Each receives one unique transaction and mines one block.
""")

print("  Starting 3 isolated nodes...")
for port in PORTS:
    start_node(port)
print(f"\n  Nodes are live:  S1=http://127.0.0.1:{PORTS[0]}  S2=http://127.0.0.1:{PORTS[1]}  S3=http://127.0.0.1:{PORTS[2]}")

print("\n  Sending unique transactions (no cross-node broadcasting):")
h_t1, t1, r = send_tx(PORTS[0], "Alice",  "Bob",   10)
print(f"    T1 -> S1  {t1}  result={r}")
h_t2, t2, r = send_tx(PORTS[1], "Bob",    "Carol", 20)
print(f"    T2 -> S2  {t2}  result={r}")
h_t3, t3, r = send_tx(PORTS[2], "Carol",  "Alice", 30)
print(f"    T3 -> S3  {t3}  result={r}")

print("\n  Each node mines its own block (all on genesis, prev_hash=0*64):")
bh1, r = send_block(PORTS[0], [t1])
print(f"    B1 mined by S1: {bh1[:20]}...  result={r}")
bh2, r = send_block(PORTS[1], [t2])
print(f"    B2 mined by S2: {bh2[:20]}...  result={r}")
bh3, r = send_block(PORTS[2], [t3])
print(f"    B3 mined by S3: {bh3[:20]}...  result={r}")

print_status("State after mining -- divergent ledgers")

print("""
  Result:
    S1 ledger: [B1]  (contains T1: Alice -> Bob)
    S2 ledger: [B2]  (contains T2: Bob -> Carol)
    S3 ledger: [B3]  (contains T3: Carol -> Alice)

  Nodes are still running -- inspect them now if you like:
    http://127.0.0.1:{p0}/status   http://127.0.0.1:{p1}/status   http://127.0.0.1:{p2}/status
""".format(p0=PORTS[0], p1=PORTS[1], p2=PORTS[2]))

input("  [Press Enter to continue to Part 2...]")

# =============================================================================
# PART 2 -- Equal-length fork: consensus FAILS
# =============================================================================

print("\n" + "=" * 62)
print("  PART 2  --  Equal-length fork: consensus CANNOT resolve (failure case)")
print("=" * 62)
print("""
  We connect all nodes.  All three chains still have height=1.
  Longest-chain rule: adopt only if peer chain is STRICTLY longer.
  Height 1 vs height 1 -- no winner -- inconsistency persists.
""")

print("  Connecting all nodes via /addpeer...")
connect_all()

print("  Waiting 15 s for the consensus rounds to run...")
time.sleep(15)

print_status("After first consensus round -- equal-length chains")

if all_agree():
    print("\n  OK  Nodes happened to agree (unlikely for equal-length chains).")
else:
    print("""
  FAIL  Nodes still disagree -- as expected.

    The longest-chain rule fires only when a peer's chain is STRICTLY
    longer than ours.  With three competing height-1 chains, no node
    ever sees a longer chain and so no node ever switches.

    This is the intentional failure case: the algorithm guarantees
    convergence only when chains have DIFFERENT lengths.

  Inspect now (note store=3 on each: they downloaded each other's
  blocks but kept their own as canonical):
    http://127.0.0.1:{p0}/status
""".format(p0=PORTS[0]))

input("  [Press Enter to continue to Part 3...]")

# =============================================================================
# PART 3 -- Longer chain wins: consensus SUCCEEDS
# =============================================================================

print("\n" + "=" * 62)
print("  PART 3  --  One chain grows longer: consensus SUCCEEDS")
print("=" * 62)
print("""
  We send a new transaction only to S1 and mine a second block there
  (height=2).  After the next consensus round, S2 and S3 should detect
  the longer chain and adopt it.
""")

h_t4, t4, r = send_tx(PORTS[0], "Dave", "Eve", 50)
print(f"  T4 -> S1  {t4}  result={r}")

if r == 1 or r == "1":
    s1_chain = http_get(PORTS[0], "/getblocks")
    if s1_chain:
        s1_tip = s1_chain[-1]
        bh_new, r = send_block(PORTS[0], [t4], prev_hash=s1_tip)
        print(f"  B_new mined by S1 on top of {s1_tip[:20]}...  result={r}")
        print_status("After S1 mines block 2  (S1 height=2, others still height=1)")
        print(f"\n  Inspect S1 now at http://127.0.0.1:{PORTS[0]}/status  (should show height=2)")

        input("  [Press Enter to wait for the next consensus round (15 s)...]")
        print("  Waiting 15 s for the next consensus round...")
        time.sleep(15)

        print_status("After second consensus round")

        if all_agree():
            print("""
  OK  All nodes now agree on S1's chain (height=2)!

    What happened:
      1. S2 and S3 asked each peer: GET /chainlen
      2. S1 answered: 2.  S2 and S3 have: 1.  Strictly longer -- sync.
      3. S2 and S3 downloaded S1's blocks (B1, B_new) via /getdata.
      4. Both rebuilt their canonical chain from S1's block list.
      5. Their old single-block chains were replaced.
""")
        else:
            print("\n  Chains after consensus round:")
            for i, port in enumerate(PORTS):
                c = http_get(port, "/getblocks")
                print(f"    S{i+1}: {[h[:12]+'...' for h in (c or [])]}")
            print("""
  FAIL  Nodes still disagree.  Possible causes:
      - Background discovery has not had enough time (try waiting longer).
      - S1 may have been overwritten if a peer had a competing chain.
""")
    else:
        print("  Could not get S1's chain tip -- was it reorganised?")
else:
    print(f"  T4 rejected by S1 (result={r}) -- S1 may have been reorganised.")
    print("  Finding current longest chain owner...")
    best_port = max(PORTS, key=lambda p: http_get(p, "/chainlen") or 0)
    best_len = http_get(best_port, "/chainlen")
    print(f"  Longest chain at S{PORTS.index(best_port)+1} (:{best_port}), height={best_len}")
    print("  Try re-running; the equal-length tie case is non-deterministic.")

# =============================================================================
# Summary
# =============================================================================

print("\n" + "=" * 62)
print("  ALGORITHM SUMMARY -- Longest-chain consensus")
print("=" * 62)
print("""
  Implementation (consensus.py + state.py):
  ------------------------------------------
  * Every block has a prev_hash and a computed height.
  * Every 10 s each node asks every peer: GET /chainlen
  * If a peer's chain length > ours:
      1. GET /getblocks   -> their canonical chain hash list
      2. GET /getdata/<h> -> download blocks we are missing
      3. state.add_block() inserts into block_store
      4. state.adopt_chain() rebuilds the canonical chain

  Works when:   chains have different lengths (one partition did more work)
  Fails when:   chains have the same length (tie -- no deterministic winner)

  Fix for the tie case (not implemented, but straightforward):
      When lengths are equal, prefer the chain whose tip hash is
      lexicographically smaller -- deterministic, no extra communication
      (same idea as Bitcoin's proof-of-work difficulty comparison).

  Nodes are still running on ports {p0}, {p1}, {p2}.
  You can inspect them freely before stopping.
""".format(p0=PORTS[0], p1=PORTS[1], p2=PORTS[2]))

input("  [Press Enter to stop all nodes and exit...]")
stop_all()
