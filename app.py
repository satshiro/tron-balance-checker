import os
import json
import urllib.request
import urllib.error
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# Tron API
TRONGRID_BASE = "https://api.trongrid.io"

# USDT TRC20 contract address
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

# Tether blacklist function selector: isBlacklisted(address) = 0xfe575a87
BLACKLIST_SELECTOR = "fe575a87"


def fetch(url, headers=None):
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception("HTTP {}: {}".format(e.code, e.reason))
    except urllib.error.URLError as e:
        raise Exception("Rete: {}".format(e.reason))


def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception("HTTP {}: {}".format(e.code, e.reason))
    except urllib.error.URLError as e:
        raise Exception("Rete: {}".format(e.reason))


def address_to_hex(base58_addr):
    """Convert Tron base58 address to hex for contract calls via TronGrid."""
    url = "{}/wallet/validateaddress".format(TRONGRID_BASE)
    result = post_json(url, {"address": base58_addr})
    if not result.get("result"):
        raise Exception("Indirizzo Tron non valido: {}".format(base58_addr))
    # Use triggersmartcontract which accepts base58 directly
    return base58_addr


def get_usdt_balance(address):
    """Get USDT TRC20 balance for address."""
    url = "{}/v1/accounts/{}/tokens?asset_id={}".format(
        TRONGRID_BASE, address, USDT_CONTRACT
    )
    try:
        data = fetch(url)
        tokens = data.get("data", [])
        for token in tokens:
            if token.get("token_id") == USDT_CONTRACT or token.get("key") == USDT_CONTRACT:
                balance = int(token.get("balance", 0))
                return balance / 1_000_000  # USDT has 6 decimals
        # Try alternative endpoint
        url2 = "{}/v1/accounts/{}".format(TRONGRID_BASE, address)
        data2 = fetch(url2)
        accounts = data2.get("data", [])
        if accounts:
            trc20 = accounts[0].get("trc20", [])
            for item in trc20:
                if USDT_CONTRACT in item:
                    return int(item[USDT_CONTRACT]) / 1_000_000
        return 0.0
    except Exception:
        return 0.0


def is_blacklisted(address):
    """Check if address is blacklisted on USDT TRC20 contract."""
    try:
        # Pad address for ABI encoding - need hex form
        # First get hex address from TronGrid
        val_url = "{}/wallet/validateaddress".format(TRONGRID_BASE)
        val = post_json(val_url, {"address": address})
        if not val.get("result"):
            return False

        # triggersmartcontract to call isBlacklisted(address)
        url = "{}/wallet/triggersmartcontract".format(TRONGRID_BASE)
        payload = {
            "owner_address": address,
            "contract_address": USDT_CONTRACT,
            "function_selector": "isBlacklisted(address)",
            "parameter": val.get("extra", {}).get("address_hex", "").replace("41", "", 1).zfill(64),
            "call_value": 0,
            "fee_limit": 1000000
        }

        # Alternative: use trongrid trigger constant contract
        url2 = "{}/wallet/triggerconstantcontract".format(TRONGRID_BASE)
        result = post_json(url2, payload)

        constant_result = result.get("constant_result", [])
        if constant_result:
            hex_result = constant_result[0]
            # Last byte is the boolean result
            return hex_result.strip("0") == "1" or hex_result.endswith("1")
        return False
    except Exception:
        return False


def validate_address(address):
    """Validate a Tron address."""
    try:
        url = "{}/wallet/validateaddress".format(TRONGRID_BASE)
        result = post_json(url, {"address": address})
        return result.get("result", False)
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
            results.append({
                "address": addr,
                "valid": False,
                "error": "Indirizzo non valido"
            })
            continue

        blacklisted = is_blacklisted(addr)

        if blacklisted:
            results.append({
                "address": addr,
                "valid": True,
                "blacklisted": True,
                "balance": None
            })
        else:
            balance = get_usdt_balance(addr)
            results.append({
                "address": addr,
                "valid": True,
                "blacklisted": False,
                "balance": balance
            })

    return jsonify({"results": results})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
