<div align="center">

# 🦊 KhmerFox

**A compact, Cambodia-focused Google Maps scraper powered by Camoufox.**

Built for Khmer & English business listings. Stealth browser, async concurrency, and a modern web UI — all in a tiny codebase.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Camoufox](https://img.shields.io/badge/browser-Camoufox-orange)](https://camoufox.com/)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://docs.astral.sh/ruff/)

</div>

> ⚠️ **Use responsibly.** KhmerFox is intended for personal research, data you own, or publicly available listings you have permission to scrape. Always respect [Google Maps Terms of Service](https://www.google.com/intl/en/help/terms_maps.html), rate limits, and local laws. Use at your own risk.

---

## ✨ Features

| Feature | Description |
|--------|-------------|
| 🚀 **Fast Async Scraping** | Concurrent place extraction with configurable workers |
| 🦊 **Stealth Browser** | Camoufox anti-detect Firefox reduces blocking |
| 🇰🇭 **Cambodia Defaults** | Khmer query defaults, phone normalization, name splitting |
| 🌐 **Web UI** | Modern Flask dashboard with live logs, progress, dark mode, and downloads |
| 📊 **40 Output Fields** | Core + extended fields with selectable export columns |
| 📁 **Multiple Formats** | CSV (Excel-safe), JSON, Markdown, Excel (.xlsx) |
| 🌑 **Dark Mode** | Toggle between light and dark themes in the web UI |
| 🛑 **Stop Button** | Gracefully stop a running scrape from the UI |
| 🌏 **Cross-Platform** | Windows, macOS, and Linux |

---

## 📦 Installation

### Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- ~2 GB free disk space for Camoufox browser binaries

Install `uv`:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Setup

```bash
git clone <repository-url>
cd khmerfox
uv sync
python -m camoufox fetch
```

`python -m camoufox fetch` downloads the Camoufox browser binaries for your platform. Run it again after switching OS or after updating `camoufox`.

---

## 🖥️ Web UI

The easiest way to use KhmerFox:

```bash
uv run khmerfox-web
```

Open http://127.0.0.1:5000

### What you get

- **Settings panel** — query, format, max results, concurrency, proxy, field selection
- **Output field checkboxes** — choose exactly which columns to export
- **Live progress** — places found, scraped, and elapsed time
- **Live logs** — color-coded, copyable, clearable
- **Stop button** — stop a running scrape gracefully
- **Results table** — download CSV, JSON, Markdown, or Excel with one click
- **Dark / light mode** — persists in your browser

---

## 💻 Command Line

```bash
# Default query: coffee shops in Phnom Penh (Khmer)
uv run khmerfox

# English query, all formats, 8 concurrent workers
uv run khmerfox -q "Tube Coffee in Phnom Penh" --format all --concurrency 8

# Excel only, max 50 places
uv run khmerfox -q "hotels in Siem Reap" --format xlsx --max-results 50

# Headed browser with screenshots for debugging
uv run khmerfox -q "banks in Phnom Penh" --no-headless --screenshots

# Export only selected fields
uv run khmerfox -q "coffee in Phnom Penh" --fields "name,rating,reviews,address,phone,domain"
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `-q, --query` | Search query | `ហាងកាហ្វេនៅភ្នំពេញ` |
| `-t, --territory` | Territory for phone normalization | `Cambodia` |
| `--headless / --no-headless` | Run browser headless | `headless` |
| `--max-results` | Limit results (`0` = unlimited) | `0` |
| `--concurrency` | Concurrent pages (`1`–`8`) | `4` |
| `--format` | `csv`, `json`, `md`, `xlsx`, comma-separated, or `all` | `csv` |
| `--fields` | Comma-separated output fields, or `all` | core set |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `--proxy` | HTTP/SOCKS5 proxy, e.g. `http://127.0.0.1:8080` | — |
| `--screenshots` | Save debug screenshots on errors | — |
| `--session` | Session name for Camoufox state | `default` |
| `--scroll-delay` | Seconds between scrolls in result list | `0.5` |
| `--page-delay` | Seconds to wait after opening a place | `0.5` |
| `--retries` | Retries per failed place | `1` |

---

## 📋 Output Fields

### Core Fields (default)

`place_id`, `name`, `name_kh`, `name_en`, `rating`, `reviews`, `category`, `address`, `phone`, `website`, `hours`, `price_level`, `plus_code`, `latitude`, `longitude`, `maps_url`

### Extended Fields

`query`, `created_at`, `fulladdr`, `local_name`, `local_fulladdr`, `addr1`, `addr2`, `addr3`, `addr4`, `district`, `phone_number`, `international_phone_number`, `phone_numbers`, `primary_category`, `categories`, `features`, `url`, `domain`, `listing_url`, `thumbnail`, `reviews_url`, `claimed`, `fid`, `cid`, `timezone`

> **Field reliability note:** `name_kh`/`local_name` are only populated when the business name contains Khmer script. `claimed` only reports `No` when Google shows a "Claim this business" link, `Yes` when owner indicators are visible, and stays empty when the status cannot be determined. `timezone` is not exposed by Google Maps and will always be empty.

---

## 🏗️ Project Structure

```
khmerfox/
├── khmerfox/
│   ├── __init__.py
│   ├── core.py      # models, scraper, extractor, exporter, utils
│   ├── cli.py       # command-line interface
│   └── web.py       # Flask app + embedded UI
├── data/            # output files (gitignored except .gitkeep)
├── sessions/        # saved browser sessions (gitignored except .gitkeep)
├── screenshots/     # debug screenshots (gitignored except .gitkeep)
├── .env.example     # example environment variables
├── pyproject.toml   # project config
├── uv.lock          # locked dependencies
├── LICENSE          # MIT
└── README.md
```

---

## 🍎 macOS Notes

1. Install `uv` using the command above.
2. Camoufox downloads the correct browser binary automatically when you run `python -m camoufox fetch`.
3. If macOS Gatekeeper blocks the browser, remove quarantine attributes:

   ```bash
   xattr -rd com.apple.quarantine ~/.cache/uv/
   ```

4. Use `uv run khmerfox` and `uv run khmerfox-web` exactly as on other platforms.

---

## 🔒 Safe Usage & Rate Limits

- Keep `--concurrency` low (`2`–`4`) to avoid aggressive requests.
- Use `--proxy` to rotate IP addresses if you run repeated scrapes.
- Run with `--no-headless --screenshots` first to visually verify behavior.
- Do not scrape private or copyrighted data you are not authorized to access.
- Google Maps may block or CAPTCHA your IP if abused. KhmerFox provides no guarantee of uninterrupted access.

---

## 🔧 Environment Variables

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

Supported variables: `QUERY`, `TERRITORY`, `HEADLESS`, `FORMAT`, `MAX_RESULTS`, `CONCURRENCY`, `PROXY`, `SCREENSHOTS`.

> CLI flags override environment variables.

---

## 🧑‍💻 Development

```bash
# Install dev dependencies
uv sync --dev

# Lint
uv run ruff check khmerfox/
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).
