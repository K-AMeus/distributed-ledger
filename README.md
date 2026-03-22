# ITI0215_26 — Hajusandmebaas / P2P sõlm

## Käivitamine

Python 3.9+ peab olema installitud, muid sõltuvusi pole.

Ühe sõlme käivitamine:
```bash
python node.py <port>
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

Testiskripti käivitamine:
```bash
python test_network.py
```

---

## Protokoll

Kõik sõlmed suhtlevad HTTP kaudu. Aadress on kujul `ip:port`, näiteks `127.0.0.1:5001`.

---

### GET /addr

Tagastab kõik teadaolevad sõlmed.

Päring:
```
GET http://127.0.0.1:5001/addr
```

Vastus:
```json
["127.0.0.1:5002", "127.0.0.1:5003"]
```

---

### GET /getblocks

Tagastab kõik ploki hashid järjekorras.

Päring:
```
GET http://127.0.0.1:5001/getblocks
```

Vastus:
```json
["a3f1c2d4...", "b9e4d1f2..."]
```

---

### GET /getblocks/\<hash\>

Tagastab ploki hashid alates antud hashist (kasutatakse sünkimiseks).

Päring:
```
GET http://127.0.0.1:5001/getblocks/a3f1c2d4...
```

Vastus:
```json
["b9e4d1f2..."]
```

Kui hashi ei leita, tagastatakse kõik hashid.

---

### GET /getdata/\<hash\>

Tagastab ühe ploki sisu.

Päring:
```
GET http://127.0.0.1:5001/getdata/b9e4d1f2...
```

Vastus (leitud):
```json
{
  "hash": "b9e4d1f2...",
  "content": {
    "content": {
      "transactions": [
        {"sender": "Jaan", "receiver": "Ants", "amount": 0.0001}
      ],
      "timestamp": 1708000000
    },
    "prev_hash": "a3f1c2d4..."
  }
}
```

Vastus (ei leitud):
```json
{"error": "block not found"}
```

---

### POST /inv

Uue tehingu vastuvõtmine. Salvestatakse mempoolile ja saadetakse kõigile teistele sõlmedele edasi. Duplikaadid ignoreeritakse.

Päring:
```
POST http://127.0.0.1:5001/inv
Content-Type: application/json

{
  "hash": "abc123...",
  "content": {"sender": "Jaan", "receiver": "Ants", "amount": 0.0001}
}
```

Hash arvutatakse nii: `sha256(json.dumps(content, sort_keys=True))` hex-kujul.

Vastus (vastu võetud):
```json
1
```

Vastus (juba olemas):
```json
{"status": "already known"}
```

Vastus (hash ei klapi):
```json
{"errcode": 3, "errmsg": "hash mismatch, expected <õige_hash>"}
```

---

### POST /block

Uue ploki vastuvõtmine. Kontrollitakse hashchain'i, vaadatakse et kõik tehingud oleksid mempoolil olemas, salvestatakse plokk, eemaldatakse kinnitatud tehingud mempoolist ja saadetakse edasi.

Päring:
```
POST http://127.0.0.1:5001/block
Content-Type: application/json

{
  "hash": "ff291a...",
  "prev_hash": "a3f1c2d4...",
  "content": {
    "transactions": [
      {"sender": "Jaan", "receiver": "Ants", "amount": 0.0001}
    ],
    "timestamp": 1708000000
  }
}
```

Hash arvutatakse:
```python
sha256(json.dumps({"content": content, "prev_hash": prev_hash}, sort_keys=True))
```

Esimene plokk (genesis) kasutab `prev_hash = "0" * 64`.

Vastus (vastu võetud):
```json
1
```

Vastus (juba olemas):
```json
{"errcode": 1, "errmsg": "already known"}
```

Vastus (tehing puudub mempoolist):
```json
{"errcode": 4, "errmsg": "unknown transaction ab12cd34"}
```

Vastus (hash ei klapi):
```json
{"errcode": 3, "errmsg": "hash mismatch, expected <õige_hash>"}
```

---

## Võrgu topoloogia

```
5001 (bootstrap)
  ├── 5002
  ├── 5003
  ├── 5004
  └── 5005
```

Iga sõlm laeb algul peers'id `network.json` failist. Käivitumisel teeb BFS otsingu läbi `/addr` ja leiab kõik aktiivsed sõlmed. Avastamine kordub iga 10 sekundi järel taustal. Uus sõlm, mis võrku liitub, leiab automaatselt kõik teised sõlmed ja sünkib plokid.

Blokkide ja tehingute edastamine toimub flood-meetodil — iga sõlm saadab saadud info kõigile teistele edasi, duplikaadid filtreeritakse hashiga.

---

## Katseosa

### Metoodika

`test_network.py` käivitab automaatse stsenaariumi:

1. Käivitatakse 5 sõlme (pordid 5001–5005)
2. Saadetakse 10 tehingut sõlmele 5001
3. Tehingud pannakse plokki ja saadetakse — kontrollitakse propagatsiooni
4. Tapetakse sõlmed 5003 ja 5004 — vaadatakse kas ülejäänud töötavad edasi
5. Saadetakse tehingud ja plokk kuni kahte sõlme on maas
6. Lisatakse 3 uut sõlme (5010–5012) — vaadatakse kas nad süngivad plokid
7. Stressitest: 50 tehingut laiali kõigile sõlmedele, pannakse plokki

### Tulemused

| Test | Tulemus |
|------|---------|
| Peer discovery (5 sõlme) | Kõik leitud ~2s jooksul |
| Tehingute laialisaatmine | Jõudis kõigini koheselt |
| Ploki propageerimine | Kõik sünkisid ~2s jooksul |
| 2 sõlme tapmine | Ülejäänud 3 töötasid edasi |
| 3 uue sõlme lisamine | Sünkisid kõik plokid ~10s jooksul |
| Stressitest (50 tehingut) | ~1400–1800 tehingut/sek |
| Maksimaalselt testitud sõlmi | 8 korraga |

### Mitme masinaga katse

Testitud kahel masinal samas võrgus:
- Masin A: 192.168.1.10, sõlmed pordil 5001 ja 5002
- Masin B: 192.168.1.15, sõlm pordil 5001

Masin B käivitati:
```bash
python node.py 5001 192.168.1.15
```

Masin B `network.json` osutas masin A bootstrap sõlmele (`192.168.1.10:5001`).

Tulemus: Masin B sõlm leidis masin A sõlmed ~10s jooksul ja sünkis kõik plokid edukalt.
