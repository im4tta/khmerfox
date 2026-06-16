"""Compact async core for KhmerFox."""

from __future__ import annotations

import asyncio
import contextlib
import csv
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import openpyxl
from camoufox.async_api import AsyncCamoufox

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SESSIONS_DIR = ROOT / "sessions"
SCREENSHOTS_DIR = ROOT / "screenshots"
for _d in (DATA_DIR, SESSIONS_DIR, SCREENSHOTS_DIR):
    _d.mkdir(exist_ok=True)

OUTPUT_FIELDS = [
    "place_id",
    "name",
    "name_kh",
    "name_en",
    "rating",
    "reviews",
    "category",
    "address",
    "phone",
    "website",
    "hours",
    "price_level",
    "plus_code",
    "latitude",
    "longitude",
    "maps_url",
]

CAMBODIA_DEFAULT_QUERY = "ហាងកាហ្វេនៅភ្នំពេញ"


@dataclass(slots=True)
class Place:
    """A single Google Maps place."""

    place_id: str = ""
    name: str = ""
    name_kh: str = ""
    name_en: str = ""
    rating: str = ""
    reviews: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    hours: str = ""
    price_level: str = ""
    plus_code: str = ""
    latitude: str = ""
    longitude: str = ""
    maps_url: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class Config:
    """Scraper configuration."""

    query: str = CAMBODIA_DEFAULT_QUERY
    territory: str = "Cambodia"
    headless: bool = True
    log_level: str = "INFO"
    output_format: str = "csv"
    max_results: int = 0
    concurrency: int = 4
    scroll_delay: float = 1.0
    page_delay: float = 1.0
    retries: int = 1
    proxy: str = ""
    screenshots: bool = False
    session_name: str = "default"

    def camoufox_kwargs(self) -> dict[str, Any]:
        kw: dict[str, Any] = {"headless": self.headless}
        if self.proxy:
            kw["proxy"] = {"server": self.proxy}
        return kw


# --- helpers -----------------------------------------------------------------

_KHMER_RE = re.compile(r"[\u1780-\u17FF\u19E0-\u19FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def has_khmer(text: str) -> bool:
    return bool(_KHMER_RE.search(text)) if text else False


def has_latin(text: str) -> bool:
    return bool(_LATIN_RE.search(text)) if text else False


def split_name(name: str) -> tuple[str, str]:
    """Return (khmer_part, english_part)."""
    if not name:
        return "", ""
    if has_khmer(name) and not has_latin(name):
        return name.strip(), ""
    if has_latin(name) and not has_khmer(name):
        return "", name.strip()
    # Mixed: try to separate by script blocks
    parts = re.split(r"(?<=[\u1780-\u17FF])\s+(?=[A-Za-z])|(?<=[A-Za-z])\s+(?=[\u1780-\u17FF])", name)
    kh = " ".join(p for p in parts if has_khmer(p)).strip()
    en = " ".join(p for p in parts if has_latin(p)).strip()
    return kh or name.strip(), en or ""


def normalize_phone(phone: str, territory: str = "Cambodia") -> str:
    if not phone or territory.lower() not in {"cambodia", "kh"}:
        return phone.strip() if phone else ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("855") and len(digits) >= 10:
        digits = "0" + digits[3:]
    return digits


def extract_coords(url: str) -> tuple[str, str]:
    if not url:
        return "", ""
    if m := re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url):
        return m.group(1), m.group(2)
    if m := re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", url):
        return m.group(1), m.group(2)
    return "", ""


def extract_place_id(url: str, page_content: str = "") -> str:
    if url:
        for pat in (r"(?:19s|1s)(ChIJ[0-9A-Za-z_-]+)", r"1s(0x[0-9a-f]+:0x[0-9a-f]+)"):
            if m := re.search(pat, url):
                return m.group(1)
    if page_content and (m := re.search(r'"(ChIJ[0-9A-Za-z_-]{10,})"', page_content)):
        return m.group(1)
    return ""


def parse_reviews(text: str) -> str:
    if not text:
        return ""
    if m := re.search(r"[\d,]+", text):
        return m.group(0).replace(",", "")
    return text.strip()


def slugify(query: str) -> str:
    return re.sub(r"[-\s]+", "_", re.sub(r"[^\w\s-]", "", query.lower())).strip("_-")


