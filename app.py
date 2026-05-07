import os
import json
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


def validate_address(address):
    try:
        url = "{}/wallet/validateaddress".format(TRONGRID_BASE)
        result = post_json(url, {"address": address})
        return result.get("result", False)
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
    try:
        val_url = "{}/wallet/validateaddress".format(TRONGRID_BASE)
        val = post_json(val_url, {"address": address})
        if not val.get("result"):
            return False

        addr_hex = val.get("extra", {}).get("address_hex", "")
        param = addr_hex[2:].zfill(64) if addr_hex.startswith("41") else addr_hex.zfill(64)

        url = "{}/wallet/triggerconstantcontract".format(TRONGRID_BASE)
        payload = {
            "owner_address": address,
            "contract_address": USDT_CONTRACT,
            "function_selector": "isBlacklisted(address)",
            "parameter": param,
            "call_value": 0,
            "fee_limit": 1000000
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
