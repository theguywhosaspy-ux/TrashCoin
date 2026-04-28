"""
TrashCoin DePIN Validator
=========================
"""

import socket
import struct
import json
import time
import random
import hashlib
import sqlite3
import threading
import os
import logging
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from flask import Flask, send_from_directory, jsonify

# ── Config ────────────────────────────────────────────────────────────────────
MCAST_GRP  = "239.255.0.1"
MCAST_PORT = 5007
WEB_PORT   = 8080
DB_PATH    = "trashcoin.db"
KEY_PATH   = "chacha.key"

MINT_BASE      = 0.01   # base coin per trash item
MINT_JITTER    = 0.001  # random jitter multiplier
DUPLICATE_TTL  = 10     # seconds – reject replays inside this window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("validator")

# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            student_id   TEXT PRIMARY KEY,
            balance      REAL DEFAULT 0.0,
            total_trash  INTEGER DEFAULT 0,
            created_at   TEXT,
            updated_at   TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            tx_hash      TEXT PRIMARY KEY,
            student_id   TEXT,
            device       TEXT,
            location     TEXT,
            trash_count  INTEGER,
            amount       REAL,
            timestamp    TEXT,
            raw_ts       REAL,
            FOREIGN KEY (student_id) REFERENCES wallets(student_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id    TEXT PRIMARY KEY,
            location     TEXT,
            is_full      INTEGER DEFAULT 0,
            last_seen    TEXT,
            total_events INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS validation_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT,
            status       TEXT,
            detail       TEXT
        )
    """)

    conn.commit()
    conn.close()


def db_conn():
    """Thread-local SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Crypto ────────────────────────────────────────────────────────────────────

def load_key():
    if not os.path.exists(KEY_PATH):
        log.warning("No %s found – generating a new key", KEY_PATH)
        with open(KEY_PATH, "wb") as f:
            f.write(ChaCha20Poly1305.generate_key())
    with open(KEY_PATH, "rb") as f:
        return f.read()


