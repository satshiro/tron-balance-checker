import os
import json
import base58
import urllib.request
import urllib.error
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

TRONGRID_BASE = "https://api.trongrid.io"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
# Neutral owner address for constant calls
NEUTRAL_ADDR = "TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax"


def fetch(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def validate_address(address):
    """Validate Tron base58check address."""
    try:
        decoded = base58.b58decode_check(address)
        return len(decoded) == 21 and decoded[0] == 0x41
    except Exception:
        return False


def base58_to_param(address):
    """Convert Tron base58 address to 32-byte ABI-encoded hex parameter."""
    decoded = base58.b58decode_check(address)  # 21 bytes: 0x41 + 20 bytes
    addr_20 = decoded[1:]  # 20 bytes
    return addr_20.hex().zfill(64)  # left-pad to 32 bytes = 64 hex chars


def is_blacklisted_contract(address):
    """
    Primary method: call isBlacklisted(address) on USDT contract.
    Returns True/False/None (None = call failed).
    """
    try:
        param = base58_to_param(address)
        url = "{}/wallet/triggerconstantcontract".format(TRONGRID_BASE)
        payload = {
            "owner_address": NEUTRAL_ADDR,
            "contract_address": USDT_CONTRACT,
            "function_selector": "isBlacklisted(address)",
            "parameter": param,
            "call_value": 0,
            "fee_limit": 1000000,
            "visible": True
        }
        result = post_json(url, payload)

        # Check for contract execution error
        if not result.get("result", {}).get("result", True) is False:
            constant = result.get("constant_result", [])
            if constant and len(constant) > 0:
                hex_val = constant[0].strip()
                if len(hex_val) == 64:
                    return int(hex_val, 16) != 0
        return None
    except Exception:
        return None


def is_blacklisted_events(address):
    """
    Fallback method: check AddedBlackList/RemovedBlackList events on TronGrid.
    Returns True/False/None.
    """
    try:
        url = (
            "{}/v1/contracts/{}/events"
            "?event_name=AddedBlackList&only_confirmed=true&limit=200"
        ).format(TRONGRID_BASE, USDT_CONTRACT)

        data = fetch(url)
        events = data.get("data", [])

        added = set()
        removed = set()

        for ev in events:
            result_data = ev.get("result", {})
            user = result_data.get("_user") or result_data.get("user") or result_data.get("0")
            if user:
                added.add(user.lower())

        # Check RemovedBlackList
        url2 = (
            "{}/v1/contracts/{}/events"
            "?event_name=RemovedBlackList&only_confirmed=true&limit=200"
        ).format(TRONGRID_BASE, USDT_CONTRACT)
        data2 = fetch(url2)
        for ev in data2.get("data", []):
            result_data = ev.get("result", {})
            user = result_data.get("_user") or result_data.get("user") or result_data.get("0")
            if user:
                removed.add(user.lower())

        addr_lower = address.lower()
        if addr_lower in added and addr_lower not in removed:
            return True
        if addr_lower in added:
            return True  # conservative: if ever added, flag it
        return False
    except Exception:
        return None


def is_blacklisted(address):
    """Try contract call first, fall back to events."""
    result = is_blacklisted_contract(address)
    if result is not None:
        return result
    # Fallback
    result = is_blacklisted_events(address)
    return result if result is not None else False


def get_usdt_balance(address):
    try:
        url = "{}/v1/accounts/{}".format(TRONGRID_BASE, address)
        data = fetch(url)
        accounts = data.get("data", [])
        if not accounts:
            return 0.0
        trc20_list = accounts[0].get("trc20", [])
        for item in trc20_list:
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
