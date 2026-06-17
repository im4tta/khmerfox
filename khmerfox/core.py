"""Compact async core for KhmerFox."""

from __future__ import annotations

import asyncio
import contextlib
import csv
import datetime
import json
import logging
import re
from dataclasses import asdict, dataclass, make_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import openpyxl
from camoufox.async_api import AsyncCamoufox

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR, SESSIONS_DIR, SCREENSHOTS_DIR = (ROOT / d for d in ("data", "sessions", "screenshots"))
for _d in (DATA_DIR, SESSIONS_DIR, SCREENSHOTS_DIR):
    _d.mkdir(exist_ok=True)

# Single source of truth: (field_name, label, default_selected)
_FIELD_DEFS: list[tuple[str, str, bool]] = [
    ("place_id",                   "Place ID",              True),
    ("name",                       "Name",                  True),
    ("name_kh",                    "Name (Khmer)",          True),
    ("name_en",                    "Name (English)",        True),
    ("rating",                     "Rating",                True),
    ("reviews",                    "Reviews",               True),
    ("category",                   "Primary Category",      True),
    ("categories",                 "Categories",            False),
    ("features",                   "Features",              False),
    ("address",                    "Address",               True),
    ("fulladdr",                   "Full Address",          False),
    ("local_name",                 "Local Name",            False),
    ("local_fulladdr",             "Local Full Address",    False),
    ("addr1",                      "Address Line 1",        False),
    ("addr2",                      "Address Line 2",        False),
    ("addr3",                      "Address Line 3",        False),
    ("addr4",                      "Address Line 4",        False),
    ("district",                   "District",              False),
    ("phone",                      "Phone",                 True),
    ("phone_number",               "Phone Number",          False),
    ("international_phone_number", "International Phone",   False),
    ("phone_numbers",              "Phone Numbers",         False),
    ("website",                    "Website",               True),
    ("url",                        "URL",                   False),
    ("domain",                     "Domain",                False),
    ("hours",                      "Hours",                 True),
    ("price_level",                "Price Level",           True),
    ("plus_code",                  "Plus Code",             True),
    ("latitude",                   "Latitude",              True),
    ("longitude",                  "Longitude",             True),
    ("maps_url",                   "Maps URL",              True),
    ("listing_url",                "Listing URL",           False),
    ("thumbnail",                  "Thumbnail",             False),
    ("reviews_url",                "Reviews URL",           False),
    ("claimed",                    "Claimed",               False),
    ("fid",                        "FID",                   False),
    ("cid",                        "CID",                   False),
    ("timezone",                   "Timezone",              False),
    ("query",                      "Query",                 False),
    ("created_at",                 "Created At",            False),
]

OUTPUT_FIELDS: list[str] = [f for f, _, _ in _FIELD_DEFS]
AVAILABLE_FIELDS: list[tuple[str, str, bool]] = _FIELD_DEFS

CAMBODIA_DEFAULT_QUERY = "ហាងកាហ្វេនៅភ្នំពេញ"


def _place_to_dict(self, fields: list[str] | None = None) -> dict[str, str]:
    data = asdict(self)
    return {f: data.get(f, "") for f in fields if f in data} if fields else data


Place = make_dataclass(
    "Place",
    [(f, str, dc_field(default="")) for f in OUTPUT_FIELDS + ["primary_category"]],
    slots=True,
    namespace={"__doc__": "A single Google Maps place.", "to_dict": _place_to_dict},
)


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
    scroll_delay: float = 0.5
    page_delay: float = 0.5
    retries: int = 1
    proxy: str = ""
    screenshots: bool = False
    session_name: str = "default"
    fields: list[str] | None = None

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
    text = text.lower()
    if m := re.search(r"[\d,]+(?=\s*review|\s*\))", text):
        return m.group(0).replace(",", "")
    if "review" in text and (m := re.search(r"[\d,]+", text)):
        return m.group(0).replace(",", "")
    return ""


def pick_reviews_count(candidates: list[str], rating: str = "") -> str:
    """Pick the most likely review count from a list of candidate texts."""
    rating_norm = rating.replace(",", "").strip()
    for text in candidates:
        if (parsed := parse_reviews(text)) and parsed != rating_norm:
            return parsed
    for text in candidates:
        if m := re.search(r"[\d,]+", text):
            num = m.group(0).replace(",", "")
            if num != rating_norm:
                try:
                    if int(num) > 5 or (rating_norm and int(num) > int(float(rating_norm))):
                        return num
                except ValueError:
                    continue
    return ""


