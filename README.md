# ITI0215_26 — Hajutatud Ledger konsensusega

## Käivitamine

Python 3.9+ peab olema installitud, muid sõltuvusi pole.

Ühe sõlme käivitamine:
```bash
python node.py <port>
python node.py <port> <ip>
python node.py <port> <ip> <config_file>
```

Mitu sõlme samal masinal (eri terminalides):
```bash
python node.py 5001
python node.py 5002
python node.py 5003
```

Mitme masinaga käivitamine (IP tuleb ette anda):
```bash
python node.py 5001 192.168.1.10
```

### Demoskriptid

Divergentsi ja konsensuse demo (soovituslik):
```bash
python demo.py
```

Vana põhiline võrgutesti skript:
```bash
python test_network_single_machine.py
```

---

## Arhitektuur

### Moodulid

| Fail | Eesmärk |
|------|---------|
| `node.py` | Käivituspunkt. Alustab HTTP serveri ja taustaahela. |
| `server.py` | HTTP serveris kõik endpointid. |
| `state.py` | Jagatud globaalne olek: `block_store`, `blocks` (kanooniline kett), `transactions`, `peers`. |
| `consensus.py` | Pikim-kett konsensuse algoritm. |
| `discovery.py` | BFS peer-avastamine ja plokkide sünkimine. |
| `broadcast.py` | Flood-levitamine kõigile teadaolevatele peers'idele. |
| `client.py` | HTTP GET/POST abifunktsioonid. |
| `config.py` | `network.json` laadimine algpeerside jaoks. |

### Oleku struktuur

```
state.block_store   — kõik teadaolevad plokid, sh kahvlid
                      hash -> {content, prev_hash, height}

state.blocks        — kanooniline kett (genesis -> tipp)
                      järjestatud dict, ainult peakett

state.transactions  — mempool: kinnitamata tehingud
state.peers         — teadaolevad peer-aadressid
```

Kui saabub uus plokk mis loob pikema keti kui praegune, kutsutakse `state.add_block()` mis ehitab `state.blocks` ümber.

---

## Konsensuse algoritm

Kasutatakse **pikim-kett võidab** (Bitcoin-stiil):

1. Igal plokil on `prev_hash` ja arvutatud `height` (kaugus genesisest).
2. Iga 10 sekundi järel küsib iga sõlm kõigilt peers'idelt: `GET /chainlen`.
3. Kui peers'il on **rangelt pikem** kett:
   - Laadib alla tema ploki hashid (`GET /getblocks`)
   - Laadib puuduvad plokid (`GET /getdata/<hash>`)
   - Võtab keti üle (`state.adopt_chain()`)

**Töötab kui:** ühe partitsiooni kett on pikem teisest — lühem asendatakse.

**Ei tööta kui:** kaks partitsiooni on täpselt sama pikkusega — kumbki ei laadi teise ketti üle. See on demonstreeritav tõrkejuhtum.

---

## Protokoll

Kõik sõlmed suhtlevad HTTP kaudu. Aadress on kujul `ip:port`, näiteks `127.0.0.1:5001`.

---

### GET /addr

Tagastab kõik teadaolevad peers'id.

```
GET http://127.0.0.1:5001/addr
```
```json
["127.0.0.1:5002", "127.0.0.1:5003"]
```

---

### GET /chainlen

Tagastab kanonilise keti pikkuse (plokiarv).

```
GET http://127.0.0.1:5001/chainlen
```
```json
2
```

---

### GET /status

Tagastab debug-hetktõmmise: keti kõrgus, block_store suurus, mempool, peers, keti hashid.

```
GET http://127.0.0.1:5001/status
```
```json
{
  "port": 5001,
  "chain_height": 2,
  "block_store_size": 3,
  "mempool_size": 0,
  "peers": ["127.0.0.1:5002"],
  "chain_tip": "eb54d8eb...",
  "chain": ["7525cf5a...", "eb54d8eb..."]
}
```

---

### GET /getblocks

Tagastab kanonilise keti ploki hashid järjekorras (genesis → tipp).

```
GET http://127.0.0.1:5001/getblocks
```
```json
["a3f1c2d4...", "b9e4d1f2..."]
```

---

### GET /getblocks/\<hash\>

Tagastab keti hashid alates antud hashist (kasutatakse inkrementaalseks sünkimiseks).

```
GET http://127.0.0.1:5001/getblocks/a3f1c2d4...
```
```json
["b9e4d1f2..."]
```

---

### GET /getdata/\<hash\>

