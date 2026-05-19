"""
demo.py -- Full demonstration: divergence + consensus.

PART 1 -- Create divergent ledgers (no consensus)
PART 2 -- Equal-length tie: consensus fails then resolves via tie-break
PART 3 -- Longer chain wins: consensus succeeds
PART 4 -- Rapid concurrent mining: consensus cannot keep up

Run:
    python demo.py
"""
MINING_ROUNDS = 5
MINE_INTERVAL = 0.5



import hashlib
import json
import subprocess
import sys
import time
import threading
from urllib.request import urlopen, Request

CONSENSUS_INTERVAL = 2
consensus_stop = threading.Event()

PORTS = [5001, 5002, 5003]
NAMES = ["S1", "S2", "S3"]
procs = {}
GENESIS = "0" * 64

W = 62  # output width


# -- Formatting helpers --------------------------------------------------------

def banner(title):
    print(f"\n{'█' * W}")
    print(f"  {title}")
    print(f"{'█' * W}")


def section(title):
    print(f"\n  ┌{'─' * (W - 4)}┐")
    print(f"  │ {title:<{W - 5}}│")
    print(f"  └{'─' * (W - 4)}┘")


def result_pass(msg):
    print(f"\n  ✓ RESULT: {msg}")


def result_fail(msg):
    print(f"\n  ✗ RESULT: {msg}")


def wait_msg(seconds):
    print(f"\n  ⏳ Waiting {seconds}s for consensus round...")
    time.sleep(seconds)


# -- HTTP helpers --------------------------------------------------------------

def http_get(port, path):
    for _ in range(5):
        try:
            resp = urlopen(f"http://127.0.0.1:{port}{path}", timeout=5)
            return json.loads(resp.read())
        except Exception:
            time.sleep(0.3)
    return None