def extract_reviews_count(page_content: str) -> str:
    """Try to extract review count from embedded JSON in the page."""
    if not page_content:
        return ""
    for pat in (
        r'"reviewCount"[:\s]+(\d+)',
        r'"review_count"[:\s]+"?(\d+)"?',
        r'"userRatingCount"[:\s]+(\d+)',
        r'"rating"[^}]*"count"[:\s]+(\d+)',
    ):
        if m := re.search(pat, page_content):
            return m.group(1)
    return ""


def extract_hours_from_features(features: str) -> str:
    """Try to recover hours text from the noisy features string."""
    if not features:
        return ""
    day_signals = (
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        "អាទិត្យ", "ច័ន្ទ", "អង្គារ", "ពុធ", "ព្រហស្បតិ៍", "សុក្រ", "សៅរ៍",
        "\u1794\u17be\u1780", "Open", "Closed",
    )
    parts = [p.strip() for p in features.split(";") if p.strip()]
    for part in reversed(parts):
        if any(s in part for s in day_signals):
            return part
    return ""


def derive_domain(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    try:
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.") if netloc else ""
    except Exception:
        return ""


def format_international_phone(phone: str, territory: str = "Cambodia") -> str:
    if not phone or territory.lower() not in {"cambodia", "kh"}:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("855"):
        return "+" + digits
    if digits.startswith("0") and len(digits) >= 9:
        return "+855" + digits[1:]
    return ""


def parse_address_parts(address: str) -> dict[str, str]:
    """Best-effort split of a Cambodian address into parts."""
    parts = {"addr1": "", "addr2": "", "addr3": "", "addr4": "", "district": ""}
    if not address:
        return parts
    chunks = [c.strip() for c in address.split(",") if c.strip()]
    for i, chunk in enumerate(chunks[:4]):
        parts[f"addr{i + 1}"] = chunk
    if len(chunks) >= 2:
        parts["district"] = chunks[-2]
    return parts


def build_reviews_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else ""


def extract_fid_cid(url: str, page_content: str = "") -> tuple[str, str]:
    """Best-effort extraction of Google internal fid/cid identifiers."""
    fid = cid = ""
    text = f"{url} {page_content}"
    if m := re.search(r"[!&]fid[=:](\d+)", text):
        fid = m.group(1)
    if m := re.search(r"[!&]cid[=:](\d+)", text):
        cid = m.group(1)
    if not cid and (m := re.search(r"0x([0-9a-f]+):0x([0-9a-f]+)", text)):
        cid = str(int(m.group(2), 16))
    return fid, cid


def slugify(query: str) -> str:
    return re.sub(r"[-\s]+", "_", re.sub(r"[^\w\s-]", "", query.lower())).strip("_-")


def _place_key(place) -> str:
    return place.place_id.strip() or place.maps_url.strip() or place.name.strip()


def dedupe_places(places: list) -> list:
    """Remove duplicate places, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list = []
    for p in places:
        key = _place_key(p)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


# --- selectors (module-level) ------------------------------------------------

_SEL: dict[str, list[tuple[str, str]]] = {
    "name": [
        ("h1.DUwDvf", "text"), ("h1", "text"), ('[data-item-id="title"]', "text"),
    ],
    "rating": [
        ('div.F7nice span[aria-hidden="true"]', "text"),
        ("span[aria-hidden='true']", "text"),
        ('button[aria-label*="star"]', "aria-label"),
    ],
    "reviews": [
        ('div.F7nice span[aria-label*="reviews"]', "aria-label"),
        ('div.F7nice button[aria-label*="reviews"]', "aria-label"),
        ("div.F7nice span", "text"),
        ('button[aria-label*="reviews"]', "aria-label"),
        ('a[aria-label*="reviews"]', "aria-label"),
    ],
    "category": [
        ("button.DkEaL", "text"),
        ('button[jsaction*="pane.rating"]', "text"),
        ('[jsaction*="pane.rating"]', "text"),
    ],
    "address": [
        ('button[data-item-id="address"] div.fontBodyMedium', "text"),
        ('[data-item-id="address"]', "text"),
        ('button[data-tooltip="Copy address"]', "text"),
    ],
    "phone": [
        ('button[data-item-id*="phone"] div.fontBodyMedium', "text"),
        ('[data-item-id*="phone"]', "text"),
        ('button[data-tooltip="Copy phone number"]', "text"),
    ],
    "website": [
        ('a[data-item-id="authority"]', "href"),
        ('[data-item-id="authority"]', "href"),
        ('a[data-tooltip="Open website"]', "href"),
    ],
    "hours": [
        ("div.t39EBf.GUrTXd[aria-label]", "aria-label"),
        ('[aria-label*="Hours"][aria-label*="day"]', "aria-label"),
        ('button[aria-label*="Hours"]', "aria-label"),
    ],
    "price_level": [
        ("span.mgr77e span[aria-label]", "text"),
        ('span[aria-label*="Price"]', "aria-label"),
        ('span[aria-label*="price"]', "aria-label"),
    ],
    "plus_code": [
        ('button[data-item-id="oloc"] div.fontBodyMedium', "text"),
        ('[data-item-id="oloc"]', "text"),
        ('button[data-tooltip="Copy plus code"]', "text"),
    ],
}


# --- extraction --------------------------------------------------------------

async def accept_cookies(page) -> None:
    try:
        form = page.locator('form[action="https://consent.google.com/save"]').first
        if await form.is_visible(timeout=3000):
            await form.locator("button").first.click()
            logging.getLogger("kf").info("Cookie consent accepted")
    except Exception:
        pass


async def extract_place(page, url: str, territory: str) -> Any:
    place = Place()
    content = ""
    with contextlib.suppress(Exception):
        content = await page.content()

    async def _try(chains: list[tuple[str, str]]) -> str:
        for sel, attr in chains:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    value = (
                        (await loc.first.text_content() or "").strip()
                        if attr == "text"
                        else (await loc.first.get_attribute(attr) or "").strip()
                    )
                    if value:
                        return value
            except Exception:
                continue
        return ""

    data: dict[str, str] = {}
    for field, chains in _SEL.items():
        data[field] = await _try(chains)

    place.name = data["name"]
    place.name_kh, place.name_en = split_name(place.name)
    place.rating = data["rating"]
    place.reviews = parse_reviews(data["reviews"]) or extract_reviews_count(content)
    place.category = data["category"]
    place.address = data["address"]
    place.phone = normalize_phone(data["phone"], territory)
    place.website = data["website"]
    place.hours = data["hours"]
    place.price_level = data["price_level"]
    place.plus_code = data["plus_code"]
    if not place.hours:
        place.hours = extract_hours_from_features(place.features)
    place.maps_url = url
    place.listing_url = url
    place.place_id = extract_place_id(url, content)
    place.latitude, place.longitude = extract_coords(url)
    if not place.name_kh and has_khmer(place.name):
        place.name_kh = place.name
    if not place.name_en and has_latin(place.name):
        place.name_en = place.name

    # Aliases / derived fields
    place.fulladdr = place.address
    place.local_name = place.name_kh
    place.local_fulladdr = place.address
    place.phone_number = place.phone
    place.international_phone_number = format_international_phone(place.phone, territory)
    place.phone_numbers = place.phone
    place.primary_category = place.category
    place.url = place.website
    place.domain = derive_domain(place.website)
    place.reviews_url = build_reviews_url(place.place_id)
    place.fid, place.cid = extract_fid_cid(url, content)
    addr = parse_address_parts(place.address)
    place.addr1, place.addr2, place.addr3, place.addr4, place.district = (
        addr["addr1"], addr["addr2"], addr["addr3"], addr["addr4"], addr["district"],
    )

    # Categories
    try:
        cat_locs = page.locator("button.DkEaL")
        cats = []
        for i in range(min(await cat_locs.count(), 5)):
            with contextlib.suppress(Exception):
                if c := (await cat_locs.nth(i).text_content() or "").strip():
                    cats.append(c)
        place.categories = "; ".join(dict.fromkeys(cats)) if cats else place.category
    except Exception:
        place.categories = place.category

    # Reviews fallback chain
    if not place.reviews:
        try:
            candidates: list[str] = []
            for sel in ("div.F7nice span", "div.F7nice button", "div.F7nice a"):
                locs = page.locator(sel)
                for i in range(min(await locs.count(), 10)):
                    with contextlib.suppress(Exception):
                        if txt := (await locs.nth(i).text_content() or "").strip():
                            if txt not in candidates:
                                candidates.append(txt)
            place.reviews = pick_reviews_count(candidates, place.rating)
        except Exception:
            pass
    if not place.reviews:
        try:
            reviews_js = await page.evaluate(
                """() => {
                    const re = /([\\d,]+)\\s*(reviews|review|ការពិនិត្យ)/i;
                    for (const el of document.querySelectorAll('*')) {
                        const t = (el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '');
                        const m = t.match(re);
                        if (m) return m[1].replace(/,/g, '');
                    }
                    return '';
                }"""
            )
            place.reviews = str(reviews_js or "")
        except Exception:
            place.reviews = ""
    if not place.reviews:
        place.reviews = extract_reviews_count(content)

    # Hours fallback
    if not place.hours:
        try:
            hours_js = await page.evaluate(
                """() => {
                    const days = /(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|អាទិត្យ|ច័ន្ទ|អង្គារ|ពុធ|ព្រហស្បតិ៍|សុក្រ|សៅរ៍)/;
                    for (const el of document.querySelectorAll('[aria-label]')) {
                        const label = el.getAttribute('aria-label') || '';
                        if (days.test(label) && label.length < 2000) return label;
                    }
                    return '';
                }"""
            )
            place.hours = str(hours_js or "")
        except Exception:
            pass

    # Features
    try:
        feat_locs = page.locator(
            'div[role="region"] div.fontBodyMedium, div[role="region"] span.fontBodyMedium'
        )
        feats = []
        for i in range(min(await feat_locs.count(), 20)):
            with contextlib.suppress(Exception):
                if ftxt := (await feat_locs.nth(i).text_content() or "").strip():
                    feats.append(ftxt)
        place.features = "; ".join(dict.fromkeys(feats)) if feats else ""
    except Exception:
        place.features = ""

    # Thumbnail
    try:
        for sel in (
            'button[data-photo-index="0"] img', 'img[class*="photo"]',
            'img[src*="googleusercontent"]', 'img[class*="image"]',
        ):
            loc = page.locator(sel).first
            if await loc.count() > 0:
                if src := (await loc.get_attribute("src") or "").strip():
                    place.thumbnail = src
                    break
        if not place.thumbnail:
            for sel in ('button[data-photo-index="0"]', '[role="img"]', 'div[style*="background-image"]'):
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    style = (await loc.get_attribute("style") or "").strip()
                    if m := re.search(r"""url\(["']?(https?://[^"')]+)""", style):
                        place.thumbnail = m.group(1)
                        break
    except Exception:
        place.thumbnail = ""

    # Claimed
    try:
        claim_state = await page.evaluate(
            r"""() => {
                const text = document.body.innerText || '';
                const labels = Array.from(document.querySelectorAll('[aria-label]'))
                    .map(el => el.getAttribute('aria-label')).join(' ');
                const all = text + ' ' + labels;
                const unclaimed = /Claim this business|អះអាង[\s\u200b-\u200d]*ពាណិជ្ជកម្ម[\s\u200b-\u200d]*នេះ|Reclamar este negocio|Gérer cette fiche|认领此商家|Xác nhận doanh nghiệp này/i.test(all);
                const claimed = /Managed by business owner|Business owner|Owner response|Your business|Manage this business|Verified by business owner/i.test(all);
                return unclaimed ? 'No' : claimed ? 'Yes' : '';
            }"""
        )
        place.claimed = str(claim_state or "")
        if not place.claimed and content:
            if re.search(r'"isClaimed"\s*:\s*(?:true|1)', content, re.IGNORECASE):
                place.claimed = "Yes"
            elif re.search(r'"isClaimed"\s*:\s*(?:false|0)', content, re.IGNORECASE):
                place.claimed = "No"
    except Exception:
        place.claimed = ""

    return place


# --- exporter ----------------------------------------------------------------

def _resolve_fields(fields: list[str] | None) -> list[str]:
    return [f for f in fields if f in OUTPUT_FIELDS] if fields else OUTPUT_FIELDS


def log_field_coverage(places: list, log: logging.Logger) -> None:
    """Log how often each output field was populated."""
    if not places:
        return
    total = len(places)
    coverage = {
        f: round(sum(1 for p in places if getattr(p, f, "").strip()) / total * 100, 1)
        for f in OUTPUT_FIELDS
    }
    log.info("Field coverage for %d places:", total)
    log.info("  High (>=80%%): %s", ", ".join(f for f, p in coverage.items() if p >= 80) or "none")
    log.info("  Medium (20-79%%): %s", ", ".join(f for f, p in coverage.items() if 20 <= p < 80) or "none")
    log.info("  Low (<20%%): %s", ", ".join(f for f, p in coverage.items() if p < 20) or "none")
    if missing := [f for f, p in coverage.items() if p == 0]:
        log.warning("Fields never populated: %s", ", ".join(missing))


def export_csv(places: list, query: str, fields: list[str] | None = None) -> Path:
    cols = _resolve_fields(fields)
    path = DATA_DIR / f"{slugify(query)}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(p.to_dict(cols) for p in places)
    return path


def export_json(places: list, query: str, fields: list[str] | None = None) -> Path:
    cols = _resolve_fields(fields)
    path = DATA_DIR / f"{slugify(query)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"query": query, "count": len(places), "places": [p.to_dict(cols) for p in places]},
            f, ensure_ascii=False, indent=2,
        )
    return path


def export_md(places: list, query: str, fields: list[str] | None = None) -> Path:
    cols = _resolve_fields(fields)
    path = DATA_DIR / f"{slugify(query)}.md"
    lines = [f"# {query}", "", f"**ទឹកដី:** Cambodia | **សរុប:** {len(places)}", ""]
    for i, p in enumerate(places, 1):
        lines.append(f"## {i}. {p.name or 'គ្មានឈ្មោះ'}")
        for fld in cols:
            if v := getattr(p, fld, ""):
                lines.append(f"- **{fld.replace('_', ' ').title()}:** {v}")
        lines += ["", "---", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_xlsx(places: list, query: str, fields: list[str] | None = None) -> Path:
    cols = _resolve_fields(fields)
    path = DATA_DIR / f"{slugify(query)}.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Places"
    ws.append(cols)
    for p in places:
        ws.append([getattr(p, f, "") for f in cols])
    wb.save(path)
    return path


_EXPORTERS = {"csv": export_csv, "json": export_json, "md": export_md, "xlsx": export_xlsx}


def export_places(places: list, query: str, fmt: str, fields: list[str] | None = None) -> list[Path]:
    fmts = list(_EXPORTERS) if fmt == "all" else [f.strip() for f in fmt.split(",")]
    return [_EXPORTERS[f](places, query, fields) for f in fmts if f in _EXPORTERS]


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

    def __init__(
        self,
        config: Config,
        progress_callback: Any | None = None,
        stop_event: asyncio.Event | None = None,
    ):
        self.cfg = config
        self.log = logging.getLogger("kf")
        self._progress = progress_callback
        self._stop_event = stop_event

    def _stopped(self) -> bool:
        return self._stop_event is not None and self._stop_event.is_set()

    async def run(self) -> list:
        query = self.cfg.query
        self.log.info("🦊 KhmerFox — %s", query)
        self.log.info("Territory: %s", self.cfg.territory)
        async with AsyncCamoufox(**self.cfg.camoufox_kwargs()) as browser:
            urls = await self._collect_urls(browser)
            if self._stopped():
                self.log.info("Scrape stopped by user")
                return []
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
            places = dedupe_places([p for p in results if p])
            now = datetime.datetime.now().isoformat()
            for p in places:
                p.query = query
                p.created_at = now
            log_field_coverage(places, self.log)
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
            await page.wait_for_timeout(1000)

            feed = page.locator('div[role="feed"]')
            if await feed.count() == 0:
                self.log.warning("Results feed not found")
                return []

            items = page.locator('div[role="feed"] > div > div > a')
            end_marker = page.locator(".HlvSq")
            target = self.cfg.max_results
            buffer = 5 if target else 0
            for i in range(200):
                if self._stopped():
                    self.log.info("URL collection stopped by user")
                    break
                await feed.first.evaluate("el => el.scrollBy(0, 4000)")
                await asyncio.sleep(self.cfg.scroll_delay)
                try:
                    if await end_marker.is_visible(timeout=1000):
                        self.log.info("Reached end of feed after %d scrolls", i + 1)
                        break
                except Exception:
                    pass
                if target and i % 2 == 0:
                    try:
                        if await items.count() >= target + buffer:
                            self.log.info("Collected enough result elements for max_results=%d", target)
                            break
                    except Exception:
                        pass
            else:
                self.log.info("Stopped scrolling after max iterations")

            items = page.locator('div[role="feed"] > div > div > a')
            total = await items.count()
            self.log.info("Found %d result elements", total)

            urls: list[str] = []
            seen_hrefs: set[str] = set()
            for i in range(total):
                if self._stopped():
                    self.log.info("URL extraction stopped by user")
                    break
                if self.cfg.max_results and len(urls) >= self.cfg.max_results:
                    break
                if (href := await items.nth(i).get_attribute("href")) and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    urls.append(href)
            self.log.info("Collected %d place URLs", len(urls))

            try:
                await page.context.storage_state(path=str(session_file))
            except Exception as exc:
                self.log.debug("Session save skipped: %s", exc)

            return urls
        finally:
            await page.close()

    async def _scrape_one(self, pool: _PagePool, url: str, idx: int, total: int):
        page = await pool.get()
        try:
            for attempt in range(self.cfg.retries + 1):
                if self._stopped():
                    self.log.info("[%d/%d] Stopped by user", idx, total)
                    return None
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