Tagastab ühe ploki sisu (otsitakse `block_store`'ist, sh kahvliplokid).

```
GET http://127.0.0.1:5001/getdata/b9e4d1f2...
```
```json
{
  "hash": "b9e4d1f2...",
  "content": {
    "content": {
      "transactions": [{"sender": "Jaan", "receiver": "Ants", "amount": 0.0001}],
      "timestamp": 1708000000
    },
    "prev_hash": "a3f1c2d4...",
    "height": 2
  }
}
```

---

### POST /inv

Uue tehingu vastuvõtmine. Salvestatakse mempoolile ja saadetakse flood-meetodil edasi. Duplikaadid ignoreeritakse.

```
POST http://127.0.0.1:5001/inv
Content-Type: application/json

{"hash": "abc123...", "content": {"sender": "Jaan", "receiver": "Ants", "amount": 0.0001}}
```

Hash: `sha256(json.dumps(content, sort_keys=True))` hex-kujul.

| Vastus | Tähendus |
|--------|----------|
| `1` | Vastu võetud |
| `{"status": "already known"}` | Juba teada |
| `{"errcode": 3, ...}` | Hashi mittevastavus |

---

### POST /block

Uue ploki vastuvõtmine. Kontrollitakse hash-integriteet, vaadatakse et kõik tehingud oleksid mempoolil, salvestatakse `block_store`'i, uuendatakse kanoonilist ketti kui plokk loob pikema haru.

```
POST http://127.0.0.1:5001/block
Content-Type: application/json

{
  "hash": "ff291a...",
  "prev_hash": "a3f1c2d4...",
  "content": {
    "transactions": [{"sender": "Jaan", "receiver": "Ants", "amount": 0.0001}],
    "timestamp": 1708000000
  }
}
```

Hash: `sha256(json.dumps({"content": content, "prev_hash": prev_hash}, sort_keys=True))`

Genesis-plokk kasutab `prev_hash = "0" * 64`.

| Vastus | Tähendus |
|--------|----------|
| `1` | Vastu võetud |
| `{"status": "already known"}` | Juba teada |
| `{"errcode": 3, ...}` | Hashi mittevastavus |
| `{"errcode": 4, ...}` | Tehing puudub mempoolist |

---

### POST /addpeer

Lisab uue peer-aadressi käituse ajal (ilma sõlme taaskäivitamiseta).

```
POST http://127.0.0.1:5001/addpeer
Content-Type: application/json

{"addr": "127.0.0.1:5002"}
```
```json
{"status": "ok", "peers": ["127.0.0.1:5002"]}
```

---

## Võrgu topoloogia

```
5001 (bootstrap)
  -- 5002
  -- 5003
  -- 5004
  -- 5005
```

Iga sõlm laeb algul peers'id `network.json` failist. Käivitumisel teeb BFS otsingu läbi `/addr` ja leiab kõik aktiivsed sõlmed. Avastamine + konsensuse ring korduvad iga 10 sekundi järel taustal.

---

## Demo tulemused

### demo.py

**Osa 1 — Divergentsi loomine**

Kolm sõlme käivitati täielikus isolatsioonis (peers puuduvad). Igale saadeti unikaalne tehing ja igaüks kaevandas oma ploki genesis-ploki peale.

| Sõlm | Ledger | Tehing |
|------|--------|--------|
| S1 | [B1] | Alice -> Bob, 10 |
| S2 | [B2] | Bob -> Carol, 20 |
| S3 | [B3] | Carol -> Alice, 30 |

Tulemus: kõigil height=1 aga erinevad tip-hashid — ledgerid on erinevad.

**Osa 2 — Võrdse pikkusega kahvel (konsensus EI tööta)**

Pärast sõlmede ühendamist (`/addpeer`) jäid kõik kolm ketti height=1. Konsensuse algoritm nõuab **rangelt** pikemat ketti — viik ei lahendu. Kõigil `store=3` (laadisid üksteise plokid alla), aga kanooniline kett jäi enda oma.

**Osa 3 — Pikem kett võidab (konsensus TÖÖTAB)**

S1 kaevanadas teise ploki (height=2). Järgmisel konsensuseringil:
- S2 ja S3 küsisid `/chainlen` — S1 vastas 2, nemad olid 1
- Laadisid S1 plokid alla `/getdata` kaudu
- Võtsid S1 keti üle (`adopt_chain`)

Lõpptulemus: kõik kolm sõlme leppisid kokku täpselt samas ketis.

### Piirangud

- **Võrdse pikkuse viik:** kui kaks ketti on täpselt sama pikad, eelistab konsensusalgoritm väiksema tip-hashiga ketti (deterministlik, ei nõua lisasuhtlust). See on implementeeritud `consensus.py` funktsioonides `sync_from_peer` ja `state.adopt_chain(allow_equal=True)`.
- **Plokkide saatmine peers'idele:** `/block` endpoint nõuab et tehingud oleksid mempoolil — sünkimisel kasutatakse seetõttu otse `/getdata` (mempooli kontroll möödutakse).
