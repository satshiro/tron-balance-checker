# Tron USDT Checker

A web app to check if Tron wallet addresses are blacklisted by Tether, and display their current USDT TRC20 balance.

Built with Python + Flask. No API key required.

---

## Features

- Paste up to **20 Tron addresses** at once (one per line)
- For each wallet:
  - 🔴 **Blacklisted** — flagged by Tether's USDT contract
  - ✅ **Clean** — not blacklisted, shows current USDT balance
  - ⚠️ **Invalid** — not a valid Tron address
- Summary panel with total USDT across clean wallets

---

## How it works

1. Validates each address via TronGrid API
2. Calls the USDT TRC20 contract (`isBlacklisted`) to check blacklist status
3. If clean, fetches the current USDT balance

USDT Contract: `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`

---

## Deploy on Railway (free, no credit card)

1. Fork or upload this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Set these in **Settings**:
   - **Start Command:** `gunicorn app:app`
   - **Build Command:** `pip install -r requirements.txt`
4. Go to **Settings → Networking → Generate Domain**
   - Set port to `8080`
5. Done — your app is live

---

## Run locally

```bash
pip install -r requirements.txt
python3 app.py
```

Then open [http://localhost:5000](http://localhost:5000)

---

## Project structure

```
tron-checker/
├── app.py              # Flask backend + TronGrid API calls
├── templates/
│   └── index.html      # Frontend UI
├── requirements.txt
└── README.md
```

---

## API used

- [TronGrid](https://www.trongrid.io/) — public Tron node API, no key needed

---

## License

MIT
