# Agent Notes for KhmerFox

## Project

KhmerFox is a compact, Cambodia-focused Google Maps scraper built with Python, Camoufox (stealth Firefox), and Flask.

- **Package**: `khmerfox/`
- **Entry points**: `khmerfox` (CLI), `khmerfox-web` (Flask UI)
- **Python**: 3.11+
- **Package manager**: `uv`

## Build & Run

```bash
uv sync
python -m camoufox fetch          # download browser binaries
uv run khmerfox -q "coffee in Phnom Penh"
uv run khmerfox-web               # http://127.0.0.1:5000
```

## Lint

```bash
uv sync --dev
uv run ruff check khmerfox/
```

## Code Style

- Single-file compact design:
  - `core.py` — all scraper logic (models, browser pool, extraction, export)
  - `cli.py` — argument parsing and CLI runner
  - `web.py` — Flask app with embedded HTML/CSS/JS
- Use `pathlib.Path` for all filesystem paths (cross-platform: Windows, macOS, Linux).
- Keep the public interface minimal: `Config`, `Place`, `GmapsScraper`, `export_places`.
- Prefer `contextlib.suppress(Exception)` over bare `try/except/pass`.
- Line length is 100 characters (enforced by ruff, except E501 is ignored).

## Safety & Ethics

- This tool scrapes Google Maps. Always remind users to respect Google's Terms of Service, rate limits, and local laws.
- Keep default concurrency conservative (`4`).
- Generated data (`data/`, `sessions/`, `screenshots/`) is gitignored; only `.gitkeep` files are tracked.

## macOS Notes

- Camoufox downloads the correct browser binary automatically.
- Users may need to remove macOS quarantine attributes if Gatekeeper blocks the browser:
  `xattr -rd com.apple.quarantine ~/.cache/uv/`

## Commits

Do not run `git commit`, `git push`, or other git mutations unless the user explicitly asks.
