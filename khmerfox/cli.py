"""Compact CLI for KhmerFox."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from khmerfox.core import OUTPUT_FIELDS, Config, GmapsScraper, export_places


def _env(key: str, default):
    val = os.getenv(key, str(default))
    if isinstance(default, bool):
        return val.lower() in {"1", "true", "yes", "on"}
    try:
        return type(default)(val)
    except (ValueError, TypeError):
        return default


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="khmerfox",
        description="Cambodia Google Maps scraper powered by Camoufox",
    )
    p.add_argument("-q", "--query", default="ហាងកាហ្វេនៅភ្នំពេញ", help="Search query")
    p.add_argument("-t", "--territory", default="Cambodia", help="Territory for normalization")
    p.add_argument("--headless", default=_env("HEADLESS", True), action=argparse.BooleanOptionalAction)
    p.add_argument("--max-results", type=int, default=_env("MAX_RESULTS", 0))
    p.add_argument("--concurrency", type=int, default=_env("CONCURRENCY", 4))
    p.add_argument("--format", default="csv", help="csv,json,md,xlsx,comma-separated,all")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--proxy", default="")
    p.add_argument("--screenshots", default=_env("SCREENSHOTS", False), action=argparse.BooleanOptionalAction)
    p.add_argument("--session", default="default")
    p.add_argument("--scroll-delay", type=float, default=1.0)
    p.add_argument("--page-delay", type=float, default=1.0)
    p.add_argument("--retries", type=int, default=1)
    p.add_argument(
        "--fields",
        default="",
        help="Comma-separated output fields (default: core set). Use 'all' for every field.",
    )
    return p


def _parse_fields(text: str) -> list[str] | None:
    if not text:
        return None
    if text.strip().lower() == "all":
        return list(OUTPUT_FIELDS)
    return [f.strip() for f in text.split(",") if f.strip()]


def config_from_args(args: argparse.Namespace) -> Config:
    return Config(
        query=args.query,
        territory=args.territory,
        headless=args.headless,
        log_level=args.log_level,
        output_format=args.format,
        max_results=args.max_results,
        concurrency=args.concurrency,
        scroll_delay=args.scroll_delay,
        page_delay=args.page_delay,
        retries=args.retries,
        proxy=args.proxy,
        screenshots=args.screenshots,
        session_name=args.session,
        fields=_parse_fields(args.fields),
    )


async def run_async(config: Config) -> int:
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    places = await GmapsScraper(config).run()
    if not places:
        logging.warning("No places collected")
        return 1
    paths = export_places(places, config.query, config.output_format, config.fields)
    for path in paths:
        print(f"Saved: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run_async(config_from_args(args)))


if __name__ == "__main__":
    sys.exit(main())