# --- extraction --------------------------------------------------------------

async def accept_cookies(page) -> None:
    try:
        form = page.locator('form[action="https://consent.google.com/save"]').first
        if await form.is_visible(timeout=3000):
            await form.locator("button").first.click()
            logging.getLogger("kf").info("Cookie consent accepted")
    except Exception:
        pass


async def extract_place(page, url: str, territory: str) -> Place:
    place = Place()
    content = ""
    with contextlib.suppress(Exception):
        content = await page.content()

    selectors = {
        "name": ("h1.DUwDvf", "text"),
        "rating": ('div.F7nice span[aria-hidden="true"]', "text"),
        "reviews": ('div.F7nice span[aria-label*="reviews"]', "aria-label"),
        "category": ("button.DkEaL", "text"),
        "address": ('button[data-item-id="address"] div.fontBodyMedium', "text"),
        "phone": ('button[data-item-id*="phone"] div.fontBodyMedium', "text"),
        "website": ('a[data-item-id="authority"]', "href"),
        "hours": ("div.t39EBf.GUrTXd[aria-label]", "aria-label"),
        "price_level": ("span.mgr77e span[aria-label]", "text"),
        "plus_code": ('button[data-item-id="oloc"] div.fontBodyMedium', "text"),
    }

    data: dict[str, str] = {}
    for field, (sel, attr) in selectors.items():
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                data[field] = (
                    (await loc.first.text_content() or "").strip()
                    if attr == "text"
                    else (await loc.first.get_attribute(attr) or "").strip()
                )
        except Exception:
            pass

    place.name = data.get("name", "")
    place.name_kh, place.name_en = split_name(place.name)
    place.rating = data.get("rating", "")
    place.reviews = parse_reviews(data.get("reviews", ""))
    place.category = data.get("category", "")
    place.address = data.get("address", "")
    place.phone = normalize_phone(data.get("phone", ""), territory)
    place.website = data.get("website", "")
    place.hours = data.get("hours", "")
    place.price_level = data.get("price_level", "")
    place.plus_code = data.get("plus_code", "")
    place.maps_url = url
    place.place_id = extract_place_id(url, content)
    place.latitude, place.longitude = extract_coords(url)

    if not place.name_kh and has_khmer(place.name):
        place.name_kh = place.name
    if not place.name_en and has_latin(place.name):
        place.name_en = place.name

    return place


# --- exporter ----------------------------------------------------------------

def export_csv(places: list[Place], query: str) -> Path:
    path = DATA_DIR / f"{slugify(query)}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(p.to_dict() for p in places)
    return path


def export_json(places: list[Place], query: str) -> Path:
    path = DATA_DIR / f"{slugify(query)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"query": query, "count": len(places), "places": [p.to_dict() for p in places]},
            f,
            ensure_ascii=False,
            indent=2,
        )
    return path