def decrypt(payload: bytes, key: bytes) -> dict | None:
    """Decrypt a ChaCha20-Poly1305 frame → JSON dict, or None on failure."""
    try:
        chacha = ChaCha20Poly1305(key)
        nonce, ct = payload[:12], payload[12:]
        plaintext = chacha.decrypt(nonce, ct, None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        log.warning("Decrypt/parse failed: %s", exc)
        return None


# ── Validation ────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {"device", "location", "student_id", "trash_count", "full", "time_stamp"}
_recent_hashes: dict[str, float] = {} 


def _tx_hash(data: dict) -> str:
    """Deterministic hash of a payload for dedup / ledger key."""
    raw = json.dumps(data, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def validate(data: dict) -> tuple[bool, str]:
    """Return (ok, reason)."""
    # structural check
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        return False, f"missing fields: {missing}"

    # status-only heartbeat (no student)
    if data.get("student_id") is None:
        return True, "heartbeat"

    # trash_count sanity
    tc = data.get("trash_count", 0)
    if not isinstance(tc, (int, float)) or tc < 0:
        return False, f"invalid trash_count: {tc}"

    # replay / duplicate guard
    h = _tx_hash(data)
    now = time.time()
    if h in _recent_hashes and now - _recent_hashes[h] < DUPLICATE_TTL:
        return False, "duplicate"
    _recent_hashes[h] = now

    # purge stale entries
    stale = [k for k, v in _recent_hashes.items() if now - v > DUPLICATE_TTL * 2]
    for k in stale:
        del _recent_hashes[k]

    return True, "ok"


# ── Minting ───────────────────────────────────────────────────────────────────

def mint(trash_count: int) -> float:
    """Calculate TrashCoin reward."""
    if trash_count <= 0:
        return 0.0
    return round(MINT_BASE * trash_count + MINT_JITTER * random.randint(0, 100), 6)


# ── Ledger writes ─────────────────────────────────────────────────────────────

def record_transaction(data: dict, amount: float):
    """Insert/update wallet, transaction, and device tables."""
    conn = db_conn()
    c = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    sid = data["student_id"]
    tx_h = _tx_hash(data)

    # upsert wallet
    c.execute("""
        INSERT INTO wallets (student_id, balance, total_trash, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET
            balance     = balance + excluded.balance,
            total_trash = total_trash + excluded.total_trash,
            updated_at  = excluded.updated_at
    """, (sid, amount, data.get("trash_count", 0), now_iso, now_iso))

    # transaction
    c.execute("""
        INSERT OR IGNORE INTO transactions
            (tx_hash, student_id, device, location, trash_count, amount, timestamp, raw_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (tx_h, sid, data.get("device"), data.get("location"),
          data.get("trash_count", 0), amount, now_iso, data.get("time_stamp", 0)))

    conn.commit()
    conn.close()


def update_device(data: dict):
    """Track device heartbeat & full status."""
    conn = db_conn()
    c = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    dev = data.get("device", "unknown")

    c.execute("""
        INSERT INTO devices (device_id, location, is_full, last_seen, total_events)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(device_id) DO UPDATE SET
            location     = excluded.location,
            is_full      = excluded.is_full,
            last_seen    = excluded.last_seen,
            total_events = total_events + 1
    """, (dev, data.get("location"), int(data.get("full", False)), now_iso))

    conn.commit()
    conn.close()


def log_validation(status: str, detail: str):
    conn = db_conn()
    conn.execute(
        "INSERT INTO validation_log (timestamp, status, detail) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), status, detail),
    )
    conn.commit()
    conn.close()


# ── UDP listener thread ──────────────────────────────────────────────────────

def udp_listener(key: bytes):
    """Blocking loop – run in a daemon thread."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", MCAST_PORT))
    mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    log.info("UDP listener up on %s:%s", MCAST_GRP, MCAST_PORT)

    while True:
        try:
            raw, addr = sock.recvfrom(4096)
            data = decrypt(raw, key)
            if data is None:
                log_validation("REJECT", f"decrypt failure from {addr}")
                continue

            ok, reason = validate(data)
            update_device(data)

            if not ok:
                log.warning("REJECTED %s – %s", addr, reason)
                log_validation("REJECT", f"{addr}: {reason}")
                continue

            if reason == "heartbeat":
                log.info("HEARTBEAT from %s  device=%s  full=%s",
                         addr, data.get("device"), data.get("full"))
                log_validation("HEARTBEAT", json.dumps(data))
                continue

            amount = mint(data.get("trash_count", 0))
            record_transaction(data, amount)
            log.info(
                "VALIDATED  student=%s  trash=%d  minted=%.6f TC  dev=%s",
                data["student_id"], data["trash_count"], amount, data["device"],
            )
            log_validation("VALID", f"student={data['student_id']} amount={amount}")

        except Exception as exc:
            log.error("Listener error: %s", exc)


# ── Flask API + dashboard ────────────────────────────────────────────────────

app = Flask(__name__, static_folder=".")


@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")


@app.route("/api/wallets")
def api_wallets():
    conn = db_conn()
    rows = conn.execute(
        "SELECT student_id, balance, total_trash, created_at, updated_at "
        "FROM wallets ORDER BY balance DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/transactions")
def api_transactions():
    conn = db_conn()
    rows = conn.execute(
        "SELECT tx_hash, student_id, device, location, trash_count, amount, timestamp "
        "FROM transactions ORDER BY timestamp DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/devices")
def api_devices():
    conn = db_conn()
    rows = conn.execute(
        "SELECT device_id, location, is_full, last_seen, total_events "
        "FROM devices ORDER BY last_seen DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/stats")
def api_stats():
    conn = db_conn()
    total_wallets   = conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]
    total_minted    = conn.execute("SELECT COALESCE(SUM(balance),0) FROM wallets").fetchone()[0]
    total_trash     = conn.execute("SELECT COALESCE(SUM(total_trash),0) FROM wallets").fetchone()[0]
    total_txns      = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    total_devices   = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    devices_full    = conn.execute("SELECT COUNT(*) FROM devices WHERE is_full=1").fetchone()[0]

    recent = conn.execute(
        "SELECT timestamp, status, detail FROM validation_log "
        "ORDER BY id DESC LIMIT 30"
    ).fetchall()
    conn.close()
    return jsonify({
        "total_wallets": total_wallets,
        "total_minted": round(total_minted, 6),
        "total_trash": total_trash,
        "total_transactions": total_txns,
        "total_devices": total_devices,
        "devices_full": devices_full,
        "recent_validations": [dict(r) for r in recent],
    })


@app.route("/api/wallet/<student_id>")
def api_wallet_detail(student_id):
    conn = db_conn()
    wallet = conn.execute(
        "SELECT * FROM wallets WHERE student_id=?", (student_id,)
    ).fetchone()
    if not wallet:
        conn.close()
        return jsonify({"error": "not found"}), 404
    txns = conn.execute(
        "SELECT * FROM transactions WHERE student_id=? ORDER BY timestamp DESC",
        (student_id,),
    ).fetchall()
    conn.close()
    return jsonify({"wallet": dict(wallet), "transactions": [dict(t) for t in txns]})


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    key = load_key()
    log.info("Validator starting …")

    # start UDP listener in background
    t = threading.Thread(target=udp_listener, args=(key,), daemon=True)
    t.start()

    # start web dashboard
    log.info("Dashboard → http://0.0.0.0:%d", WEB_PORT)
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False)