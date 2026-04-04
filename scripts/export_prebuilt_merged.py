#!/usr/bin/env python3
"""
Build merged load+weather CSV for one OpenEI city (same pipeline as the API) and copy it
to prebuilt_merged/{city_key}_load_weather_merged.csv for fast deploy / Render.

Usage (from repo root):
  pip install -r requirements.txt
  export NSRDB_API_KEY=... NSRDB_EMAIL=...    # strongly recommended (Open-Meteo may fail in CI)
  python scripts/export_prebuilt_merged.py --city "Chicago IL"

Afterward: git add prebuilt_merged/*.csv && git commit && push (or upload files to PREBUILT_MERGED_BASE_URL).
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_main_module():
    path = REPO_ROOT / "backend" / "main.py"
    spec = importlib.util.spec_from_file_location("eae_backend_main", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    parser = argparse.ArgumentParser(description="Export prebuilt merged CSV for one city.")
    parser.add_argument(
        "--city",
        required=True,
        help='OpenEI display name e.g. "Chicago IL"',
    )
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT))
    import os

    os.chdir(REPO_ROOT)

    mod = load_main_module()
    if not getattr(mod, "MODULES_AVAILABLE", False):
        print("ERROR: backend modules not importable (install requirements from repo root).", file=sys.stderr)
        sys.exit(1)

    city = args.city.strip()
    print(f"Building merged dataset for {city!r} (may take several minutes)...")
    merged_path, err_step, err_msg, src = mod.ensure_city_prepared(city)
    if merged_path is None:
        print(f"ERROR step={err_step}: {err_msg}", file=sys.stderr)
        sys.exit(1)

    canonical = mod.get_canonical_city_key(city)
    if not canonical:
        print("ERROR: could not resolve canonical key", file=sys.stderr)
        sys.exit(1)
    city_key = canonical.lower()

    out_dir = REPO_ROOT / "prebuilt_merged"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{city_key}_load_weather_merged.csv"
    shutil.copy2(merged_path, dest)
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"OK -> {dest} ({size_mb:.1f} MiB)  [weather_source={src}]")


if __name__ == "__main__":
    main()