def http_post(port, path, data):
    for _ in range(5):
        try:
            body = json.dumps(data).encode()
            req = Request(
                f"http://127.0.0.1:{port}{path}",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            return json.loads(urlopen(req, timeout=5).read())
        except Exception:
            time.sleep(0.3)
    return None


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

def kill_port(port):
    """Kill any process currently listening on this TCP port (cross-platform)."""
    if sys.platform == "win32":
        # netstat -ano lists PID; find lines with the target port in LISTENING state
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    else:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    time.sleep(0.3)


def start_node(port):
    kill_port(port)
    p = subprocess.Popen(
        [sys.executable, "node.py", str(port), "127.0.0.1", "nonexistent.json", "--no-loop"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs[port] = p
    if not wait_for_server(port):
        print(f"  ⚠  node :{port} did not respond within 10s")


def trigger_sync(rounds=1):
    """Trigger one full sync+consensus cycle on all nodes."""
    for _ in range(rounds):
        for port in PORTS:
            http_post(port, "/sync", {})
        time.sleep(0.5)


def stop_all():
    for p in procs.values():
        p.terminate()
    procs.clear()
    time.sleep(0.5)
    for port in PORTS:
        kill_port(port)
    print("  All nodes stopped.")


def add_peer(port, peer_port):
    http_post(port, "/addpeer", {"addr": f"127.0.0.1:{peer_port}"})


def connect_all():
    for p in PORTS:
        for q in PORTS:
            if p != q:
                add_peer(p, q)
                
def consensus_background():
    while not consensus_stop.is_set():
        for port in PORTS:
            http_post(port, "/sync", {})
        consensus_stop.wait(CONSENSUS_INTERVAL)
        print("\n  [Consensus round state]")
        print_chains_compact()


# -- Transaction / block helpers -----------------------------------------------

def make_tx(sender, receiver, amount):
    content = {
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "timestamp": time.time(),
    }
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
    if r == 1:
        return h, r
    return None, r


# -- Reporting -----------------------------------------------------------------

def print_mempools():
    for i, port in enumerate(PORTS):
        txs = http_get(port, "/mempool") or []
        items = ", ".join(f"{t['sender']}→{t['receiver']}" for t in txs)
        print(f"    {NAMES[i]}  [{len(txs)} tx]  {items}")


def print_chains():
    for i, port in enumerate(PORTS):
        s = http_get(port, "/status") or {}
        h = s.get("chain_height", 0)
        tip = (s.get("chain_tip") or "none")[:16]
        chain = s.get("chain", [])
        blocks_str = " → ".join(bh[:10] for bh in chain) if chain else "(empty)"
        print(f"    {NAMES[i]}  height={h}  tip={tip}…")
        print(f"         {blocks_str}")


def print_chains_compact():
    for i, port in enumerate(PORTS):
        s = http_get(port, "/status") or {}
        h = s.get("chain_height", 0)
        tip = (s.get("chain_tip") or "?")[:12]
        st = s.get("block_store_size", 0)
        print(f"    {NAMES[i]}  height={h}  tip={tip}…  store={st}")


def all_agree():
    chains = [tuple(http_get(p, "/getblocks") or []) for p in PORTS]
    return len(set(chains)) == 1


# =============================================================================
# PART 1 -- Create divergent ledgers
# =============================================================================

banner("PART 1 — Create divergent ledgers (no consensus)")

print("""
  Scenario (from assignment):
    S1 sends T1 to S2 only       S2 sends T2 to S3 only
    S3 sends T3 to S1 only

  Expected result:
    S1: {T1, T3}    S2: {T1, T2}    S3: {T2, T3}
""")

section("Starting 3 isolated nodes")
for port in PORTS:
    start_node(port)
print(f"    S1=:{PORTS[0]}   S2=:{PORTS[1]}   S3=:{PORTS[2]}")

section("Creating transactions")
h_t1, t1 = make_tx("S1", "S2", 10)
h_t2, t2 = make_tx("S2", "S3", 20)
h_t3, t3 = make_tx("S3", "S1", 30)
print(f"    T1: S1→S2, 10 coins    hash={h_t1[:12]}…")
print(f"    T2: S2→S3, 20 coins    hash={h_t2[:12]}…")
print(f"    T3: S3→S1, 30 coins    hash={h_t3[:12]}…")

section("Selective delivery (no broadcast)")
store_local(PORTS[0], h_t1, t1); store_local(PORTS[1], h_t1, t1)
store_local(PORTS[1], h_t2, t2); store_local(PORTS[2], h_t2, t2)
store_local(PORTS[2], h_t3, t3); store_local(PORTS[0], h_t3, t3)
print(f"    T1 → S1, S2      T2 → S2, S3      T3 → S3, S1")

section("Mempools after delivery")
print_mempools()

s1_txs = {tx["sender"] + tx["receiver"] for tx in (http_get(PORTS[0], "/mempool") or [])}
s2_txs = {tx["sender"] + tx["receiver"] for tx in (http_get(PORTS[1], "/mempool") or [])}
s3_txs = {tx["sender"] + tx["receiver"] for tx in (http_get(PORTS[2], "/mempool") or [])}
ok = (s1_txs == {"S1S2", "S3S1"} and s2_txs == {"S1S2", "S2S3"} and s3_txs == {"S2S3", "S3S1"})
if ok:
    result_pass("Mempools match assignment scenario exactly")
else:
    result_fail("Mempools do not match expected scenario")

input("\n  [Enter] Mine a block on each node →")

section("Mining one block per node")
bh1, r = mine_block(PORTS[0]); print(f"    S1 mined: {(bh1 or '?')[:16]}…")
bh2, r = mine_block(PORTS[1]); print(f"    S2 mined: {(bh2 or '?')[:16]}…")
bh3, r = mine_block(PORTS[2]); print(f"    S3 mined: {(bh3 or '?')[:16]}…")

section("Chain state — three different height-1 chains")
print_chains()

all_diff = len({bh1, bh2, bh3}) == 3
if all_diff:
    result_fail("Ledgers have DIVERGED — all three blocks are different")
else:
    result_pass("Blocks are not all different (unexpected)")

input("\n  [Enter] Connect nodes and attempt consensus (Part 2) →")

# =============================================================================
# PART 2 -- Equal-length tie
# =============================================================================

banner("PART 2 — Equal-length tie (failure → resolution)")

print("""
  All chains are height=1.  Longest-chain rule needs a STRICTLY longer
  chain, so equal-length tie leaves nodes stuck.

  Tie-break rule: when heights are equal, adopt the chain whose tip
  hash is lexicographically smallest (deterministic, no extra messages).
""")

tips = {}
for i, port in enumerate(PORTS):
    chain = http_get(port, "/getblocks") or []
    tips[NAMES[i]] = chain[-1] if chain else ""

winning_name = min(tips, key=lambda n: tips[n])
winning_tip  = tips[winning_name]

section("STEP 2a — Connect nodes (before consensus fires)")
connect_all()
print(f"    All nodes connected via /addpeer")

section("Chain state — immediately after connecting")
print_chains_compact()

if not all_agree():
    result_fail("Nodes DISAGREE — consensus has not fired yet")
    print("    All chains are height=1, no chain is strictly longer.")
    print(f"    Predicted tie-break winner: {winning_name} (smallest tip hash)")
else:
    result_pass("Consensus fired instantly (timing was close)")

input("\n  [Enter] Wait for tie-break consensus round →")

section("STEP 2b — After consensus round")
trigger_sync(rounds=2)
print_chains_compact()

adopted_tip = (http_get(PORTS[0], "/getblocks") or [""])[-1]
if all_agree() and adopted_tip == winning_tip:
    result_pass(f"Tie-break resolved — all adopted {winning_name}'s chain")
    print(f"    Tip: {winning_tip[:24]}…")
    print("    Mechanism: equal height → compare tip hashes → smallest wins")
elif all_agree():
    result_pass(f"Nodes agree (tip={adopted_tip[:16]}…)")
else:
    result_fail("Still disagreeing after 2 sync rounds")

input("\n  [Enter] Grow one chain longer (Part 3) →")

# =============================================================================
# PART 3 -- Longer chain wins
# =============================================================================

banner("PART 3 — Longer chain wins (consensus succeeds)")

print("""
  S1 gets a new transaction and mines block 2 (height=2).
  S2 and S3 still have height=1.  Consensus detects the longer chain
  and all nodes adopt S1's chain.
""")

print_chains_compact()

section("S1 mines block 2")
h_t4, t4 = make_tx("S1", "S2", 99)
for port in PORTS:
    store_local(port, h_t4, t4)  # T4 in all mempools before mining
print(f"    New tx: S1→S2, 99 coins")
bh_new, r = mine_block(PORTS[0])
if bh_new:
    print(f"    S1 mined: {bh_new[:16]}…")
else:
    print(f"    Mining failed: {r}")

section("After consensus round")
trigger_sync(rounds=2)
print_chains_compact()

if all_agree():
    chains = [http_get(p, "/getblocks") or [] for p in PORTS]
    tip = (chains[0][-1] if chains[0] else "?")[:16]
    result_pass(f"All nodes agree — adopted S1's chain (height=2, tip={tip}…)")
    print("    Mechanism: S1 has height=2 > others' height=1 → sync")
else:
    result_fail("Still disagreeing after 20s")

input("\n  [Enter] Consensus failure under load (Part 4) →")

# =============================================================================
# PART 4 -- Rapid concurrent mining outpaces consensus
# =============================================================================

banner("PART 4 — Consensus FAILURE: rapid concurrent mining")

print("""
  All 3 nodes mine simultaneously every 0.5s.
  Consensus round runs every 5s.
  → Forks are created 10x faster than consensus can resolve.
  → Each node's transactions are LOCAL ONLY (peers reject the blocks).
  → The system never stabilises.
""")


def _inject_and_mine(port, name, rnd, results):
    """Thread target: inject a unique tx into one node, then mine a block."""
    content = {"sender": name, "receiver": f"rapid_{rnd}", "amount": rnd + port * 0.001}
    h = tx_hash(content)
    store_local(port, h, content)
    bh, r = mine_block(port)
    results[name] = (bh, r, content)


section("Starting state (all agree from Part 3)")
print_chains_compact()

disagree_rounds = []
agree_rounds = []

consensus_thread = threading.Thread(target=consensus_background, daemon=True)
consensus_thread.start()

for rnd in range(1, MINING_ROUNDS + 1):
    results = {}
    threads = [
        threading.Thread(target=_inject_and_mine, args=(port, name, rnd, results))
        for port, name in zip(PORTS, NAMES)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"\n  ── Round {rnd}/{MINING_ROUNDS} ({'─' * 44}")

    for name in NAMES:
        bh, r, tx = results.get(name, (None, None, {}))
        if bh:
            print(f"    {name} mined {bh[:12]}…  (tx: {tx['sender']}→{tx['receiver']})")
        else:
            print(f"    {name} FAILED ({r})")

    chain_data = {}
    for port, name in zip(PORTS, NAMES):
        s = http_get(port, "/status") or {}
        chain_data[name] = {
            "height": s.get("chain_height", 0),
            "tip": (s.get("chain_tip") or "?")[:12],
            "store": s.get("block_store_size", 0),
            "chain": s.get("chain", []),
        }

    for name in NAMES:
        d = chain_data[name]
        print(f"    {name}: height={d['height']}  tip={d['tip']}…  store={d['store']}")

    chains = [tuple(chain_data[n]["chain"]) for n in NAMES]
    agree = len(set(chains)) == 1
    if agree:
        agree_rounds.append(rnd)
        print("    → AGREE")
    else:
        disagree_rounds.append(rnd)
        print(f"    → DISAGREE ({len(set(chains))} different chains)")

    time.sleep(MINE_INTERVAL)

# Conclusion
total = MINING_ROUNDS
dis = len(disagree_rounds)
agr = len(agree_rounds)

consensus_stop.set()
consensus_thread.join(timeout=1)

section("Part 4 results")

for port, name in zip(PORTS, NAMES):
    s = http_get(port, "/status") or {}
    h = s.get("chain_height", 0)
    st = s.get("block_store_size", 0)
    print(f"    {name}: chain={h} blocks, store={st} blocks, orphaned={st - h}")

print(f"""
    Disagreement: {dis}/{total} rounds ({100*dis//max(total,1)}%)
    Agreement:    {agr}/{total} rounds ({100*agr//max(total,1)}%)""")

if dis > 0:
    result_fail("Consensus CANNOT keep up with mining rate")
    print(f"    Mining: 1 block / {MINE_INTERVAL}s per node")
    print(f"    Consensus: 1 round / 5s")
    print(f"    Orphaned blocks = wasted work that overloads the system")
else:
    result_pass("Consensus kept up (unexpected)")

input("\n  [Enter] Summary and exit →")

# =============================================================================
# Summary
# =============================================================================

banner("SUMMARY")

print("""
  Algorithm: longest-chain + tip-hash tie-breaking
  ─────────────────────────────────────────────────
  Part 1:  Without consensus → ledgers diverge
  Part 2:  Equal-height tie  → tie-break resolves it     ✓
  Part 3:  Longer chain      → consensus adopts it       ✓
  Part 4:  Rapid mining      → consensus can't keep up   ✗

  The algorithm works when given time, but fails when
  blocks are produced faster than the round interval.
""")

print(f"  Nodes still live for inspection:")
for i, port in enumerate(PORTS):
    print(f"    http://127.0.0.1:{port}/status")

input("\n  [Enter] Stop all nodes and exit →")
stop_all()
