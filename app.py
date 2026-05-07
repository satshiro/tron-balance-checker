import os
import json
import base58
import urllib.request
import urllib.error
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

TRONGRID_BASE = "https://api.trongrid.io"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
NEUTRAL_ADDR  = "TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax"

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def validate_address(address):
    try:
        decoded = base58.b58decode_check(address)
        return len(decoded) == 21 and decoded[0] == 0x41
    except Exception:
        return False


def base58_to_param(address):
    """ABI-encode Tron address as 32-byte hex parameter."""
    decoded = base58.b58decode_check(address)
    return decoded[1:].hex().zfill(64)


def hex_to_base58(hex_addr):
    """Convert 40-char hex (without 41) to Tron base58 address."""
    try:
        full = "41" + hex_addr[-40:]
        return base58.b58encode_check(bytes.fromhex(full)).decode()
    except Exception:
        return ""


# ── Method 1: contract call ──────────────────────────────────────────────────

def check_via_contract(address):
    """Call isBlacklisted(address) on USDT contract. Returns True/False/None."""
    try:
        param = base58_to_param(address)
        payload = {
            "owner_address": NEUTRAL_ADDR,
            "contract_address": USDT_CONTRACT,
            "function_selector": "isBlacklisted(address)",
            "parameter": param,
            "call_value": 0,
            "fee_limit": 1000000,
            "visible": True
        }
        result = post_json(f"{TRONGRID_BASE}/wallet/triggerconstantcontract", payload)
        constant = result.get("constant_result", [])
        if constant and len(constant[0].strip()) == 64:
            return int(constant[0].strip(), 16) != 0
        return None
    except Exception:
        return None


# ── Method 2: scan AddedBlackList events with address filter ─────────────────

def check_via_events(address):
    """
    Query TronGrid events for USDT contract filtered by the specific address.
    TronGrid supports filtering by topic (indexed param = the blacklisted address).
    Returns True/False/None.
    """
    try:
        # Convert address to 32-byte hex topic for event filter
        addr_hex_32 = base58_to_param(address)

        # Paginate through AddedBlackList events searching for this address
        fingerprint = None
        added = False
        removed = False

        for _ in range(10):  # max 10 pages
            url = (
                f"{TRONGRID_BASE}/v1/contracts/{USDT_CONTRACT}/events"
                f"?event_name=AddedBlackList&only_confirmed=true&limit=200"
            )
            if fingerprint:
                url += f"&fingerprint={fingerprint}"

            data = fetch(url)
            events = data.get("data", [])

            for ev in events:
                res = ev.get("result", {})
                user = (res.get("_user") or res.get("user") or
                        res.get("0") or "").lower()
                if user == address.lower():
                    added = True
                    break

            if added:
                break

            meta = data.get("meta", {})
            fingerprint = meta.get("fingerprint")
            if not fingerprint or not events:
                break

        if not added:
            return False

        # Check if later removed
        fingerprint = None
        for _ in range(5):
            url = (
                f"{TRONGRID_BASE}/v1/contracts/{USDT_CONTRACT}/events"
                f"?event_name=RemovedBlackList&only_confirmed=true&limit=200"
            )
            if fingerprint:
                url += f"&fingerprint={fingerprint}"

            data = fetch(url)
            for ev in data.get("data", []):
                res = ev.get("result", {})
                user = (res.get("_user") or res.get("user") or
                        res.get("0") or "").lower()
                if user == address.lower():
                    removed = True
                    break

            if removed:
                break
            meta = data.get("meta", {})
            fingerprint = meta.get("fingerprint")
            if not fingerprint:
                break

        return added and not removed

    except Exception:
        return None


# ── Method 3: scan USDT TRC20 transactions for this address ─────────────────

def check_via_trc20_txns(address):
    """
    Look for incoming TRC20 transfers with type 'addBlackList' in the
    transaction list of the USDT contract involving this address.
    Returns True/False/None.
    """
    try:
        url = (
            f"{TRONGRID_BASE}/v1/accounts/{address}/transactions/trc20"
            f"?contract_address={USDT_CONTRACT}&only_confirmed=true&limit=200"
        )
        data = fetch(url)
        for tx in data.get("data", []):
            # Some responses include type field
            if tx.get("type", "").lower() in ("addblacklist", "add_black_list"):
                return True
        return None
    except Exception:
        return None


def is_blacklisted(address):
    """
    Try methods in order. Contract call is most reliable when it works.
    Events scan is the ground-truth fallback.
    """
    # Method 1: contract call
    result = check_via_contract(address)
    if result is True:
        return True
    if result is False:
        # Contract returned False — but double-check with events for recent freezes
        ev_result = check_via_events(address)
        if ev_result is True:
            return True
        return False

    # Method 1 failed — use events
    ev_result = check_via_events(address)
    if ev_result is not None:
        return ev_result

    # Last resort
    txn_result = check_via_trc20_txns(address)
    return bool(txn_result)


def get_usdt_balance(address):
    try:
        url = f"{TRONGRID_BASE}/v1/accounts/{address}"
        data = fetch(url)
        accounts = data.get("data", [])
        if not accounts:
            return 0.0
        for item in accounts[0].get("trc20", []):
            if USDT_CONTRACT in item:
                return int(item[USDT_CONTRACT]) / 1_000_000
        return 0.0
    except Exception:
        return 0.0


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/check", methods=["POST"])
def check():
    body = request.get_json()
    addresses = body.get("addresses", [])

    if not addresses:
        return jsonify({"error": "Nessun indirizzo fornito."}), 400
    if len(addresses) > 20:
        return jsonify({"error": "Massimo 20 indirizzi per volta."}), 400

    results = []
    for addr in addresses:
        addr = addr.strip()
        if not addr:
            continue
        if not validate_address(addr):
            results.append({"address": addr, "valid": False})
            continue

        blacklisted = is_blacklisted(addr)
        balance = None if blacklisted else get_usdt_balance(addr)
        results.append({
            "address": addr,
            "valid": True,
            "blacklisted": blacklisted,
            "balance": balance
        })

    return jsonify({"results": results})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
