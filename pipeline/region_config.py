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
DEFAULT_POVERTY_GRDI = PROJECT_ROOT / "data" / "raw" / "povmap-grdi-v1-10.tif"
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


# Mexico City is coded MEX (no underscore). Event extracts use folder "full".
_CITY_FOLDER_OVERRIDE = {"MEX": "MexicoCity"}
_IMAGE_EXTS = {".png", ".pdf", ".svg", ".jpg", ".jpeg"}
_GEO_EXTS = {".gpkg", ".shp", ".geojson", ".tif", ".tiff"}


def layout_parts(code: str) -> tuple[str, str]:
    """(country, city_or_full) for folder layout. IDN extract → ('IDN', 'full')."""
    country = country_prefix(code)
    if is_event_region(code):
        return country, "full"
    if code in _CITY_FOLDER_OVERRIDE:
        return country, _CITY_FOLDER_OVERRIDE[code]
    if "_" in code:
        return country, code.split("_", 1)[1]
    return country, code


def region_from_layout(country: str, place: str) -> str:
    """Inverse of layout_parts."""
    if place == "full":
        return country
    for code, slug in _CITY_FOLDER_OVERRIDE.items():
        if country_prefix(code) == country and slug == place:
            return code
    if place == country:
        return country
    return f"{country}_{place}"


def csv_dir(region: str, step: str | None = None) -> Path:
    country, place = layout_parts(region)
    p = PROJECT_ROOT / "outputs" / country / place
    return p / step if step else p


def figure_dir(region: str, step: str | None = None) -> Path:
    country, place = layout_parts(region)
    p = PROJECT_ROOT / "figure" / country / place
    return p / step if step else p


def geo_dir(region: str, step: str | None = None) -> Path:
    country, place = layout_parts(region)
    p = PROJECT_ROOT / "data" / "processed" / country / place
    return p / step if step else p


_COUNTRY_LABEL = {
    "PHI": "Philippines",
    "KEN": "Kenya",
    "MEX": "Mexico",
    "IDN": "Indonesia",
    "LKA": "Sri Lanka",
    "COL": "Colombia",
    "ECU": "Ecuador",
    "ZAF": "South Africa",
}

# Pink–green armyrose (same as residual maps). Cream skipped for country fills.
ARMYROSE = (
    "#798234",
    "#A3AD62",
    "#D0D3A2",
    "#FDFBE4",
    "#F0C6C3",
    "#DF91A3",
    "#D46780",
)
ARMYROSE_COUNTRY = {
    "Kenya": ARMYROSE[0],
    "Philippines": ARMYROSE[6],
    "Mexico": ARMYROSE[1],
    "Indonesia": ARMYROSE[5],
    "Sri Lanka": ARMYROSE[2],
    "Colombia": ARMYROSE[4],
    "Ecuador": "#5F6E28",
    "South Africa": "#A33A58",
}


def country_display_name(code: str) -> str:
    return _COUNTRY_LABEL.get(country_prefix(code), country_prefix(code))


def display_label(code: str, cfg: dict | None = None) -> str:
    """City name, or '{name} (full)' for an unclipped extract."""
    if cfg is None:
        cfg = get_region_config(code)
    label = cfg.get("city_label") or cfg.get("map_bbox_label") or cfg.get("name") or code
    if is_event_region(code, cfg):
        return f"{label} (full)"
    return label


def list_event_regions() -> list:
    regions = load_regions()
    return [k for k in list_regions() if is_event_region(k, regions[k])]


def find_artifact(region: str, step: str, filename: str) -> Path | None:
    """New layout first, then legacy outputs/{REGION}/{step}/filename."""
    ext = Path(filename).suffix.lower()
    if ext in _GEO_EXTS:
        new = geo_dir(region, step) / filename
    elif ext in _IMAGE_EXTS:
        new = figure_dir(region, step) / filename
    else:
        new = csv_dir(region, step) / filename
    if new.exists():
        return new
    old = PROJECT_ROOT / "outputs" / region / step / filename
    return old if old.exists() else None


def baseline_path(region: str, hour: int) -> Path:
    """Shared Meta baseline GPKG for a country (cities reuse the event extract)."""
    country, _ = layout_parts(region)
    return PROJECT_ROOT / "data" / "baselines" / country / f"fb_baseline_median_h{int(hour):02d}.gpkg"


class StepPaths:
    """One step's CSV / figure / GPKG dirs. ``paths / 'a.png'`` routes by suffix."""

    def __init__(self, region: str, step: str):
        self.region = region
        self.step = step
        self.csv_dir = csv_dir(region, step)
        self.fig_dir = figure_dir(region, step)
        self.geo_dir = geo_dir(region, step)

    def mkdir(self, parents: bool = True, exist_ok: bool = True):
        for d in (self.csv_dir, self.fig_dir, self.geo_dir):
            d.mkdir(parents=parents, exist_ok=exist_ok)
        return self

    def __truediv__(self, name):
        n = str(name)
        ext = Path(n).suffix.lower()
        if ext in _IMAGE_EXTS:
            return self.fig_dir / n
        if ext in _GEO_EXTS:
            return self.geo_dir / n
        return self.csv_dir / n

    def __fspath__(self):
        return str(self.csv_dir)

    def __str__(self):
        return str(self.csv_dir)


