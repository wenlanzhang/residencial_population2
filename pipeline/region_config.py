#!/usr/bin/env python3
"""
Region configuration for multi-country pipeline.

Loads config/regions.json and provides paths for each region.
Paths in config can be relative (to project root) or absolute.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "regions.json"


def load_regions():
    """Load regions.json. Returns dict region_code -> config."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Region config not found: {CONFIG_PATH}")
    with open(CONFIG_PATH) as f:
        return json.load(f)


def resolve_path(p: str, base: Path | None = None) -> Path:
    """Resolve path: absolute stays, relative is relative to base or PROJECT_ROOT."""
    path = Path(p)
    if not path.is_absolute():
        path = (base or PROJECT_ROOT) / path
    return path


def get_region_config(region: str) -> dict:
    """Get config for region (e.g. PHI, KEN, MEX). Resolves paths."""
    regions = load_regions()
    data_root = regions.get("data_root")
    if data_root:
        data_root = Path(data_root)
    if region not in regions or region == "data_root":
        raise ValueError(f"Unknown region: {region}. Available: {list_regions()}")
    cfg = regions[region].copy()
    path_keys = ("worldpop", "meta", "poverty", "clip_shape", "pdc_raw_dir", "pdc_processed_csv")
    data_root_keys = ("worldpop", "poverty", "pdc_raw_dir")
    for key in path_keys:
        if key in cfg and cfg[key]:
            base = data_root if (data_root and key in data_root_keys) else PROJECT_ROOT
            cfg[key] = resolve_path(cfg[key], base)
    return cfg


def get_output_dir(region: str, step: str) -> Path:
    """Output directory for a pipeline step. E.g. outputs/PHI/01, outputs/PHI/02."""
    return PROJECT_ROOT / "outputs" / region / step


def get_input_path(region: str, step: str, filename: str) -> Path:
    """Input path for a step. E.g. outputs/PHI/01/harmonised_meta_worldpop.gpkg."""
    prev_step = {"02": "01", "03a": "02", "03b": "02", "03c": "02", "03d": "02", "03e": "02", "03f": "02"}
    in_step = prev_step.get(step, "01")
    return get_output_dir(region, in_step) / filename


def list_regions() -> list:
    """List available region codes."""
    return [k for k in load_regions().keys() if k != "data_root"]
