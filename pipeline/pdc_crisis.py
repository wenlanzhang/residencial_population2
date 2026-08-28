#!/usr/bin/env python3
"""Load or build country-level caches of Meta n_crisis at the reference hour.

Median cache: data/baselines/{COUNTRY}/fb_crisis_median_h{HH}.csv
Snapshot cache: data/baselines/{COUNTRY}/fb_crisis_snapshots_h{HH}.parquet
  (quadkey, date, n_crisis) — one row per cell-day at the reference hour.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _load_pdc_builder():
    path = PROJECT_ROOT / "data_prep" / "build_fb_baseline_median.py"
    spec = importlib.util.spec_from_file_location("build_fb_baseline_median", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pdc_input_path(cfg: dict) -> Path:
    raw = cfg.get("pdc_raw_dir")
    csv = cfg.get("pdc_processed_csv")
    if raw:
        p = Path(raw)
        if p.exists():
            return p
    if csv:
        p = Path(csv)
        if p.exists():
            return p
    missing = raw or csv or "(no pdc_raw_dir / pdc_processed_csv)"
    raise FileNotFoundError(
        f"PDC extract not found: {missing}. "
        "04b needs the Meta crisis zip (same file used to build the baseline)."
    )


def _read_pdc_frame(input_path: Path) -> pd.DataFrame:
    builder = _load_pdc_builder()
    if input_path.is_dir() or input_path.suffix.lower() == ".zip":
        df = builder.preprocess_raw_pdc(input_path)
    else:
        df = pd.read_csv(input_path, dtype={"quadkey": str})
        df.columns = df.columns.str.strip()
    if "n_crisis" not in df.columns:
        count_col = next(
            (c for c in df.columns if "crisis" in c.lower() or c.lower() in ("count", "n_")),
            None,
        )
        if count_col:
            df = df.rename(columns={count_col: "n_crisis"})
        else:
            raise ValueError(f"Expected n_crisis in {input_path}. Columns: {list(df.columns)}")
    df["date_time"] = pd.to_datetime(df["date_time"])
    df["quadkey"] = df["quadkey"].astype(str)
    df["n_crisis"] = pd.to_numeric(df["n_crisis"], errors="coerce")
    df = df.dropna(subset=["n_crisis"])
    return df[["quadkey", "date_time", "n_crisis"]].copy()


def _cfg_and_hour(code: str, *, footprint: bool, ref_hour: int | None) -> tuple[dict, int]:
    import region_config

    if footprint:
        cfg = region_config.get_footprint_config(code)
    else:
        cfg = region_config.get_region_config(code)
    hour = int(ref_hour if ref_hour is not None else cfg.get("pdc_ref_hour") or 0)
    return cfg, hour


def _write_parquet_or_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception:
        alt = path.with_suffix(".csv")
        df.to_csv(alt, index=False)
        return alt


def _read_parquet_or_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        out = pd.read_parquet(path)
    else:
        alt = path.with_suffix(".csv")
        if not alt.exists():
            raise FileNotFoundError(path)
        out = pd.read_csv(alt, dtype={"quadkey": str})
    out["quadkey"] = out["quadkey"].astype(str)
    return out


def _build_from_pdc(cfg: dict, hour: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    input_path = _pdc_input_path(cfg)
    print(f"  Building crisis caches from {input_path} (hour={hour})...")
    df = _read_pdc_frame(input_path)
    start = df["date_time"].min()
    end = df["date_time"].max()
    df["hour"] = df["date_time"].dt.hour
    df_ref = df[df["hour"] == hour].copy()
    if df_ref.empty:
        raise ValueError(f"No PDC rows at hour {hour} in {input_path}")
    df_ref["date"] = df_ref["date_time"].dt.strftime("%Y-%m-%d")
    snapshots = (
        df_ref.groupby(["quadkey", "date"], as_index=False)
        .agg(n_crisis=("n_crisis", "median"))
    )
    snapshots["quadkey"] = snapshots["quadkey"].astype(str)
    median = (
        snapshots.groupby("quadkey", as_index=False)
        .agg(n_crisis_median=("n_crisis", "median"), n_obs=("n_crisis", "size"))
    )
    median["quadkey"] = median["quadkey"].astype(str)
    median["date_start"] = start.strftime("%Y-%m-%d")
    median["date_end"] = end.strftime("%Y-%m-%d")
    median["ref_hour"] = hour
    return median, snapshots


def load_or_build_crisis_tables(
    code: str,
    *,
    footprint: bool = False,
    ref_hour: int | None = None,
    force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (median-by-quadkey, cell-day snapshots) at the reference hour."""
    import region_config

    cfg, hour = _cfg_and_hour(code, footprint=footprint, ref_hour=ref_hour)
    med_path = region_config.crisis_median_path(code, hour)
    snap_path = region_config.crisis_snapshots_path(code, hour)
    snap_csv = snap_path.with_suffix(".csv")
    have_med = med_path.exists() and not force
    have_snap = (snap_path.exists() or snap_csv.exists()) and not force
    if have_med and have_snap:
        median = pd.read_csv(med_path, dtype={"quadkey": str})
        median["quadkey"] = median["quadkey"].astype(str)
        snapshots = _read_parquet_or_csv(snap_path if snap_path.exists() else snap_csv)
        print(f"  Crisis cache: {med_path} ({len(median)} quadkeys)")
        print(f"  Snapshot cache: {len(snapshots)} cell-days, {snapshots['date'].nunique()} dates")
        return median, snapshots

    median, snapshots = _build_from_pdc(cfg, hour)
    med_path.parent.mkdir(parents=True, exist_ok=True)
    median.to_csv(med_path, index=False)
    written = _write_parquet_or_csv(snapshots, snap_path)
    print(
        f"  Saved crisis cache: {med_path} ({len(median)} quadkeys, "
        f"{median['date_start'].iloc[0]} to {median['date_end'].iloc[0]})"
    )
    print(f"  Saved snapshot cache: {written} ({len(snapshots)} cell-days, {snapshots['date'].nunique()} dates)")
    return median, snapshots


def load_or_build_crisis_median(
    code: str,
    *,
    footprint: bool = False,
    ref_hour: int | None = None,
    force: bool = False,
) -> pd.DataFrame:
    median, _ = load_or_build_crisis_tables(
        code, footprint=footprint, ref_hour=ref_hour, force=force
    )
    return median