def step_paths(region: str, step: str) -> StepPaths:
    paths = StepPaths(region, step)
    paths.mkdir()
    return paths


def region_from_artifact_path(path: Path | str | None) -> str | None:
    """Recover region code from outputs/figure/data/processed country/city paths."""
    if path is None:
        return None
    parts = Path(path).resolve().parts
    for root in ("outputs", "figure", "processed", "baselines"):
        if root not in parts:
            continue
        i = parts.index(root)
        if root == "baselines" and i + 1 < len(parts):
            return None
        if i + 2 >= len(parts):
            continue
        country, place = parts[i + 1], parts[i + 2]
        if place in ("01", "02"):
            continue
        return region_from_layout(country, place)
    return None


def resolve_step_paths(
    region: str | None,
    step: str,
    output_dir: Path | None = None,
    input_path: Path | str | None = None,
) -> Path | StepPaths:
    """Prefer --region, else infer from input path, else ``output_dir/step`` (legacy)."""
    code = region or region_from_artifact_path(input_path)
    if code:
        return step_paths(code, step)
    d = Path(output_dir or (PROJECT_ROOT / "outputs")) / step
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_output_dir(region: str, step: str) -> Path:
    """CSV directory for a pipeline step: outputs/{country}/{city|full}/{step}."""
    return csv_dir(region, step)


def get_input_path(region: str, step: str, filename: str) -> Path:
    """Input path for a step (GPKGs live under data/processed)."""
    prev_step = {"02": "01", "04": "02", "03a": "02", "03b": "02", "03c": "02", "03d": "02", "03e": "02", "03f": "02"}
    in_step = prev_step.get(step, "01")
    ext = Path(filename).suffix.lower()
    base = geo_dir(region, in_step) if ext in _GEO_EXTS else csv_dir(region, in_step)
    return base / filename


def list_regions() -> list:
    """List available region codes (cities and event extracts)."""
    return [k for k in load_regions().keys() if k not in GLOBAL_KEYS]


def country_prefix(code: str) -> str:
    """KEN_Nairobi → KEN; MEX → MEX."""
    return code.split("_", 1)[0]


def is_event_region(code: str, cfg: dict | None = None) -> bool:
    """Unclipped Meta extract: ISO3-only code with clip_shape unset."""
    if "_" in code:
        return False
    if cfg is None:
        regions = load_regions()
        cfg = regions.get(code) or {}
    return not bool(cfg.get("clip_shape"))


def list_cities(country: str | None = None) -> list:
    """Selected study cities, optionally limited to one country prefix (PHI, KEN, MEX, …)."""
    regions = load_regions()
    out = []
    for k in list_regions():
        if is_event_region(k, regions[k]):
            continue
        if country is not None and country_prefix(k) != country:
            continue
        out.append(k)
    return out


def list_event_region(country: str) -> str | None:
    """Unclipped extract code for a country, or None (PHI/KEN/MEX have cities only)."""
    regions = load_regions()
    if country in GLOBAL_KEYS or country not in regions:
        return None
    if is_event_region(country, regions[country]):
        return country
    return None


def expand_region_to_list(region_or_prefix: str, *, event: bool = False) -> list:
    """
    Expand a country code to the runs to execute.

    Default: all selected cities in that country
      MEX → Mexico City, Puebla, León
      IDN → Medan, Banda Aceh (not the unclipped extract)
      PHI → all Philippines cities

    event=True: the unclipped Meta extract, if one exists
      IDN → IDN; MEX/PHI/KEN raise (no extract region)

    A full city code still maps to itself so other scripts can resume one city.
    Comma-separated lists are not accepted; pass one country code.
    """
    raw = str(region_or_prefix).strip()
    if "," in raw:
        raise ValueError(
            "Pass one country code (e.g. MEX or IDN), not a comma-separated city list."
        )
    if not raw:
        return []

    regions = load_regions()
    keys = list_regions()

    if event:
        ev = list_event_region(raw)
        if ev:
            return [ev]
        have = [k for k in keys if is_event_region(k, regions[k])]
        cities = list_cities(raw)
        extra = f" Use --region {raw} for selected cities ({', '.join(cities)})." if cities else ""
        have_txt = ", ".join(have) if have else "(none)"
        raise ValueError(
            f"No unclipped extract for {raw!r}. Configured extracts: {have_txt}.{extra}"
        )

    cities = list_cities(raw)
    if cities:
        return cities
    if raw in keys:
        return [raw]
    return []