def export_md(places: list[Place], query: str) -> Path:
    path = DATA_DIR / f"{slugify(query)}.md"
    lines = [f"# {query}", "", f"**ទឹកដី:** Cambodia | **សរុប:** {len(places)}", ""]
    for i, p in enumerate(places, 1):
        lines.append(f"## {i}. {p.name or 'គ្មានឈ្មោះ'}")
        for fld in OUTPUT_FIELDS:
            v = getattr(p, fld, "")
            if v:
                lines.append(f"- **{fld.replace('_', ' ').title()}:** {v}")
        lines += ["", "---", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_xlsx(places: list[Place], query: str) -> Path:
    path = DATA_DIR / f"{slugify(query)}.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Places"
    ws.append(OUTPUT_FIELDS)
    for p in places:
        ws.append([getattr(p, f, "") for f in OUTPUT_FIELDS])
    wb.save(path)
    return path


_EXPORTERS = {
    "csv": export_csv,
    "json": export_json,
    "md": export_md,
    "xlsx": export_xlsx,
}


def export_places(places: list[Place], query: str, fmt: str) -> list[Path]:
    fmts = [f.strip() for f in fmt.split(",")] if fmt != "all" else list(_EXPORTERS.keys())
    return [_EXPORTERS[f](places, query) for f in fmts if f in _EXPORTERS]


# --- scraper -----------------------------------------------------------------

class _PagePool:
    """Pool of Playwright pages for concurrent reuse."""

    def __init__(self, browser, size: int):
        self.browser = browser
        self.size = size
        self._pages: list[Any] = []
        self._lock = asyncio.Lock()
        self._avail = asyncio.Semaphore(0)

    async def init(self):
        context = await self.browser.new_context(viewport={"width": 1920, "height": 1080})
        for _ in range(self.size):
            self._pages.append(await context.new_page())
            self._avail.release()

    async def get(self) -> Any:
        await self._avail.acquire()
        async with self._lock:
            return self._pages.pop()

    async def put(self, page: Any):
        async with self._lock:
            self._pages.append(page)
        self._avail.release()


class GmapsScraper:
    """Async Google Maps scraper."""

    def __init__(self, config: Config, progress_callback: Any | None = None):
        self.cfg = config
        self.log = logging.getLogger("kf")
        self._progress = progress_callback

    async def run(self) -> list[Place]:
        query = self.cfg.query
        self.log.info("🦊 KhmerFox — %s", query)
        self.log.info("Territory: %s", self.cfg.territory)

        async with AsyncCamoufox(**self.cfg.camoufox_kwargs()) as browser:
            urls = await self._collect_urls(browser)
            if not urls:
                self.log.warning("No place URLs found")
                return []

            concurrency = min(self.cfg.concurrency, len(urls))
            self.log.info("Scraping %d places with concurrency %d...", len(urls), concurrency)
            pool = _PagePool(browser, concurrency)
            await pool.init()
            results = await asyncio.gather(
                *(self._scrape_one(pool, url, i + 1, len(urls)) for i, url in enumerate(urls))
            )
            places = [p for p in results if p]
            self.log.info("✅ Complete: %d/%d places collected", len(places), len(urls))
            return places

    async def _collect_urls(self, browser) -> list[str]:
        session_file = SESSIONS_DIR / f"{self.cfg.session_name}.json"
        page = await browser.new_page(
            storage_state=str(session_file) if session_file.exists() else None,
            viewport={"width": 1920, "height": 1080},
        )
        try:
            url = f"https://www.google.com/maps/search/{self.cfg.query.replace(' ', '+')}"
            await page.goto(url, wait_until="domcontentloaded")
            await accept_cookies(page)
            await page.wait_for_timeout(1500)

            feed = page.locator('div[role="feed"]')
            if await feed.count() == 0:
                self.log.warning("Results feed not found")
                return []

            end_marker = page.locator(".HlvSq")
            for i in range(200):
                await feed.first.evaluate("el => el.scrollBy(0, 4000)")
                await asyncio.sleep(self.cfg.scroll_delay)
                try:
                    if await end_marker.is_visible(timeout=1000):
                        self.log.info("Reached end of feed after %d scrolls", i + 1)
                        break
                except Exception:
                    pass
            else:
                self.log.info("Stopped scrolling after max iterations")

            items = page.locator('div[role="feed"] > div > div > a')
            total = await items.count()
            self.log.info("Found %d result elements", total)

            urls: list[str] = []
            for i in range(total):
                if self.cfg.max_results and len(urls) >= self.cfg.max_results:
                    break
                href = await items.nth(i).get_attribute("href")
                if href:
                    urls.append(href)
            self.log.info("Collected %d place URLs", len(urls))

            try:
                await page.context.storage_state(path=str(session_file))
            except Exception as exc:
                self.log.debug("Session save skipped: %s", exc)

            return urls
        finally:
            await page.close()

    async def _scrape_one(self, pool: _PagePool, url: str, idx: int, total: int) -> Place | None:
        page = await pool.get()
        try:
            for attempt in range(self.cfg.retries + 1):
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(int(self.cfg.page_delay * 1000))
                    place = await extract_place(page, url, self.cfg.territory)
                    if place.name:
                        self.log.info("[%d/%d] %s", idx, total, place.name)
                        if self._progress:
                            self._progress()
                        return place
                    self.log.warning("[%d/%d] No name found", idx, total)
                except Exception as exc:
                    self.log.warning("[%d/%d] Attempt %d failed: %s", idx, total, attempt + 1, exc)
                    if self.cfg.screenshots:
                        with contextlib.suppress(Exception):
                            await page.screenshot(path=str(SCREENSHOTS_DIR / f"err_{idx}_{attempt}.png"))
            return None
        finally:
            await pool.put(page)
