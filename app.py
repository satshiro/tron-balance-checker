import os
import json
import base58
import urllib.request
import urllib.error
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

TRONGRID_BASE = "https://api.trongrid.io"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def fetch(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def base58_to_hex(address):
    """Convert Tron base58check address to 20-byte hex (without 41 prefix)."""
    decoded = base58.b58decode_check(address)  # 21 bytes: 0x41 + 20 bytes
    return decoded[1:].hex()  # strip leading 0x41


def validate_address(address):
    try:
        decoded = base58.b58decode_check(address)
        return len(decoded) == 21 and decoded[0] == 0x41
    except Exception:
        return False


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


def is_blacklisted(address):
    """
    Call isBlacklisted(address) on USDT TRC20 contract via triggerconstantcontract.
    ABI-encode the address: 20-byte hex padded to 32 bytes (64 hex chars).
    Use visible=true so we can pass base58 addresses directly.
    """
    try:
        addr_hex_20 = base58_to_hex(address)
        param = addr_hex_20.zfill(64)  # pad to 32 bytes

        url = "{}/wallet/triggerconstantcontract".format(TRONGRID_BASE)
        payload = {
            "owner_address": "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb",  # zero-like neutral address
            "contract_address": USDT_CONTRACT,
            "function_selector": "isBlacklisted(address)",
            "parameter": param,
            "call_value": 0,
            "fee_limit": 1000000,
            "visible": True
        }
        result = post_json(url, payload)

        constant_result = result.get("constant_result", [])
        if constant_result:
            hex_val = constant_result[0].strip()
            return int(hex_val, 16) == 1
        return False
    except Exception:
        return False


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
