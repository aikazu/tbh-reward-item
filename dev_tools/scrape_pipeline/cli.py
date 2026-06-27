"""CLI entry point for the scrape pipeline."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dev_tools.scrape_pipeline.image_stage import run_bundle
from dev_tools.scrape_pipeline.manifest import write_manifest
from dev_tools.scrape_pipeline.scrape_stage import run_scrape

log = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scrape_pipeline",
        description="Refresh scraped JSON caches + download images for desktop binary bundle.",
    )
    parser.add_argument(
        "stage",
        nargs="?",
        default="all",
        choices=("scrape", "bundle", "all"),
        help="Which stage to run (default: all)",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("tbh_desktop"),
                        help="Output root dir (default: tbh_desktop)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip scrape combos with fresh cache (within --max-cache-age)")
    parser.add_argument("--max-cache-age", type=int, default=7,
                        help="Max cache age in days for --resume (default: 7)")
    parser.add_argument("--workers", type=int, default=4,
                        help="ThreadPoolExecutor worker count for image stage (default: 4)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen, don't write files")
    return parser.parse_args(argv)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code (0 success, 1 hard fail)."""
    _setup_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    out_dir: Path = args.out_dir

    if args.dry_run:
        print(f"[dry-run] would run stage={args.stage} out_dir={out_dir} "
              f"resume={args.resume} workers={args.workers}")
        return 0

    started = datetime.now().isoformat(timespec="seconds")
    scrape_stats: dict = {}
    bundle_stats: dict = {}

    if args.stage in ("scrape", "all"):
        scrape_stats = run_scrape(
            out_dir,
            resume=args.resume,
            max_cache_age_days=args.max_cache_age,
        )
        log.info("scrape stage done: %s", scrape_stats)

    if args.stage in ("bundle", "all"):
        bundle_stats = run_bundle(out_dir, out_dir, workers=args.workers)
        log.info("bundle stage done: %s", bundle_stats)

    write_manifest(
        {
            "scrape_started_at": started,
            "scrape": scrape_stats,
            "images": bundle_stats,
        },
        out_dir / "manifest.json",
    )
    log.info("manifest written to %s", out_dir / "manifest.json")

    # Hard fail: scrape produced 0 items AND nothing cached
    if args.stage in ("scrape", "all"):
        if scrape_stats.get("items_total", 0) == 0 and scrape_stats.get("combos_cached", 0) == 0:
            log.error("scrape stage produced no items and no cache fallback")
            return 1
    return 0
