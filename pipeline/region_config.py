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

# Top-level keys in regions.json that are not region codes
GLOBAL_KEYS = ("data_root", "poverty_source", "poverty_grdi", "clip_source")
DEFAULT_POVERTY_SOURCE = "grdi"
VALID_POVERTY_SOURCES = ("grdi", "rwi")
DEFAULT_POVERTY_GRDI = PROJECT_ROOT / "data" / "povmap-grdi-v1-10.tif"
DEFAULT_CLIP_SOURCE = "local"
VALID_CLIP_SOURCES = ("local", "osm", "geob")


def load_regions():
    """Load regions.json. Returns dict region_code -> config (includes global keys)."""
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


def get_poverty_source(regions: dict | None = None) -> str:
    """Global default poverty source from config (`grdi` or `rwi`)."""
    if regions is None:
        regions = load_regions()
    src = str(regions.get("poverty_source") or DEFAULT_POVERTY_SOURCE).strip().lower()
    if src not in VALID_POVERTY_SOURCES:
        raise ValueError(
            f"Unknown poverty_source {src!r}. Use one of: {', '.join(VALID_POVERTY_SOURCES)}"
        )
    return src


def resolve_poverty_path(cfg: dict, source: str | None = None) -> Path | None:
    """
    Active poverty file for a region config.

    grdi → top-level poverty_grdi (project-root GeoTIFF)
    rwi  → per-region poverty (RWI CSV under data_root)
    """
    src = (source or cfg.get("poverty_source") or DEFAULT_POVERTY_SOURCE)
    src = str(src).strip().lower()
    if src not in VALID_POVERTY_SOURCES:
        raise ValueError(
            f"Unknown poverty source {src!r}. Use one of: {', '.join(VALID_POVERTY_SOURCES)}"
        )
    if src == "grdi":
        path = cfg.get("poverty_grdi")
        return Path(path) if path else None
    path = cfg.get("poverty")
    return Path(path) if path else None


def get_clip_source(regions: dict | None = None, region_cfg: dict | None = None) -> str:
    """Clip boundary source: `local` (default), `osm`, or `geob`."""
    raw = None
    if region_cfg and region_cfg.get("clip_source"):
        raw = region_cfg.get("clip_source")
    elif regions is not None:
        raw = regions.get("clip_source")
    elif region_cfg is None:
        regions = load_regions()
        raw = regions.get("clip_source")
    src = str(raw or DEFAULT_CLIP_SOURCE).strip().lower()
    if src not in VALID_CLIP_SOURCES:
        raise ValueError(
            f"Unknown clip_source {src!r}. Use one of: {', '.join(VALID_CLIP_SOURCES)}"
        )
    return src


def get_region_config(region: str) -> dict:
    """Get config for region (e.g. PHI, KEN, MEX). Resolves paths."""
    regions = load_regions()
    data_root = regions.get("data_root")
    if data_root:
        data_root = Path(data_root)
    if region not in regions or region in GLOBAL_KEYS:
        raise ValueError(f"Unknown region: {region}. Available: {list_regions()}")
    cfg = regions[region].copy()
    path_keys = ("worldpop", "meta", "poverty", "clip_shape", "pdc_raw_dir", "pdc_processed_csv")
    data_root_keys = ("poverty", "pdc_raw_dir")
    for key in path_keys:
        if key in cfg and cfg[key]:
            base = data_root if (data_root and key in data_root_keys) else PROJECT_ROOT
            cfg[key] = resolve_path(cfg[key], base)

    cfg["region_code"] = region
    cfg["poverty_source"] = get_poverty_source(regions)
    grdi = regions.get("poverty_grdi")
    cfg["poverty_grdi"] = resolve_path(grdi, PROJECT_ROOT) if grdi else DEFAULT_POVERTY_GRDI
    cfg["clip_source"] = get_clip_source(regions, cfg)
    return cfg


def get_output_dir(region: str, step: str) -> Path:
    """Output directory for a pipeline step. E.g. outputs/PHI/01, outputs/PHI/02."""
    return PROJECT_ROOT / "outputs" / region / step


def get_input_path(region: str, step: str, filename: str) -> Path:
    """Input path for a step. E.g. outputs/PHI/01/harmonised_meta_worldpop.gpkg."""
    prev_step = {"02": "01", "04": "02", "03a": "02", "03b": "02", "03c": "02", "03d": "02", "03e": "02", "03f": "02"}
    in_step = prev_step.get(step, "01")
    return get_output_dir(region, in_step) / filename


def list_regions() -> list:
    """List available region codes."""
    return [k for k in load_regions().keys() if k not in GLOBAL_KEYS]


def expand_region_to_list(region_or_prefix: str) -> list:
    """
    Expand a region code, country prefix, or comma-separated list to region codes.
    PHI -> [PHI_CagayandeOroCity, PHI_DavaoCity, ...]; KEN -> [KEN_Nairobi, KEN_Mombasa, ...];
    MEX -> [MEX]; IDN / LKA / COL / ECU / ZAF -> that event region;
    IDN,LKA,ZAF -> [IDN, LKA, ZAF];
    PHI_CagayandeOroCity -> [PHI_CagayandeOroCity].
    """
    keys = list_regions()
    parts = [p.strip() for p in str(region_or_prefix).split(",") if p.strip()]
    out = []
    seen = set()
    for part in parts:
        matches = [part] if part in keys else [k for k in keys if k.startswith(part)]
        for m in matches:
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out
