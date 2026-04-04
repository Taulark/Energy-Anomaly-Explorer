"""
FastAPI backend for Energy Anomaly Explorer
Reuses existing Python modules for data processing, regression, and anomaly detection.
"""
import json
import os
import time
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Tuple
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path to import existing modules
# Ensure repo root is in sys.path (parent of /backend)
ROOT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT_DIR
sys.path.insert(0, str(ROOT_DIR))

# Import existing modules
try:
    from openei_loader import fetch_openei_city_resources, download_load_profile
    from nsrdb_downloader import (
        fetch_nsrdb_weather, CITY_COORDS, ensure_city_coordinates, resolve_city_coords_fallback
    )
    from build_merge import build_and_save_merged
    from regression_engine import (
        get_candidate_weather_features, select_weather_features, fit_regression, get_regression_confidence
    )
    from insights import (
        generate_anomaly_explanations, detect_recurring_patterns,
        generate_executive_summary, estimate_cost_impact
    )
    from occupancy_insights import generate_occupancy_insights
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False

app = FastAPI(title="Energy Anomaly Explorer API")

# CORS middleware — allows localhost (dev) and any Render/custom domain (prod)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(http://localhost:\d+|https://.*\.onrender\.com|https://.*)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for results
cache = {
    "cities": None,
    "buildings": {},
    "regression_results": {},
    "anomaly_results": {},
    "model_cache": {},
}

# Disk-backed caches (helps Render cold starts and restarts; same instance disk only)
CITIES_LIST_CACHE_FILE = PROJECT_ROOT / "data" / "cities_list_cache.json"
CITIES_LIST_CACHE_TTL_SEC = 86400  # 24 hours — OpenEI city list is effectively static
MODEL_DISK_CACHE_DIR = PROJECT_ROOT / "data" / "trained_models"


def _try_load_cities_list_from_disk() -> Optional[List[str]]:
    if not CITIES_LIST_CACHE_FILE.is_file():
        return None
    try:
        with open(CITIES_LIST_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - float(data.get("ts", 0)) > CITIES_LIST_CACHE_TTL_SEC:
            return None
        cities = data.get("cities")
        return cities if isinstance(cities, list) else None
    except Exception as e:
        logger.warning(f"Could not read cities list cache: {e}")
        return None


def _save_cities_list_to_disk(city_names: List[str]) -> None:
    try:
        CITIES_LIST_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CITIES_LIST_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "cities": city_names}, f)
    except Exception as e:
        logger.warning(f"Could not write cities list cache: {e}")


def _sanitize_for_filename(s: str, max_len: int = 100) -> str:
    out = "".join(c if c.isalnum() or c in "._-" else "_" for c in (s or "").strip())
    return out[:max_len] if out else "x"


def _model_disk_cache_path(city: str, building: str) -> Path:
    MODEL_DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    c = _sanitize_for_filename(city, 120)
    b = _sanitize_for_filename(building, 120)
    return MODEL_DISK_CACHE_DIR / f"{c}__{b}.joblib"


def persist_model_for_forecast(city: str, building: str, model_data: Dict[str, Any]) -> None:
    try:
        import joblib
    except ImportError:
        logger.warning("joblib not available; skipping forecast model disk persistence")
        return
    path = _model_disk_cache_path(city, building)
    try:
        payload = {
            "model": model_data["model"],
            "scaler": model_data["scaler"],
            "features": model_data["features"],
            "residual_std": float(model_data.get("residual_std", 0) or 0),
            "r2": model_data.get("r2"),
            "city": model_data.get("city", city),
            "building": model_data.get("building", building),
            "lat": model_data.get("lat"),
            "lon": model_data.get("lon"),
        }
        joblib.dump(payload, path)
        logger.info(f"Persisted forecast model to {path}")
    except Exception as e:
        logger.warning(f"Could not persist forecast model to {path}: {e}")


def load_model_for_forecast_from_disk(city: str, building: str) -> Optional[Dict[str, Any]]:
    try:
        import joblib
    except ImportError:
        return None
    path = _model_disk_cache_path(city, building)
    if not path.is_file():
        return None
    try:
        data = joblib.load(path)
        if not isinstance(data, dict) or "model" not in data or "scaler" not in data:
            return None
        return data
    except Exception as e:
        logger.warning(f"Could not load forecast model from {path}: {e}")
        return None

# Request models
class PrepareCityRequest(BaseModel):
    city: str

class RunRequest(BaseModel):
    city: str
    building: str
    z_threshold: float = 2.0
    top_n: int = 50
    selected_year: Optional[str] = "All"
    feature_mode: str = "Auto-select (ElasticNet)"  # "Auto-select (ElasticNet)" | "Auto-select (Correlation Top-K)" | "Fixed 3-feature"
    top_k: int = 3
    include_cloud_type: bool = False
    enable_cost_estimate: bool = False
    electricity_rate: float = 0.12
    # Insight flags
    enable_insights: bool = True
    enable_recurrence: bool = True
    enable_cost_estimates: bool = False
    enable_ai_summary: bool = False

class CityResponse(BaseModel):
    cities: List[str]

class BuildingResponse(BaseModel):
    buildings: List[str]

class StatusResponse(BaseModel):
    status: str
    message: str
    ready: bool

# Helper functions (reuse existing logic)
# Cache for OpenEI city resources to avoid repeated fetches
_openei_cities_cache = None

def get_canonical_city_key(city_display: str) -> Optional[str]:
    """
    Get canonical city key from OpenEI resources with robust matching.
    Uses multiple matching strategies to handle variations in city display names.
    
    Args:
        city_display: Display name like "Chicago IL" or "Minneapolis MN"
    
    Returns:
        Canonical key like "Chicago" (from OpenEI dict), or None if not found
    """
    global _openei_cities_cache
    
    logger.info(f"get_canonical_city_key: looking up '{city_display}'")
    
    if not MODULES_AVAILABLE:
        logger.warning("Modules not available, falling back to normalize_city_key")
        return normalize_city_key(city_display)
    
    try:
        # Fetch OpenEI resources (cache after first call)
        if _openei_cities_cache is None:
            _openei_cities_cache = fetch_openei_city_resources()
            logger.info(f"Fetched OpenEI cities cache: {len(_openei_cities_cache)} cities")
            # Log available cities for debugging
            available_displays = [info.get("display", "") for info in _openei_cities_cache.values()]
            logger.debug(f"Available city displays: {available_displays[:10]}...")  # First 10 for brevity
        
        # Normalize input for matching
        normalized_input = normalize_city_name_for_matching(city_display)
        logger.debug(f"Normalized input: '{city_display}' -> '{normalized_input}'")
        
        # Strategy 1: Exact match on display name
        for canonical_key, info in _openei_cities_cache.items():
            if info.get("display") == city_display:
                logger.info(f"get_canonical_city_key: '{city_display}' -> '{canonical_key}' (exact match)")
                return canonical_key
        
        # Strategy 2: Normalized match (handles variations like commas, extra spaces)
        for canonical_key, info in _openei_cities_cache.items():
            openei_display = info.get("display", "")
            normalized_openei = normalize_city_name_for_matching(openei_display)
            if normalized_openei == normalized_input:
                logger.info(f"get_canonical_city_key: '{city_display}' -> '{canonical_key}' (normalized match: '{openei_display}')")
                return canonical_key
        
        # Strategy 3: If input ends with state (e.g., "Minneapolis MN"), try without state
        if len(city_display.split()) >= 2:
            city_without_state = ' '.join(city_display.split()[:-1])  # Remove last word (state)
            normalized_without_state = normalize_city_name_for_matching(city_without_state)
            for canonical_key, info in _openei_cities_cache.items():
                openei_display = info.get("display", "")
                normalized_openei = normalize_city_name_for_matching(openei_display)
                # Check if normalized OpenEI display starts with normalized city name
                if normalized_openei.startswith(normalized_without_state) or normalized_without_state.startswith(normalized_openei):
                    logger.info(f"get_canonical_city_key: '{city_display}' -> '{canonical_key}' (partial match: '{openei_display}')")
                    return canonical_key
        
        # Strategy 4: Match canonical key directly (case-insensitive)
        normalized_canonical = normalize_city_name_for_matching(city_display)
        for canonical_key, info in _openei_cities_cache.items():
            normalized_key = normalize_city_name_for_matching(canonical_key)
            if normalized_key == normalized_canonical:
                logger.info(f"get_canonical_city_key: '{city_display}' -> '{canonical_key}' (canonical key match)")
                return canonical_key
        
        # Fallback: use normalize_city_key if not found in OpenEI
        fallback_key = normalize_city_key(city_display)
        logger.warning(f"City '{city_display}' not found in OpenEI cache (tried {len(_openei_cities_cache)} cities), using fallback: '{fallback_key}'")
        return fallback_key
        
    except Exception as e:
        logger.exception(f"Error getting canonical city key for '{city_display}': {e}")
        # Fallback to simple normalization
        fallback_key = normalize_city_key(city_display)
        logger.warning(f"Exception during lookup, using fallback: '{fallback_key}'")
        return fallback_key

def normalize_city_name_for_matching(city_display: str) -> str:
    """
    Normalize city display name for robust matching.
    Handles variations like "Minneapolis MN", "Minneapolis, MN", "Minneapolis  MN", etc.
    
    Examples:
        "Chicago IL" -> "chicago"
        "Minneapolis MN" -> "minneapolis"
        "Houston, TX" -> "houston"
        "New York NY" -> "new york"
    """
    if not city_display:
        return ""
    
    # Lowercase, strip, collapse whitespace
    normalized = city_display.lower().strip()
    normalized = ' '.join(normalized.split())  # Collapse multiple spaces
    
    # Remove commas
    normalized = normalized.replace(',', '')
    
    # Remove trailing state abbreviation (2-letter code at end)
    # Pattern: " cityname XX" or " cityname, XX"
    import re
    normalized = re.sub(r'\s+[a-z]{2}\s*$', '', normalized)
    
    return normalized.strip()

def normalize_city_key(city_display: str) -> str:
    """
    Fallback normalization (used when OpenEI lookup fails).
    Examples:
        "Chicago IL" -> "chicago"
        "Houston TX" -> "houston"
    """
    # Extract city name (before state abbreviation)
    city_name = city_display.split()[0] if city_display else ""
    return city_name.lower().strip()

def get_building_columns(df: pd.DataFrame) -> List[str]:
    """Extract building column names from dataframe."""
    exclude_cols = {
        'hour_datetime', 'DateTime', 'datetime', 'date', 'timestamp', 'time',
        'Year', 'Month', 'Day', 'Hour',
        'Temperature', 'Dew Point', 'DewPoint', 'Clearsky GHI', 'ClearskyGHI',
        'Wind Speed', 'WindSpeed', 'Pressure', 'Cloud_Type', 'Cloud Type'
    }
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    building_cols = [col for col in numeric_cols if col not in exclude_cols and 'hour_datetime' not in col.lower()]
    return building_cols

def robust_parse_datetime(df: pd.DataFrame, city_key: str, merged_file: Path) -> Tuple[pd.DataFrame, str, Optional[Dict[str, Any]]]:
    """
    Robustly parse datetime column with multiple fallback strategies.
    Never wipes the dataframe - only drops rows if <50% are NaT.
    
    Returns:
        (cleaned_dataframe, strategy_used, error_info)
        - error_info is None if successful, otherwise dict with diagnostic info
    """
    total_rows = len(df)
    strategy_used = "unknown"
    original_df = df.copy()  # Keep original for error reporting
    
    # Step 1: Strip whitespace from column names
    df.columns = df.columns.str.strip()
    col_lower = {c.lower(): c for c in df.columns}
    
    # Step 2: Try datetime-like columns (case-insensitive)
    datetime_candidates = []
    for col in df.columns:
        col_lower_name = col.lower()
        if any(kw in col_lower_name for kw in ['hour_datetime', 'datetime', 'timestamp', 'time', 'date']):
            if col_lower_name not in ['year', 'month', 'day', 'hour']:  # Exclude component columns
                datetime_candidates.append(col)
    
    hour_datetime_created = False
    
    # Strategy 1: Try existing hour_datetime or similar datetime columns
    for dt_col in datetime_candidates:
        if hour_datetime_created:
            break
            
        logger.info(f"Trying datetime column: {dt_col}")
        try:
            # Strip whitespace from values
            if df[dt_col].dtype == 'object':
                df[dt_col] = df[dt_col].astype(str).str.strip()
            
            # Check if this looks like SAS-style datetime (DDMONYYYY:HH:MM:SS)
            # Pattern: 2 digits, 3 letter month, 4 digits, colon, time
            is_sas_format = False
            if df[dt_col].dtype == 'object' and len(df) > 0:
                sample_values = df[dt_col].dropna().head(10)
                if len(sample_values) > 0:
                    # Check if values match SAS pattern: DDMONYYYY:HH:MM:SS
                    import re
                    sas_pattern = re.compile(r'^\d{2}[A-Za-z]{3}\d{4}:\d{2}:\d{2}:\d{2}$')
                    matches = sample_values.astype(str).str.match(sas_pattern)
                    if matches.sum() >= len(sample_values) * 0.8:  # 80% match
                        is_sas_format = True
                        logger.info(f"Detected SAS-style datetime format in {dt_col}")
            
            # Try SAS format parsing first if detected
            if is_sas_format:
                try:
                    # Try with original case (pandas %b is case-sensitive but should handle uppercase)
                    df['hour_datetime'] = pd.to_datetime(
                        df[dt_col], 
                        format="%d%b%Y:%H:%M:%S", 
                        errors="coerce"
                    )
                    nat_count = df['hour_datetime'].isna().sum()
                    nat_percent = (nat_count / total_rows * 100) if total_rows > 0 else 0
                    
                    # If still high NaT, try with uppercase conversion
                    if nat_percent >= 50:
                        logger.info(f"SAS format parsing with original case had {nat_percent:.1f}% NaT, trying uppercase conversion...")
                        df['hour_datetime'] = pd.to_datetime(
                            df[dt_col].str.upper(), 
                            format="%d%b%Y:%H:%M:%S", 
                            errors="coerce"
                        )
                        nat_count = df['hour_datetime'].isna().sum()
                        nat_percent = (nat_count / total_rows * 100) if total_rows > 0 else 0
                    
                    if nat_percent < 50:
                        strategy_used = f"sas_format_{dt_col}"
                        hour_datetime_created = True
                        logger.info(f"Parsed {dt_col} using SAS format %d%b%Y:%H:%M:%S: {nat_count}/{total_rows} NaT ({nat_percent:.1f}%)")
                        # Ensure datetime64[ns] dtype
                        if not pd.api.types.is_datetime64_any_dtype(df['hour_datetime']):
                            df['hour_datetime'] = pd.to_datetime(df['hour_datetime'], errors='coerce')
                        break
                    else:
                        logger.warning(f"SAS format parsing still has {nat_count}/{total_rows} NaT ({nat_percent:.1f}%), trying standard parsing...")
                        if 'hour_datetime' in df.columns:
                            df = df.drop(columns=['hour_datetime'])
                except Exception as e:
                    logger.warning(f"SAS format parsing failed: {e}, trying standard parsing...")
                    if 'hour_datetime' in df.columns:
                        df = df.drop(columns=['hour_datetime'])
            
            # Try standard UTC parsing then convert to naive
            if not hour_datetime_created:
                try:
                    parsed = pd.to_datetime(df[dt_col], errors='coerce', utc=True)
                    if parsed.dtype.name.startswith('datetime64'):
                        parsed = parsed.dt.tz_convert(None)
                    df['hour_datetime'] = parsed
                except Exception as e:
                    logger.warning(f"UTC parsing failed for {dt_col}, trying without UTC: {e}")
                    df['hour_datetime'] = pd.to_datetime(df[dt_col], errors='coerce')
                
                nat_count = df['hour_datetime'].isna().sum()
                nat_percent = (nat_count / total_rows * 100) if total_rows > 0 else 0
                
                if nat_percent < 50:  # Less than 50% NaT - acceptable
                    strategy_used = f"datetime_column_{dt_col}"
                    hour_datetime_created = True
                    logger.info(f"Successfully parsed {dt_col}: {nat_count}/{total_rows} NaT ({nat_percent:.1f}%)")
                    # Ensure datetime64[ns] dtype
                    if not pd.api.types.is_datetime64_any_dtype(df['hour_datetime']):
                        df['hour_datetime'] = pd.to_datetime(df['hour_datetime'], errors='coerce')
                    break
                else:
                    logger.warning(f"{dt_col} has {nat_count}/{total_rows} NaT ({nat_percent:.1f}%), trying next strategy...")
                    # Don't keep this attempt if >50% NaT
                    if 'hour_datetime' in df.columns:
                        df = df.drop(columns=['hour_datetime'])
        except Exception as e:
            logger.warning(f"Error parsing {dt_col}: {e}")
            if 'hour_datetime' in df.columns:
                df = df.drop(columns=['hour_datetime'])
    
    # Strategy 2: Reconstruct from Year/Month/Day/Hour components
    if not hour_datetime_created:
        has_all = all(c in col_lower for c in ['year', 'month', 'day', 'hour'])
        
        if has_all:
            logger.info("Reconstructing datetime from Year/Month/Day/Hour columns")
            try:
                year_col = col_lower['year']
                month_col = col_lower['month']
                day_col = col_lower['day']
                hour_col = col_lower['hour']
                
                # Create datetime dict
                dt_dict = {
                    'year': df[year_col],
                    'month': df[month_col],
                    'day': df[day_col],
                    'hour': df[hour_col]
                }
                
                df['hour_datetime'] = pd.to_datetime(dt_dict, errors='coerce')
                nat_count = df['hour_datetime'].isna().sum()
                nat_percent = (nat_count / total_rows * 100) if total_rows > 0 else 0
                
                if nat_percent < 50:
                    strategy_used = "reconstructed_from_components"
                    hour_datetime_created = True
                    logger.info(f"Reconstructed datetime: {nat_count}/{total_rows} NaT ({nat_percent:.1f}%)")
                else:
                    logger.warning(f"Reconstruction has {nat_count}/{total_rows} NaT ({nat_percent:.1f}%), will try date+hour combination...")
            except Exception as e:
                logger.exception(f"Error reconstructing datetime: {e}")
    
    # Strategy 3: Try combining date column + hour column
    if not hour_datetime_created:
        date_cols = [col for col in df.columns if 'date' in col.lower() and col.lower() not in ['datetime', 'timestamp']]
        hour_cols = [col for col in df.columns if col.lower() == 'hour' and col not in ['hour_datetime']]
        
        if date_cols and hour_cols:
            date_col = date_cols[0]
            hour_col = hour_cols[0]
            logger.info(f"Trying date+hour combination: {date_col} + {hour_col}")
            try:
                # Parse date
                date_parsed = pd.to_datetime(df[date_col], errors='coerce')
                # Combine with hour
                if date_parsed.notna().any():
                    df['hour_datetime'] = date_parsed + pd.to_timedelta(df[hour_col].fillna(0), unit='h')
                    nat_count = df['hour_datetime'].isna().sum()
                    nat_percent = (nat_count / total_rows * 100) if total_rows > 0 else 0
                    
                    if nat_percent < 50:
                        strategy_used = f"date_hour_combination_{date_col}_{hour_col}"
                        hour_datetime_created = True
                        logger.info(f"Date+hour combination worked: {nat_count}/{total_rows} NaT ({nat_percent:.1f}%)")
            except Exception as e:
                logger.warning(f"Error combining date+hour: {e}")
    
    # If still no hour_datetime, return error with diagnostic info
    if not hour_datetime_created or 'hour_datetime' not in df.columns:
        # Collect diagnostic info
        datetime_keywords = ['date', 'time', 'hour', 'year', 'month', 'day', 'minute']
        datetime_cols = [col for col in original_df.columns if any(kw in col.lower() for kw in datetime_keywords)]
        
        sample_data = {}
        for col in datetime_cols[:5]:  # First 5 datetime columns
            sample_values = original_df[col].head(3).tolist()
            sample_data[col] = {
                'dtype': str(original_df[col].dtype),
                'sample_values': [str(v) for v in sample_values]
            }
        
        error_info = {
            "detected_columns": list(original_df.columns),
            "datetime_columns": datetime_cols,
            "sample_values": sample_data,
            "message": "Could not create hour_datetime from available columns"
        }
        logger.error(f"Failed to parse datetime. Error info: {error_info}")
        return original_df, "failed", error_info
    
    # Step 4: Drop NaT rows only if <50% are NaT (never wipe dataframe)
    final_nat_count = df['hour_datetime'].isna().sum()
    if final_nat_count > 0:
        nat_percent = (final_nat_count / total_rows * 100) if total_rows > 0 else 0
        
        if nat_percent < 50:  # Only drop if <50% are NaT
            rows_before = len(df)
            df = df.dropna(subset=['hour_datetime'])
            rows_after = len(df)
            dropped = rows_before - rows_after
            dropped_percent = (dropped / rows_before * 100) if rows_before > 0 else 0
            
            logger.info(
                f"Datetime cleaning: dropped {dropped} rows ({dropped_percent:.1f}%) with NaT values. "
                f"Remaining: {rows_after} rows. Strategy: {strategy_used}"
            )
        else:
            # If >50% NaT, this shouldn't happen (we should have tried another strategy)
            logger.warning(
                f"Warning: {final_nat_count}/{total_rows} NaT ({nat_percent:.1f}%) but keeping all rows. "
                f"Strategy: {strategy_used}"
            )
    
    # Step 5: Ensure hour_datetime is datetime64 type
    if 'hour_datetime' in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df['hour_datetime']):
            df['hour_datetime'] = pd.to_datetime(df['hour_datetime'], errors='coerce')
            # Re-check NaT after conversion
            final_nat_count = df['hour_datetime'].isna().sum()
            if final_nat_count > 0 and final_nat_count < len(df) * 0.5:
                df = df.dropna(subset=['hour_datetime'])
                logger.info(f"Dropped {final_nat_count} rows after final datetime conversion")
    
    # Step 6: Final validation - ensure we have valid hour_datetime
    if 'hour_datetime' not in df.columns or len(df) == 0:
        error_info = {
            "detected_columns": list(original_df.columns),
            "datetime_columns": [col for col in original_df.columns if any(kw in col.lower() for kw in ['date', 'time', 'hour', 'year', 'month', 'day'])],
            "message": "hour_datetime column missing or dataframe empty after parsing"
        }
        return original_df, "failed", error_info
    
    return df, strategy_used, None

def _openmeteo_archive_hourly_to_df(h: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """Build weather DataFrame from Open-Meteo 'hourly' JSON object."""
    if not h or "time" not in h:
        return None
    times = h["time"]
    n = len(times)
    df = pd.DataFrame({
        "hour_datetime": pd.to_datetime(times, utc=True).tz_localize(None),
        "Temperature": h.get("temperature_2m", [np.nan] * n),
        "Dew Point": h.get("dew_point_2m", [np.nan] * n),
        "Clearsky GHI": h.get("shortwave_radiation", [np.nan] * n),
        "Cloud_Type": _cloud_cover_to_type(h.get("cloud_cover", [0] * n)),
        "Wind Speed": h.get("wind_speed_10m", [np.nan] * n),
        "Pressure": h.get("surface_pressure", [np.nan] * n),
    })
    for c in ["Temperature", "Dew Point", "Clearsky GHI", "Cloud_Type", "Wind Speed", "Pressure"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def download_weather_openmeteo(
    lat: float, lon: float, start_date: str = "1998-01-01", end_date: str = "2014-12-31"
) -> Optional[pd.DataFrame]:
    """
    Download hourly weather from Open-Meteo Historical Archive API (no API key).

    Large spans are requested in chunks: a single ~17-year hourly call often times out
    or fails on cloud hosts (Render, etc.).
    """
    import requests

    url = "https://archive-api.open-meteo.com/v1/archive"
    hourly = (
        "temperature_2m,dew_point_2m,relative_humidity_2m,wind_speed_10m,"
        "surface_pressure,cloud_cover,shortwave_radiation"
    )
    headers = {"User-Agent": "EnergyAnomalyExplorer/1.0 (research; contact via GitHub Taulark/Energy-Anomaly-Explorer)"}

    t0 = pd.Timestamp(start_date).normalize()
    t1 = pd.Timestamp(end_date).normalize()
    if t0 > t1:
        t0, t1 = t1, t0

    chunk_days = 370
    chunks: List[pd.DataFrame] = []
    chunk_start = t0

    while chunk_start <= t1:
        chunk_end = min(chunk_start + pd.Timedelta(days=chunk_days - 1), t1)
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": chunk_start.strftime("%Y-%m-%d"),
            "end_date": chunk_end.strftime("%Y-%m-%d"),
            "hourly": hourly,
            "timezone": "UTC",
        }
        data = None
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=180)
                if r.status_code == 429 and attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if not r.ok:
                    logger.warning(
                        "Open-Meteo archive HTTP %s for %s–%s: %s",
                        r.status_code,
                        params["start_date"],
                        params["end_date"],
                        (r.text or "")[:600],
                    )
                    r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                logger.warning(
                    "Open-Meteo chunk %s–%s attempt %s failed: %s",
                    params["start_date"],
                    params["end_date"],
                    attempt + 1,
                    e,
                )
                if attempt == 2:
                    return None
                time.sleep(1.0 * (attempt + 1))

        if not data:
            return None
        if data.get("error"):
            logger.warning("Open-Meteo archive error payload: %s", str(data)[:800])
            return None

        h = data.get("hourly", {})
        part = _openmeteo_archive_hourly_to_df(h)
        if part is None or len(part) == 0:
            logger.warning("Open-Meteo chunk %s–%s returned empty hourly data", params["start_date"], params["end_date"])
            return None
        chunks.append(part)
        chunk_start = chunk_end + pd.Timedelta(days=1)
        time.sleep(0.35)

    if not chunks:
        return None
    df = pd.concat(chunks, ignore_index=True)
    df = df.drop_duplicates(subset=["hour_datetime"], keep="first")
    df = df.sort_values("hour_datetime").reset_index(drop=True)
    logger.info(f"Open-Meteo archive merged: {len(df)} rows from {len(chunks)} chunk(s)")
    return df

def _cloud_cover_to_type(cloud_cover: list) -> list:
    """Map 0–100 cloud_cover to 0–12 Cloud_Type style."""
    out = []
    for v in cloud_cover:
        try:
            x = float(v)
            out.append(min(12, max(0, int(round(x * 12 / 100)))))
        except (TypeError, ValueError):
            out.append(0)
    return out

def download_weather_forecast_openmeteo(lat: float, lon: float, days: int = 7) -> Optional[pd.DataFrame]:
    """
    Download hourly weather FORECAST from Open-Meteo Forecast API (free, no key).
    Returns same column structure as download_weather_openmeteo for model compatibility.
    """
    import requests
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,dew_point_2m,relative_humidity_2m,wind_speed_10m,surface_pressure,cloud_cover,shortwave_radiation",
        "forecast_days": days,
        "timezone": "UTC",
    }
    try:
        r = requests.get(url, params=params, timeout=120)
        if r.status_code == 429:
            time.sleep(5)
            r = requests.get(url, params=params, timeout=120)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning(f"Open-Meteo forecast request failed: {e}")
        return None
    h = data.get("hourly", {})
    if not h or "time" not in h:
        logger.warning("Open-Meteo forecast returned no hourly data")
        return None
    times = h["time"]
    df = pd.DataFrame({
        "hour_datetime": pd.to_datetime(times, utc=True).tz_localize(None),
        "Temperature": h.get("temperature_2m", [np.nan] * len(times)),
        "Dew Point": h.get("dew_point_2m", [np.nan] * len(times)),
        "Clearsky GHI": h.get("shortwave_radiation", [np.nan] * len(times)),
        "Cloud_Type": _cloud_cover_to_type(h.get("cloud_cover", [0] * len(times))),
        "Wind Speed": h.get("wind_speed_10m", [np.nan] * len(times)),
        "Pressure": h.get("surface_pressure", [np.nan] * len(times)),
    })
    for c in ["Temperature", "Dew Point", "Clearsky GHI", "Cloud_Type", "Wind Speed", "Pressure"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def resolve_city_coordinates(city_display: str) -> Tuple[float, float]:
    """
    Robustly resolve city coordinates using multiple strategies.
    
    Strategy order:
    1. Check CITY_COORDS dict (normalized city name)
    2. Check disk cache (city_coords_cache.json)
    3. Geocode using OpenStreetMap Nominatim API
    4. Cache geocoded result to disk
    
    Args:
        city_display: City display name like "Minneapolis MN" or "Chicago IL"
    
    Returns:
        (lat, lon) tuple
    
    Raises:
        HTTPException with status_code=400 if coordinates cannot be resolved
    """
    logger.info(f"resolve_city_coordinates: resolving coordinates for '{city_display}'")
    
    # Normalize city name for lookup (lowercase, remove state if present)
    city_normalized = normalize_city_name_for_matching(city_display).lower()
    logger.debug(f"Normalized city name: '{city_display}' -> '{city_normalized}'")
    
    # Strategy 1: Check CITY_COORDS dict (case-insensitive)
    if MODULES_AVAILABLE and CITY_COORDS:
        # Try exact match first
        if city_display.lower() in CITY_COORDS:
            coords = CITY_COORDS[city_display.lower()]
            logger.info(f"Coordinates from CITY_COORDS (exact): {coords}")
            return coords
        
        # Try normalized match (city name only, no state)
        if city_normalized in CITY_COORDS:
            coords = CITY_COORDS[city_normalized]
            logger.info(f"Coordinates from CITY_COORDS (normalized): {coords}")
            return coords
        
        # Try matching against keys in CITY_COORDS (case-insensitive)
        for key, coords in CITY_COORDS.items():
            if key.lower() == city_normalized or city_normalized.startswith(key.lower()):
                logger.info(f"Coordinates from CITY_COORDS (partial match '{key}'): {coords}")
                return coords
    
    # Strategy 2: Check disk cache
    cache_file = PROJECT_ROOT / "city_coords_cache.json"
    if cache_file.exists():
        try:
            import json
            with open(cache_file, 'r') as f:
                cache = json.load(f)
            
            # Try exact match
            if city_display in cache:
                coords = tuple(cache[city_display])
                logger.info(f"Coordinates from cache (exact): {coords}")
                return coords
            
            # Try normalized match
            if city_normalized in cache:
                coords = tuple(cache[city_normalized])
                logger.info(f"Coordinates from cache (normalized): {coords}")
                return coords
        except Exception as e:
            logger.warning(f"Error reading coordinate cache: {e}")
    
    # Strategy 3: Geocode using OpenStreetMap Nominatim
    logger.info(f"Coordinates not in CITY_COORDS or cache. Geocoding '{city_display}'...")
    try:
        import requests
        import time
        
        # Use Nominatim API (free, no key required, but rate-limited)
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": city_display,
            "format": "json",
            "limit": 1,
            "addressdetails": 1
        }
        headers = {
            "User-Agent": "EnergyAnomalyExplorer/1.0"  # Required by Nominatim
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if not data or len(data) == 0:
            raise ValueError(f"No results from geocoding for '{city_display}'")
        
        result = data[0]
        lat = float(result["lat"])
        lon = float(result["lon"])
        coords = (lat, lon)
        
        logger.info(f"Geocoded coordinates for '{city_display}': {coords}")
        
        # Cache to disk
        try:
            import json
            cache_file = PROJECT_ROOT / "city_coords_cache.json"
            cache = {}
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
            
            # Store both exact and normalized keys
            cache[city_display] = [lat, lon]
            cache[city_normalized] = [lat, lon]
            
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
            
            logger.info(f"Cached coordinates to {cache_file}")
        except Exception as e:
            logger.warning(f"Could not cache coordinates: {e}")
        
        # Rate limiting: Nominatim requires max 1 request per second
        time.sleep(1.1)
        
        return coords
        
    except Exception as e:
        error_msg = f"Could not resolve coordinates for '{city_display}': {str(e)}"
        logger.error(error_msg)
        # Raise HTTPException instead of returning None
        raise HTTPException(
            status_code=400,
            detail={
                "error": "coords_missing",
                "city": city_display,
                "step": "coords",
                "message": error_msg
            }
        )

def ensure_city_prepared(city_display: str) -> Tuple[Optional[Path], Optional[str], Optional[str], Optional[str]]:
    """
    Ensure city data is prepared (merged CSV exists).
    If not, run full pipeline: OpenEI download → weather (NSRDB or Open-Meteo fallback) → merge.
    
    Returns:
        (merged_file_path, error_step, error_message, weather_source_used)
        - weather_source_used: "NSRDB" | "OPEN_METEO" | "CACHE" | None
    """
    logger.info(f"=== ensure_city_prepared START: city_display='{city_display}' ===")
    
    # Get canonical city key from OpenEI (matches Streamlit naming)
    canonical_key = get_canonical_city_key(city_display)
    if not canonical_key:
        error_msg = f"Could not determine canonical key for '{city_display}'"
        logger.error(error_msg)
        return None, "openei_download", error_msg, None
    
    city_key = canonical_key.lower()  # Use lowercase for filenames
    logger.info(f"Canonical key: '{canonical_key}' -> filename key: '{city_key}'")
    
    # Check both locations: data/merged/ (new) and project root (legacy, matches Streamlit)
    merged_file_new = PROJECT_ROOT / "data" / "merged" / f"{city_key}_load_weather_merged.csv"
    merged_file_legacy = PROJECT_ROOT / f"{city_key}_load_weather_merged.csv"
    
    logger.info(f"Checking merged files:")
    logger.info(f"  - New location: {merged_file_new} (exists: {merged_file_new.exists()})")
    logger.info(f"  - Legacy location: {merged_file_legacy} (exists: {merged_file_legacy.exists()})")
    
    # If merged file exists, return path immediately (weather source = CACHE)
    if merged_file_legacy.exists():
        logger.info(f"Merged file already exists at legacy location: {merged_file_legacy}")
        return merged_file_legacy, None, None, "CACHE"
    if merged_file_new.exists():
        logger.info(f"Merged file already exists at new location: {merged_file_new}")
        return merged_file_new, None, None, "CACHE"
    
    logger.info(f"Merged file not found. Starting preparation pipeline for {city_display}...")
    
    if not MODULES_AVAILABLE:
        error_msg = "Required modules not available"
        logger.error(error_msg)
        return None, "openei_download", error_msg, None
    
    # Step 1: Download load profile if needed
    logger.info(f"=== Step 1: Load Profile Download ===")
    try:
        # Use canonical key for load profile filename (matches OpenEI naming)
        load_file = PROJECT_ROOT / "LoadProfiles" / f"{canonical_key}_SimulatedLoadProfile.csv"
        logger.info(f"Checking load file: {load_file}")
        
        if not load_file.exists():
            # Fallback to project root (legacy)
            load_file = PROJECT_ROOT / f"{canonical_key}_SimulatedLoadProfile.csv"
            logger.info(f"Fallback check: {load_file} (exists: {load_file.exists()})")
        
        if not load_file.exists():
            logger.info(f"Load profile not found. Fetching OpenEI resources...")
            cities_dict = fetch_openei_city_resources()
            logger.info(f"OpenEI resources fetched: {len(cities_dict)} cities")
            
            # Find city by display name
            city_info = None
            for key, info in cities_dict.items():
                if info.get("display") == city_display:
                    city_info = info
                    logger.info(f"Found city info: canonical_key='{key}', display='{info.get('display')}', url='{info.get('url')}'")
                    break
            
            if not city_info:
                error_msg = f"City '{city_display}' not found in OpenEI submission 515. Available cities: {list(cities_dict.keys())[:5]}..."
                logger.error(error_msg)
                return None, "openei_download", error_msg, None
            
            # Download load profile using canonical key for filename
            load_file = PROJECT_ROOT / "LoadProfiles" / f"{canonical_key}_SimulatedLoadProfile.csv"
            load_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Downloading load profile to: {load_file}")
            logger.info(f"Download URL: {city_info['url']}")
            
            success, msg = download_load_profile(city_display, city_info["url"], load_file)
            if not success:
                error_msg = f"Failed to download load profile: {msg}"
                logger.exception(error_msg)
                return None, "openei_download", error_msg, None
            logger.info(f"Downloaded load profile: {load_file}")
        else:
            logger.info(f"Load profile already exists: {load_file}")
    except Exception as e:
        error_msg = f"Error in load profile step: {str(e)}"
        logger.exception(error_msg)
        return None, "openei_download", error_msg, None
    
    # Step 2: Get coordinates (robust resolution with geocoding fallback)
    logger.info(f"=== Step 2: Coordinates ===")
    try:
        coords = resolve_city_coordinates(city_display)
        logger.info(f"Coordinates resolved: {coords} (lat={coords[0]}, lon={coords[1]})")
    except HTTPException as e:
        # HTTPException from resolve_city_coordinates means coordinates couldn't be resolved
        error_detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        error_msg = error_detail.get("message", f"Coordinates not available for {city_display}")
        logger.error(f"Coordinate resolution failed: {error_msg}")
        return None, "coords", error_msg, None
    except Exception as e:
        error_msg = f"Error in coordinates step: {str(e)}"
        logger.exception(error_msg)
        return None, "coords", error_msg, None
    
    # Step 3: Download weather data (NSRDB if creds present, else Open-Meteo fallback)
    logger.info(f"=== Step 3: Weather Download ===")
    weather_source_used: Optional[str] = None
    try:
        import os
        NSRDB_API_KEY = os.getenv("NSRDB_API_KEY", "")
        NSRDB_EMAIL = os.getenv("NSRDB_EMAIL", "")
        
        if NSRDB_API_KEY and NSRDB_EMAIL:
            logger.info(f"Calling fetch_nsrdb_weather for city_display='{city_display}'")
            success, message, weather_df = fetch_nsrdb_weather(
                city_display,
                api_key=NSRDB_API_KEY,
                email=NSRDB_EMAIL,
                project_root=PROJECT_ROOT
            )
            if success and weather_df is not None:
                weather_source_used = "NSRDB"
                logger.info(f"Weather data downloaded via NSRDB. Shape: {weather_df.shape}")
            else:
                weather_df = None
        else:
            logger.info("NSRDB creds missing, using Open-Meteo fallback.")
            weather_df = None
        
        if weather_df is None:
            # Use Open-Meteo fallback (no key)
            weather_dir = PROJECT_ROOT / "data" / "weather"
            weather_dir.mkdir(parents=True, exist_ok=True)
            cache_path = weather_dir / f"{city_key}_weather_hourly.csv"
            if cache_path.exists():
                try:
                    weather_df = pd.read_csv(cache_path, low_memory=False)
                    weather_df["hour_datetime"] = pd.to_datetime(weather_df["hour_datetime"], errors="coerce")
                    weather_df = weather_df.dropna(subset=["hour_datetime"])
                    weather_source_used = "CACHE"
                    logger.info(f"Using cached Open-Meteo weather: {cache_path} ({len(weather_df)} rows)")
                except Exception as e:
                    logger.warning(f"Could not load cached weather: {e}")
                    weather_df = None
            if weather_df is None:
                coords = resolve_city_coordinates(city_display)
                lat, lon = coords[0], coords[1]
                weather_df = download_weather_openmeteo(lat, lon, "1998-01-01", "2014-12-31")
                if weather_df is None or len(weather_df) == 0:
                    error_msg = "Weather download failed (NSRDB creds missing and Open-Meteo fallback failed)."
                    logger.error(error_msg)
                    return None, "weather", error_msg, None
                weather_source_used = "OPEN_METEO"
                try:
                    weather_df.to_csv(cache_path, index=False)
                    logger.info(f"Cached Open-Meteo weather to {cache_path}")
                except Exception as e:
                    logger.warning(f"Could not cache weather: {e}")
        
        if weather_df is None or len(weather_df) == 0:
            error_msg = "Weather data unavailable (NSRDB failed and Open-Meteo fallback produced no data)."
            logger.error(error_msg)
            return None, "weather", error_msg, None
        # Ensure required columns exist for merge (build_merge expects these)
        for col, default in [("Clearsky GHI", np.nan), ("Cloud_Type", 0)]:
            if col not in weather_df.columns:
                weather_df[col] = default
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error in weather download step: {str(e)}"
        logger.exception(error_msg)
        return None, "weather", error_msg, None
    
    # step3_weather_source persists for final return
    step3_weather_source = weather_source_used
    
    # Step 4: Build merged dataset
    logger.info(f"=== Step 4: Merge Dataset ===")
    try:
        # CRITICAL: Pass canonical_key (not city_display) to build_and_save_merged
        # because build_and_save_merged uses city.lower() for filename
        # We want it to create: canonical_key.lower()_load_weather_merged.csv
        # Example: "Chicago" -> "chicago_load_weather_merged.csv" (matches existing file)
        logger.info(f"Calling build_and_save_merged with canonical_key='{canonical_key}' (not display name)")
        logger.info(f"load_file={load_file}")
        build_success, build_message = build_and_save_merged(
            canonical_key,  # Pass canonical key, not display name!
            project_root=PROJECT_ROOT,
            use_nsrdb=True,
            weather_df=weather_df,
            load_file_path=load_file
        )
        
        if not build_success:
            error_msg = f"Merge failed: {build_message}"
            logger.exception(error_msg)
            return None, "merge", error_msg, None
        logger.info(f"Merge successful: {build_message}")
    except Exception as e:
        error_msg = f"Error in merge step: {str(e)}"
        logger.exception(error_msg)
        return None, "merge", error_msg, None
    
    # Step 5: Verify merged file was created
    logger.info(f"=== Step 5: Verify Merged File ===")
    try:
        # build_and_save_merged saves to project_root / f"{city_lower}_load_weather_merged.csv"
        # where city_lower = canonical_key.lower() (since we passed canonical_key)
        # So it should create: city_key_load_weather_merged.csv
        merged_file_legacy = PROJECT_ROOT / f"{city_key}_load_weather_merged.csv"
        logger.info(f"Checking for merged file at: {merged_file_legacy}")
        
        if merged_file_legacy.exists():
            logger.info(f"Merged file created at legacy location: {merged_file_legacy}")
            # Optionally move to consistent location
            try:
                import shutil
                merged_file_new.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(merged_file_legacy), str(merged_file_new))
                logger.info(f"Moved merged file to: {merged_file_new}")
                return merged_file_new, None, None, step3_weather_source
            except Exception as e:
                logger.warning(f"Could not move file, using legacy location: {e}")
                return merged_file_legacy, None, None, step3_weather_source
        else:
            # Fallback: Check if build_and_save_merged used a different pattern
            # (shouldn't happen if we passed canonical_key correctly)
            city_display_lower = city_display.lower()
            merged_file_display_lower = PROJECT_ROOT / f"{city_display_lower}_load_weather_merged.csv"
            logger.info(f"Fallback check: {merged_file_display_lower} (exists: {merged_file_display_lower.exists()})")
            
            if merged_file_display_lower.exists():
                logger.warning(f"Found merged file with display name lowercase (unexpected): {merged_file_display_lower}")
                # Rename to canonical key for consistency
                try:
                    import shutil
                    shutil.move(str(merged_file_display_lower), str(merged_file_legacy))
                    logger.info(f"Renamed to canonical key: {merged_file_legacy}")
                    return merged_file_legacy, None, None, step3_weather_source
                except Exception as e:
                    logger.warning(f"Could not rename, using existing file: {e}")
                    return merged_file_display_lower, None, None, step3_weather_source
            
            error_msg = f"Merged file not found after build. Expected: {merged_file_legacy}"
            logger.error(error_msg)
            return None, "merge", error_msg, None
        
        # Determine final merged file path
        final_merged_file = merged_file_legacy if merged_file_legacy.exists() else merged_file_new
    except Exception as e:
        error_msg = f"Error verifying merged file: {str(e)}"
        logger.exception(error_msg)
        return None, "read_csv", error_msg, None
    
    # Final verification: Load and log merged dataset stats
    logger.info(f"=== Pipeline Complete: Verifying Merged Dataset ===")
    try:
        if final_merged_file and final_merged_file.exists():
            df_verify = pd.read_csv(final_merged_file, low_memory=False)
            logger.info(f"✓ Merged dataset verified:")
            logger.info(f"  - File: {final_merged_file}")
            logger.info(f"  - Rows: {len(df_verify):,}")
            logger.info(f"  - Columns: {len(df_verify.columns)}")
            
            # Parse datetime to get date range
            if 'hour_datetime' in df_verify.columns:
                df_verify['hour_datetime'] = pd.to_datetime(df_verify['hour_datetime'], errors='coerce')
                valid_dates = df_verify['hour_datetime'].dropna()
                if len(valid_dates) > 0:
                    logger.info(f"  - Date range: {valid_dates.min()} to {valid_dates.max()}")
            
            # Count building columns
            building_cols = get_building_columns(df_verify)
            logger.info(f"  - Building columns: {len(building_cols)}")
            
            logger.info(f"=== Pipeline Summary for {city_display} ===")
            logger.info(f"  1. Load Profile: ✓ (canonical_key='{canonical_key}')")
            logger.info(f"  2. Coordinates: ✓ (source logged above)")
            try:
                weather_rows = weather_df.shape[0] if weather_df is not None else 'N/A'
            except NameError:
                weather_rows = 'N/A'
            logger.info(f"  3. Weather Download: ✓ (rows: {weather_rows})")
            logger.info(f"  4. Merge: ✓ (final rows: {len(df_verify):,})")
            logger.info(f"  5. Verification: ✓ (merged file exists)")
    except Exception as e:
        logger.warning(f"Could not verify merged dataset stats: {e}")
    
    logger.info(f"=== ensure_city_prepared COMPLETE: {city_display} ===")
    return (merged_file_new if merged_file_new.exists() else merged_file_legacy), None, None, step3_weather_source

def get_buildings_from_available_data(city: str) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[str], Optional[str]]:
    """
    Get buildings from available data sources WITHOUT requiring coordinates.
    Tries merged dataset first, then load profile.
    
    Returns:
        (dataframe, error_step, error_message, source_used)
        - source_used: "merged", "load_profile", or None if error
    """
    logger.info(f"get_buildings_from_available_data: city='{city}'")
    
    # Get canonical key for filename lookup
    canonical_key = get_canonical_city_key(city)
    if not canonical_key:
        error_msg = f"Could not determine canonical key for '{city}'"
        logger.error(error_msg)
        return None, "openei_download", error_msg, None
    
    city_key = canonical_key.lower()
    logger.info(f"Using canonical key '{canonical_key}' -> filename key '{city_key}'")
    
    # Strategy 1: Try merged dataset (if exists, no preparation needed)
    merged_file_new = PROJECT_ROOT / "data" / "merged" / f"{city_key}_load_weather_merged.csv"
    merged_file_legacy = PROJECT_ROOT / f"{city_key}_load_weather_merged.csv"
    
    merged_file = None
    if merged_file_legacy.exists():
        merged_file = merged_file_legacy
    elif merged_file_new.exists():
        merged_file = merged_file_new
    
    if merged_file:
        try:
            logger.info(f"Reading merged CSV: {merged_file}")
            df = pd.read_csv(merged_file, low_memory=False)
            logger.info(f"Merged CSV loaded: {len(df)} rows, {len(df.columns)} columns")
            
            # Parse datetime if needed
            df, strategy, error_info = robust_parse_datetime(df, city_key, merged_file)
            if df is None or len(df) == 0:
                logger.warning(f"DataFrame empty after datetime parsing, trying load profile...")
            else:
                logger.info(f"Successfully loaded buildings from merged dataset: {merged_file}")
                return df, None, None, "merged"
        except Exception as e:
            logger.warning(f"Error reading merged file {merged_file}: {e}, trying load profile...")
    
    # Strategy 2: Try load profile (doesn't require coordinates)
    load_file = PROJECT_ROOT / "LoadProfiles" / f"{canonical_key}_SimulatedLoadProfile.csv"
    if not load_file.exists():
        # Try legacy location
        load_file = PROJECT_ROOT / f"{canonical_key}_SimulatedLoadProfile.csv"
    
    if load_file.exists():
        try:
            logger.info(f"Reading load profile: {load_file}")
            # Use openei_loader if available for proper parsing
            if MODULES_AVAILABLE:
                try:
                    from openei_loader import load_openei_csv
                    df = load_openei_csv(load_file)
                except ImportError:
                    df = pd.read_csv(load_file, header=0, low_memory=False)
                    df.columns = df.columns.str.strip()
                    df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False)]
            else:
                df = pd.read_csv(load_file, header=0, low_memory=False)
                df.columns = df.columns.str.strip()
                df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False)]
            
            if df is None or len(df) == 0:
                error_msg = f"Load profile file is empty: {load_file}"
                logger.error(error_msg)
                return None, "read_csv", error_msg, None
            
            logger.info(f"Load profile loaded: {len(df)} rows, {len(df.columns)} columns")
            logger.info(f"Successfully loaded buildings from load profile: {load_file}")
            return df, None, None, "load_profile"
        except Exception as e:
            error_msg = f"Error reading load profile {load_file}: {str(e)}"
            logger.exception(error_msg)
            return None, "read_csv", error_msg, None
    
    # Neither file exists
    error_msg = f"No merged dataset or load profile found for '{city}'. Run prepare (requires coords) to create merged dataset."
    logger.error(error_msg)
    return None, "no_data_available", error_msg, None

def load_merged_data(city: str) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[str], Optional[str]]:
    """
    Load merged dataset for a city. Auto-prepares if missing.
    
    Returns:
        (dataframe, error_step, error_message, weather_source_used)
        weather_source_used: "NSRDB" | "OPEN_METEO" | "CACHE" | None
    """
    logger.info(f"load_merged_data: city='{city}'")
    
    # Get canonical key for filename lookup
    canonical_key = get_canonical_city_key(city)
    if not canonical_key:
        error_msg = f"Could not determine canonical key for '{city}'"
        logger.error(error_msg)
        return None, "openei_download", error_msg, None
    
    city_key = canonical_key.lower()
    logger.info(f"Using canonical key '{canonical_key}' -> filename key '{city_key}'")
    
    # Check both locations: data/merged/ (new) and project root (legacy, matches Streamlit)
    merged_file_new = PROJECT_ROOT / "data" / "merged" / f"{city_key}_load_weather_merged.csv"
    merged_file_legacy = PROJECT_ROOT / f"{city_key}_load_weather_merged.csv"
    
    logger.info(f"Checking merged files:")
    logger.info(f"  - {merged_file_new} (exists: {merged_file_new.exists()})")
    logger.info(f"  - {merged_file_legacy} (exists: {merged_file_legacy.exists()})")
    
    merged_file = None
    weather_source_used: Optional[str] = "CACHE"  # existing merged file implies cached data
    if merged_file_legacy.exists():
        merged_file = merged_file_legacy
        logger.info(f"Found merged file at legacy location: {merged_file}")
    elif merged_file_new.exists():
        merged_file = merged_file_new
        logger.info(f"Found merged file at new location: {merged_file}")
    
    if not merged_file:
        # Auto-prepare city
        logger.info(f"Merged file not found, auto-preparing city...")
        merged_file, error_step, error_message, weather_source_used = ensure_city_prepared(city)
        if merged_file is None:
            logger.error(f"Auto-preparation failed: step={error_step}, message={error_message}")
            return None, error_step, error_message, None
    
    # Load and validate CSV
    try:
        logger.info(f"Reading merged CSV: {merged_file}")
        df = pd.read_csv(merged_file, low_memory=False)
        logger.info(f"CSV loaded: {len(df)} rows, {len(df.columns)} columns")
        logger.info(f"All columns: {list(df.columns)}")
        
        # Diagnostic: Log datetime-related columns and sample values
        datetime_keywords = ['date', 'time', 'hour', 'year', 'month', 'day', 'minute']
        datetime_cols = [col for col in df.columns if any(kw in col.lower() for kw in datetime_keywords)]
        logger.info(f"Datetime-related columns found: {datetime_cols}")
        
        if datetime_cols:
            sample_size = min(3, len(df))
            for col in datetime_cols[:5]:  # Log first 5 datetime columns
                sample_values = df[col].head(sample_size).tolist()
                logger.info(f"  {col} (dtype={df[col].dtype}): sample values = {sample_values}")
        
        # Robust datetime parsing with fallbacks
        df, strategy, error_info = robust_parse_datetime(df, city_key, merged_file)
        if error_info:
            # Return structured error
            error_msg = f"Failed to parse datetime. Detected columns: {error_info.get('detected_columns', [])}. Sample values: {error_info.get('sample_values', {})}"
            logger.error(error_msg)
            return None, "read_csv", error_msg, None
        
        logger.info(f"Datetime parsed using strategy: {strategy}")
        
        # Final validation: ensure hour_datetime exists and is valid
        if 'hour_datetime' not in df.columns:
            error_msg = "hour_datetime column missing after parsing"
            logger.error(error_msg)
            return None, "read_csv", error_msg, None
        
        # Check if dataframe is empty after cleaning (should never happen now)
        if len(df) == 0:
            error_msg = "Dataframe is empty after datetime cleaning (this should not happen)"
            logger.error(error_msg)
            return None, "read_csv", error_msg, None
        
        logger.info(f"Successfully loaded merged data: {len(df)} rows with valid hour_datetime")
        return df, None, None, weather_source_used
        
    except Exception as e:
        error_msg = f"Error reading CSV: {str(e)}"
        logger.exception(error_msg)
        return None, "read_csv", error_msg, None

# API Endpoints
def normalize_city_list(payload) -> List[str]:
    """
    Robust normalizer that converts any OpenEI city payload into a List[str].
    
    Handles:
    - list[str] → return as-is
    - list[dict] → extract city name from common keys
    - dict with nested lists → extract from nested structure
    - dict mapping city keys to city info → extract display names
    - string (JSON) → parse and normalize
    """
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Debug: log payload type and sample
    payload_type = type(payload).__name__
    if isinstance(payload, str):
        sample = payload[:200] if len(payload) > 200 else payload
        logger.debug(f"Payload type: {payload_type}, sample (first 200 chars): {sample}")
    elif isinstance(payload, (list, tuple)) and len(payload) > 0:
        sample = payload[:3] if len(payload) > 3 else payload
        logger.debug(f"Payload type: {payload_type}, sample (first 3 items): {sample}")
    elif isinstance(payload, dict):
        sample = dict(list(payload.items())[:3])
        logger.debug(f"Payload type: {payload_type}, sample (first 3 keys): {sample}")
    else:
        logger.debug(f"Payload type: {payload_type}, value: {payload}")
    
    # Case 1: Already list[str]
    if isinstance(payload, (list, tuple)):
        if len(payload) == 0:
            return []
        
        # Check if all items are strings
        if all(isinstance(item, str) for item in payload):
            return sorted(list(set(payload)))  # Deduplicate and sort
        
        # Case 2: list[dict] - extract city names
        if all(isinstance(item, dict) for item in payload):
            city_names = []
            for item in payload:
                # Try common keys
                for key in ["city", "name", "label", "title", "display_name", "display"]:
                    if key in item and isinstance(item[key], str):
                        city_names.append(item[key])
                        break
            if city_names:
                return sorted(list(set(city_names)))
    
    # Case 3: dict with nested lists
    if isinstance(payload, dict):
        # Check for nested city lists
        for key in ["cities", "data", "results", "items"]:
            if key in payload and isinstance(payload[key], (list, tuple)):
                return normalize_city_list(payload[key])
        
        # Case 4: dict mapping city keys to city info (like fetch_openei_city_resources returns)
        # Format: {"Houston": {"display": "Houston TX", "url": "..."}, ...}
        city_names = []
        for key, value in payload.items():
            if isinstance(value, dict):
                # Try to extract display name from nested dict
                for display_key in ["display", "display_name", "name", "label", "title"]:
                    if display_key in value and isinstance(value[display_key], str):
                        city_names.append(value[display_key])
                        break
                else:
                    # If no display key found, use the outer key as city name
                    if isinstance(key, str):
                        city_names.append(key)
            elif isinstance(value, str):
                # Direct mapping: {"Houston": "Houston TX"}
                city_names.append(value)
            elif isinstance(key, str):
                # Use key as city name
                city_names.append(key)
        
        if city_names:
            return sorted(list(set(city_names)))
    
    # Case 5: string (JSON string) - try to parse
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            return normalize_city_list(parsed)
        except (json.JSONDecodeError, ValueError):
            # If it's just a plain string, return as single-item list
            return [payload] if payload.strip() else []
    
    # Fallback: return empty list
    logger.warning(f"Could not normalize payload of type {payload_type}, returning empty list")
    return []


@app.get("/api/cities")
async def get_cities() -> CityResponse:
    """Get list of available cities from OpenEI."""
    import logging
    
    logger = logging.getLogger(__name__)
    
    if cache["cities"] is not None:
        return CityResponse(cities=cache["cities"])

    disk_cities = _try_load_cities_list_from_disk()
    if disk_cities is not None:
        cache["cities"] = disk_cities
        logger.info(f"Loaded {len(disk_cities)} cities from disk cache")
        return CityResponse(cities=disk_cities)
    
    if not MODULES_AVAILABLE:
        raise HTTPException(status_code=500, detail="OpenEI module not available")
    
    try:
        # Fetch cities from OpenEI
        cities_raw = fetch_openei_city_resources()
        
        # Normalize to list of city name strings
        city_names = normalize_city_list(cities_raw)
        
        if not city_names:
            logger.warning("No cities found after normalization. Raw payload type: %s", type(cities_raw).__name__)
            # Return empty list instead of error
            cache["cities"] = []
            return CityResponse(cities=[])
        
        # Cache and return
        cache["cities"] = city_names
        _save_cities_list_to_disk(city_names)
        logger.info(f"Successfully fetched {len(city_names)} cities")
        return CityResponse(cities=city_names)
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error fetching cities: {e}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Error fetching cities: {str(e)}")

@app.post("/api/prepare-city")
async def prepare_city(request: PrepareCityRequest, background_tasks: BackgroundTasks) -> StatusResponse:
    """
    Explicitly prepare city (download + merge). 
    Uses ensure_city_prepared() internally for consistency.
    Idempotent: returns already_prepared if merged file exists.
    """
    city = request.city
    canonical_key = get_canonical_city_key(city)
    if not canonical_key:
        return StatusResponse(
            status="error",
            message=f"Could not resolve OpenEI city key for '{city}'.",
            ready=False
        )
    city_key = canonical_key.lower()

    merged_file_consistent = PROJECT_ROOT / "data" / "merged" / f"{city_key}_load_weather_merged.csv"
    merged_file_legacy = PROJECT_ROOT / f"{city_key}_load_weather_merged.csv"

    if merged_file_consistent.exists() or merged_file_legacy.exists():
        return StatusResponse(
            status="already_prepared",
            message=f"Merged dataset already exists for {city}",
            ready=True
        )

    merged_path, err_step, err_msg, _ws = ensure_city_prepared(city)

    if merged_path is None:
        return StatusResponse(
            status="error",
            message=err_msg or f"Failed to prepare city {city} (step={err_step}).",
            ready=False
        )

    return StatusResponse(
        status="prepared",
        message=f"Dataset prepared successfully for {city}",
        ready=True
    )

@app.get("/api/buildings")
async def get_buildings(city: str) -> BuildingResponse:
    """
    Get list of building columns for a city.
    Does NOT require coordinates - reads from merged dataset or load profile if available.
    """
    logger.info(f"GET /api/buildings?city={city}")
    
    if city in cache["buildings"]:
        logger.info(f"Returning cached buildings for {city}: {len(cache['buildings'][city])} buildings")
        return BuildingResponse(buildings=cache["buildings"][city])
    
    # Get canonical key for logging
    canonical_key = get_canonical_city_key(city)
    city_key = canonical_key.lower() if canonical_key else None
    logger.info(f"City '{city}' mapped to canonical key '{canonical_key}' (filename key: '{city_key}')")
    
    # Log file paths that will be checked
    if city_key:
        merged_file_new = PROJECT_ROOT / "data" / "merged" / f"{city_key}_load_weather_merged.csv"
        merged_file_legacy = PROJECT_ROOT / f"{city_key}_load_weather_merged.csv"
        load_file = PROJECT_ROOT / "LoadProfiles" / f"{canonical_key}_SimulatedLoadProfile.csv"
        logger.info(f"Checking files:")
        logger.info(f"  - Merged (new): {merged_file_new} (exists: {merged_file_new.exists()})")
        logger.info(f"  - Merged (legacy): {merged_file_legacy} (exists: {merged_file_legacy.exists()})")
        logger.info(f"  - Load profile: {load_file} (exists: {load_file.exists()})")
    
    # Get buildings from available data (does NOT require coordinates)
    df, error_step, error_message, source_used = get_buildings_from_available_data(city)
    
    if df is None:
        logger.error(f"Failed to load data for '{city}': step={error_step}, message={error_message}")
        # Return structured 4xx error (not 500) for missing data
        status_code = 404 if error_step == "no_data_available" else 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": error_step or "no_data_available",
                "city": city,
                "message": error_message or "No merged dataset or load profile found"
            }
        )
    
    building_cols = get_building_columns(df)
    logger.info(f"Found {len(building_cols)} building columns from {source_used} (rows: {len(df)})")
    cache["buildings"][city] = building_cols
    logger.info(f"Returning {len(building_cols)} buildings for {city} (source: {source_used})")
    return BuildingResponse(buildings=building_cols)

class YearResponse(BaseModel):
    years: List[int]

def _nsrdb_credentials_detail(city: str) -> dict:
    """Structured error detail for missing NSRDB credentials."""
    return {
        "error": "missing_nsrdb_credentials",
        "step": "weather",
        "message": "NSRDB_API_KEY and NSRDB_EMAIL are required to download weather for new cities. Set env vars and retry.",
        "how_to_fix": [
            "export NSRDB_API_KEY=...",
            "export NSRDB_EMAIL=..."
        ],
        "city": city,
    }

@app.get("/api/years")
async def get_years(city: str, building: str) -> YearResponse:
    """Get list of available years for a city and building. Auto-prepares city if needed."""
    # Auto-prepare city if needed (ensure_city_prepared is called inside load_merged_data)
    df, error_step, error_message, _ = load_merged_data(city)
    if df is None:
        # Return 400 (not 500) for expected failures like missing NSRDB creds
        if error_step == "missing_nsrdb_credentials":
            raise HTTPException(status_code=400, detail=_nsrdb_credentials_detail(city))
        status_code = 400 if error_step in ("coords", "missing_nsrdb_credentials") else 500
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": error_step or "prepare_failed",
                "city": city,
                "step": error_step or "unknown",
                "message": error_message or "Failed to load or prepare data"
            }
        )
    
    if building not in df.columns:
        raise HTTPException(status_code=400, detail=f"Building '{building}' not found in data")
    
    # Extract unique years from hour_datetime
    if 'hour_datetime' not in df.columns:
        raise HTTPException(status_code=400, detail="hour_datetime column not found")
    
    years = sorted(df['hour_datetime'].dt.year.unique().tolist())
    logger.info(f"Returning {len(years)} years for {city}/{building}: {years[:5]}...")
    return YearResponse(years=years)

@app.post("/api/run")
async def run_analysis(request: RunRequest) -> Dict[str, Any]:
    """Run regression and anomaly detection, return results."""
    city = request.city
    building = request.building
    
    # Load data (auto-prepares city if needed)
    logger.info(f"=== Starting analysis for {city}/{building} ===")
    logger.info(f"Pipeline: City='{city}', Building='{building}'")
    
    # Ensure merged dataset exists (auto-prepare if needed)
    df, error_step, error_message, weather_source_used = load_merged_data(city)
    if df is None:
        # Return 400 (not 500) for expected failures: coords, missing NSRDB creds
        if error_step == "missing_nsrdb_credentials":
            raise HTTPException(status_code=400, detail=_nsrdb_credentials_detail(city))
        status_code = 400 if error_step == "coords" else 500
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": error_step or "prepare_failed",
                "city": city,
                "step": error_step or "unknown",
                "message": error_message or "Failed to load or prepare data"
            }
        )
    
    logger.info(f"Loaded merged data: {len(df)} rows (weather_source={weather_source_used})")
    
    if building not in df.columns:
        raise HTTPException(status_code=400, detail=f"Building '{building}' not found in data")
    
    # Apply year filter if specified
    rows_before_filter = len(df)
    if request.selected_year and request.selected_year != "All":
        try:
            year = int(request.selected_year)
            df = df[df['hour_datetime'].dt.year == year].copy()
            logger.info(f"Applied year filter ({year}): {rows_before_filter} rows -> {len(df)} rows")
        except (ValueError, TypeError):
            logger.warning(f"Could not parse year filter '{request.selected_year}', keeping all data")
            pass  # Keep all data if year parsing fails
    else:
        logger.info(f"No year filter applied: {rows_before_filter} rows")
    
    if len(df) == 0:
        raise HTTPException(status_code=400, detail=f"No data for year {request.selected_year}")
    
    # Reset index to ensure 0-based positional indexing works correctly
    # This is critical when filtering to a single year, as the original index labels
    # (e.g., 43824-52583 for year 2003) would cause out-of-bounds errors when used
    # as positions in numpy arrays of length ~8760
    df = df.reset_index(drop=True)
    logger.info(f"Data after year filter and index reset: {len(df)} rows, index range: {df.index.min()} to {df.index.max()}")
    
    # Log df_model datetime range for debugging
    if len(df) > 0:
        df_min_dt = df['hour_datetime'].min()
        df_max_dt = df['hour_datetime'].max()
        logger.info(f"df_model datetime range: {df_min_dt} to {df_max_dt}")
    
    # Feature selection
    building_cols = get_building_columns(df)
    
    # Determine feature selection method
    is_fixed = (request.feature_mode == "Fixed 3-feature")
    
    if is_fixed:
        # Use fixed 3 features
        feature_map = {
            "Temperature": ["Temperature", "temperature", "temp", "Temp"],
            "Dew Point": ["Dew Point", "DewPoint", "dew_point", "dewpoint"],
            "Clearsky GHI": ["Clearsky GHI", "ClearskyGHI", "clearsky_ghi", "ClearskyGHI"],
        }
        feature_cols = []
        for canonical, variants in feature_map.items():
            for variant in variants:
                if variant in df.columns:
                    feature_cols.append(variant)
                    break
        if len(feature_cols) < 3:
            raise HTTPException(status_code=400, detail="Required weather features not available")
        selected_features = feature_cols[:3]
        method_used = "Fixed 3-feature"
    else:
        # Auto-select features
        if not MODULES_AVAILABLE:
            raise HTTPException(status_code=500, detail="Regression engine not available")
        
        candidate_info = get_candidate_weather_features(
            df, building, exclude_cols=[], building_cols=building_cols
        )
        
        selection_method = "elasticnet" if request.feature_mode == "Auto-select (ElasticNet)" else "correlation"
        
        selection_result = select_weather_features(
            df, building,
            feature_map=candidate_info.get("feature_map", {}),
            method=selection_method,
            top_k=request.top_k,
            include_cloud_type=request.include_cloud_type,
            building_cols=building_cols
        )
        
        selected_features = selection_result.get("selected_features", [])
        method_used = selection_result.get("method_used", selection_method)
    
    if len(selected_features) == 0:
        raise HTTPException(status_code=400, detail="No features selected")
    
    # Fit regression — ONE model used for BOTH display metrics AND anomaly detection
    fit_result = fit_regression(df, building, selected_features)
    
    if fit_result.get("error"):
        logger.error(f"Regression fitting failed: {fit_result['error']}")
        raise HTTPException(
            status_code=400,
            detail={"error": "regression_failed", "message": fit_result["error"]}
        )
    
    metrics = fit_result.get("metrics", {})
    r2 = metrics.get("r2")
    
    if fit_result.get("_model") and fit_result.get("_scaler"):
        cache_key = f"{request.city}|{building}"
        cache["model_cache"][cache_key] = {
            "model": fit_result["_model"],
            "scaler": fit_result["_scaler"],
            "features": selected_features,
            "residual_std": fit_result.get("_residual_std", 0),
            "r2": r2,
            "city": request.city,
            "building": building,
        }
        logger.info(f"Cached model for forecast: {cache_key}")
        persist_model_for_forecast(request.city, building, cache["model_cache"][cache_key])
    
    y_std = df[building].std() if building in df.columns else 0
    y_mean = df[building].mean() if building in df.columns else 0
    
    logger.info(f"Regression metrics: r2={r2}, rmse={metrics.get('rmse')}, mae={metrics.get('mae')}")
    logger.info(f"Target stats: mean={y_mean:.2f}, std={y_std:.2f}, rows={len(df)}")
    
    regression_warning = None
    if r2 is not None and (pd.isna(r2) or not np.isfinite(r2)):
        regression_warning = "R² is NaN or infinite (likely constant target or insufficient variance)"
        metrics = {"r2": None, "rmse": None, "mae": None}
    elif r2 is None:
        regression_warning = "R² unavailable (constant target or insufficient variance)"
    elif y_std < 1e-6:
        regression_warning = f"Target has near-zero variance (std={y_std:.6f}), metrics may be unreliable"
    
    regression_result = {
        "selected_features": selected_features,
        "method_used": method_used,
        "metrics": metrics,
        "coef_table": fit_result.get("coef_table", pd.DataFrame()).to_dict(orient="records") if isinstance(fit_result.get("coef_table"), pd.DataFrame) else [],
        "confidence": fit_result.get("confidence", get_regression_confidence(r2 if r2 is not None else 0)),
        "regression_warning": regression_warning,
        "diagnostics": {
            "rows_before_filter": rows_before_filter,
            "rows_after_year_filter": len(df),
            "y_mean": float(y_mean),
            "y_std": float(y_std),
            "y_min": float(df[building].min()) if building in df.columns else None,
            "y_max": float(df[building].max()) if building in df.columns else None,
            "train_size": fit_result.get("train_size", 0),
            "test_size": fit_result.get("test_size", 0),
            "model_type": fit_result.get("model_type", "unknown")
        }
    }
    
    # Anomaly detection — uses predictions from the SAME regression model displayed above
    logger.info(f"Preparing anomaly detection from regression predictions")
    
    y_pred_full = fit_result['y_pred']
    y_actual = pd.to_numeric(df[building], errors='coerce').values
    
    valid_mask = ~np.isnan(y_pred_full) & ~np.isnan(y_actual)
    n_valid = int(valid_mask.sum())
    rows_before = len(df)
    rows_dropped = rows_before - n_valid
    
    logger.info(f"Valid rows for anomaly detection: {n_valid}/{rows_before} ({rows_dropped} dropped due to NaN)")
    
    MIN_SAMPLES = 200
    if n_valid < MIN_SAMPLES:
        error_detail = {
            "error": "insufficient_data_after_cleaning",
            "message": f"After cleaning NaN values, only {n_valid} samples remain (minimum required: {MIN_SAMPLES})",
            "rows_before_cleaning": rows_before,
            "rows_after_cleaning": n_valid,
            "rows_dropped": rows_dropped,
        }
        logger.error(f"Insufficient data after cleaning: {error_detail}")
        raise HTTPException(status_code=400, detail=error_detail)
    
    y = y_actual[valid_mask]
    y_pred = y_pred_full[valid_mask]
    df_model = df[valid_mask].copy()
    
    logger.info(f"Created df_model with {len(df_model)} rows")
    
    residuals = y - y_pred
    res_std = residuals.std()
    if res_std < 1e-10:
        z_scores = np.zeros_like(residuals)
        logger.warning("Residual std near zero, z-scores set to 0")
    else:
        z_scores = (residuals - residuals.mean()) / res_std
    
    assert len(y) == len(y_pred) == len(df_model) == len(residuals) == len(z_scores), \
        f"Length mismatch: y={len(y)}, y_pred={len(y_pred)}, df_model={len(df_model)}"
    logger.info(f"✓ All vectors validated: length {len(df_model)}")
    
    anomaly_df = pd.DataFrame({
        'hour_datetime': df_model['hour_datetime'].values,
        'actual': y,
        'predicted': y_pred,
        'residual': residuals,
        'z_score': z_scores,
        'abs_z': np.abs(z_scores),
        'abs_residual': np.abs(residuals),
        'anomaly': np.abs(z_scores) > request.z_threshold
    })
    
    # Validate anomaly_df length matches
    assert len(anomaly_df) == len(df_model), f"anomaly_df length {len(anomaly_df)} != df_model length {len(df_model)}"
    logger.info(f"✓ anomaly_df created with {len(anomaly_df)} rows")
    
    if 'Cloud_Type' in df_model.columns:
        anomaly_df['Cloud_Type'] = df_model['Cloud_Type'].values
    
    # Step 7: Filter anomalies by z_threshold FIRST, then apply top_n
    logger.info(f"Filtering anomalies by z_threshold={request.z_threshold}")
    filtered_anomalies = anomaly_df[anomaly_df['abs_z'] >= request.z_threshold].copy()
    
    # Log datetime ranges for debugging
    if len(filtered_anomalies) > 0:
        min_dt = filtered_anomalies['hour_datetime'].min()
        max_dt = filtered_anomalies['hour_datetime'].max()
        logger.info(f"Filtered anomalies datetime range: {min_dt} to {max_dt} ({len(filtered_anomalies)} rows)")
    else:
        logger.warning("No anomalies after threshold filter")
    
    logger.info(f"Anomalies after threshold filter: {len(filtered_anomalies)} rows (from {len(anomaly_df)} total)")
    
    # Recalculate anomaly flag and rate based on threshold
    anomaly_df['anomaly'] = anomaly_df['abs_z'] >= request.z_threshold
    anomaly_rate = float(anomaly_df['anomaly'].mean() * 100)
    anomaly_hours = int(anomaly_df['anomaly'].sum())
    logger.info(f"Anomaly rate after threshold filter: {anomaly_rate:.2f}% ({anomaly_hours} hours)")
    
    # Get top N anomalies per year FROM filtered set
    # If year filter is "All", get top-N per year. Otherwise, get top-N from filtered year.
    if len(filtered_anomalies) > 0:
        if request.selected_year and request.selected_year != "All":
            # Single year: just get top-N from that year
            top_anomalies_df = filtered_anomalies.nlargest(request.top_n, 'abs_z').copy()
            logger.info(f"Top {request.top_n} anomalies for year {request.selected_year}: {len(top_anomalies_df)} rows")
        else:
            # All years: get top-N per year, then combine
            top_anomalies = []
            for year in sorted(filtered_anomalies['hour_datetime'].dt.year.unique()):
                year_data = filtered_anomalies[filtered_anomalies['hour_datetime'].dt.year == year].copy()
                top_year = year_data.nlargest(request.top_n, 'abs_z')
                top_anomalies.append(top_year)
            
            top_anomalies_df = pd.concat(top_anomalies) if top_anomalies else pd.DataFrame()
            # Sort final result by abs_z descending to show most severe first
            top_anomalies_df = top_anomalies_df.sort_values('abs_z', ascending=False).reset_index(drop=True)
            logger.info(f"Top {request.top_n} anomalies per year: {len(top_anomalies_df)} rows total across {len(filtered_anomalies['hour_datetime'].dt.year.unique())} years")
    else:
        top_anomalies_df = pd.DataFrame()
    
    # Log top_anomalies_df datetime range and year distribution
    if len(top_anomalies_df) > 0:
        top_min_dt = top_anomalies_df['hour_datetime'].min()
        top_max_dt = top_anomalies_df['hour_datetime'].max()
        years_present = sorted(top_anomalies_df['hour_datetime'].dt.year.unique().tolist())
        logger.info(f"Top anomalies datetime range: {top_min_dt} to {top_max_dt}, years: {years_present}")
    
    # Generate insights (only if enabled)
    insights_result = None
    insights_error = None
    logger.info(f"Insight flags - enable_insights: {request.enable_insights}, enable_recurrence: {request.enable_recurrence}, enable_cost_estimates: {request.enable_cost_estimates}")
    
    if request.enable_insights and MODULES_AVAILABLE:
        try:
            # Build feature map for insights (lists of column name candidates)
            feature_map_for_insights = {
                "Temperature": ["Temperature", "temperature", "temp", "Temp"],
                "Dew Point": ["Dew Point", "DewPoint", "dew_point", "dewpoint"],
                "Clearsky GHI": ["Clearsky GHI", "ClearskyGHI", "clearsky_ghi", "ClearskyGHI"],
                "Wind Speed": ["Wind Speed", "WindSpeed", "wind_speed"],
                "Pressure": ["Pressure", "pressure", "Surface Pressure"]
            }
            
            # Validate feature_map structure and log resolved columns
            logger.info(f"Feature map for insights: {list(feature_map_for_insights.keys())}")
            if len(top_anomalies_df) > 0:
                first_anomaly_time = top_anomalies_df.iloc[0]['hour_datetime']
                # Test resolution for first anomaly
                from insights import compute_weather_z_scores
                test_z = compute_weather_z_scores(df_model, feature_map_for_insights, first_anomaly_time)
                logger.info(f"Resolved weather columns for first anomaly: {list(test_z.keys())}")
            
            # Generate explanations (actions) - use actual column from top_anomalies_df
            explanations_df = generate_anomaly_explanations(
                top_anomalies_df.head(50), df_model, feature_map_for_insights, building
            )
            actions = explanations_df.to_dict(orient="records") if isinstance(explanations_df, pd.DataFrame) and len(explanations_df) > 0 else []
            
            # Generate summary cards
            summary_cards = []
            if len(top_anomalies_df) > 0:
                # Get recurrence patterns for summary (if enabled)
                patterns_for_summary = {}
                if request.enable_recurrence:
                    patterns_for_summary = detect_recurring_patterns(filtered_anomalies)
                
                summary_cards = generate_executive_summary(
                    anomaly_df, building, request.selected_year or "All",
                    patterns_for_summary, feature_map_for_insights
                )
            
            # Recurrence patterns (only if enabled)
            recurrence = None
            if request.enable_recurrence:
                recurrence = detect_recurring_patterns(filtered_anomalies)
                logger.info(f"Recurrence analysis: {len(recurrence.get('top_hours', []))} top hours detected")
            
            insights_result = {
                "summary_cards": summary_cards or [],
                "actions": actions,
                "recurrence": recurrence if request.enable_recurrence else None,
            }
            logger.info(f"Insights generated: {len(summary_cards)} summary cards, {len(actions)} actions")
        except Exception as e:
            logger.exception(f"Insights generation error: {e}")
            insights_error = str(e)
            # Return empty insights structure instead of None to prevent frontend errors
            insights_result = {
                "summary_cards": [],
                "actions": [],
                "recurrence": None,
                "error": insights_error
            }
    
    # Occupancy insights (always generate if available)
    occupancy_result = None
    try:
        occupancy_result = generate_occupancy_insights(df_model, top_anomalies_df, building)
    except Exception as e:
        logger.warning(f"Occupancy insights error: {e}")
    
    # Cost estimate (only if enabled)
    cost_result = None
    if request.enable_cost_estimates and MODULES_AVAILABLE:
        try:
            cost_result = estimate_cost_impact(
                filtered_anomalies, building, request.electricity_rate
            )
            logger.info(f"Cost estimate: ${cost_result.get('estimated_cost', 0):.2f} (excess: {cost_result.get('excess_kwh', 0):.2f} kWh, avoided: {cost_result.get('avoided_kwh', 0):.2f} kWh)")
        except Exception as e:
            logger.exception(f"Cost estimate error: {e}")
    
    # Prepare response with all metadata
    response = {
        "anomaly_summary": {
            "total_hours": len(anomaly_df),
            "anomaly_hours": anomaly_hours,
            "anomaly_rate": anomaly_rate,
            "avg_abs_z": float(anomaly_df.loc[anomaly_df['anomaly'], 'abs_z'].mean()) if anomaly_hours > 0 else 0.0
        },
        "top_anomalies": top_anomalies_df.to_dict(orient="records"),  # Top-N per year (for table)
        "regression": regression_result,
        "insights": insights_result if insights_result is not None else {
            "summary_cards": [],
            "actions": [],
            "recurrence": None
        },
        "occupancy": occupancy_result,
        "cost": cost_result if request.enable_cost_estimates else None,
        "z_threshold_used": request.z_threshold,
        "top_n_used": request.top_n,
        "year_filter_used": request.selected_year or "All",
        "weather_source_used": weather_source_used or "CACHE",
    }
    
    # Prepare drilldown data: use ALL anomaly_df (not just filtered) for full visualization
    # Include anomaly flag for highlighting
    drilldown_data = anomaly_df.copy()
    drilldown_data['anomaly'] = drilldown_data['abs_z'] >= request.z_threshold
    
    # Apply year filter if specified
    if request.selected_year and request.selected_year != "All":
        try:
            year = int(request.selected_year)
            drilldown_data = drilldown_data[drilldown_data['hour_datetime'].dt.year == year].copy()
        except (ValueError, TypeError):
            pass  # Keep all data if year parsing fails
    
    # Downsample if too many points (preserve full range)
    if len(drilldown_data) > 5000:
        drilldown_data = drilldown_data.sort_values('hour_datetime')
        step = len(drilldown_data) // 5000
        drilldown_data = drilldown_data.iloc[::step].copy()
        logger.info(f"Downsampled drilldown data: {len(drilldown_data)} rows (from {len(anomaly_df)})")
    
    # Log drilldown datetime range
    if len(drilldown_data) > 0:
        drilldown_min_dt = drilldown_data['hour_datetime'].min()
        drilldown_max_dt = drilldown_data['hour_datetime'].max()
        logger.info(f"Drilldown data datetime range: {drilldown_min_dt} to {drilldown_max_dt} ({len(drilldown_data)} points)")
    
    # Add drilldown data to response (includes anomaly flag)
    response["drilldown_anomalies"] = drilldown_data.to_dict(orient="records")
    
    # Log response schema for debugging
    logger.info(f"Response schema: keys={list(response.keys())}, insights_keys={list(response['insights'].keys()) if response['insights'] else 'None'}")
    logger.info(f"Response prepared: {anomaly_hours} anomalies ({anomaly_rate:.2f}%), {len(top_anomalies_df)} top anomalies, {len(drilldown_data)} drilldown points, top_n={request.top_n}")
    return response

@app.get("/api/upload-requirements")
async def upload_requirements():
    """Return the data format requirements for user uploads."""
    return {
        "description": "Upload your own hourly energy consumption data for anomaly detection.",
        "file_formats": ["CSV (.csv)", "Excel (.xlsx, .xls)"],
        "required_columns": {
            "timestamp": "A datetime column with hourly timestamps (e.g. '2023-01-01 00:00:00'). Supported formats: ISO 8601, MM/DD/YYYY HH:MM, DD-MM-YYYY HH:MM, and more.",
            "energy": "A numeric column with energy consumption values (kWh or consistent units)."
        },
        "guidelines": [
            "Data should be at hourly granularity. Sub-hourly data (15-min, 30-min) will be automatically aggregated.",
            "Minimum 720 data points (roughly 1 month of hourly data) required.",
            "Provide your building location so we can fetch matching weather data.",
            "Weather data is sourced from Open-Meteo Historical API (covers 1940 to near-present).",
            "The system will merge your energy data with weather features and run anomaly detection."
        ],
        "sample_rows": [
            {"timestamp": "2023-01-01 00:00:00", "energy_kwh": 245.3},
            {"timestamp": "2023-01-01 01:00:00", "energy_kwh": 238.7},
            {"timestamp": "2023-01-01 02:00:00", "energy_kwh": 231.2},
        ]
    }


@app.post("/api/upload-analyze")
async def upload_and_analyze(
    file: UploadFile = File(...),
    location_name: str = Form(""),
    latitude: float = Form(0.0),
    longitude: float = Form(0.0),
    timestamp_column: str = Form(""),
    energy_column: str = Form(""),
    building_name: str = Form(""),
    z_threshold: float = Form(2.0),
    top_n: int = Form(50),
    feature_mode: str = Form("Auto-select (ElasticNet)"),
    top_k: int = Form(3),
    include_cloud_type: bool = Form(False),
    electricity_rate: float = Form(0.12),
    enable_insights: bool = Form(True),
    enable_recurrence: bool = Form(True),
    enable_cost_estimates: bool = Form(False),
):
    """
    Upload energy data and run anomaly detection.
    Fetches weather for the user's location, merges with energy data,
    and runs the full regression + anomaly pipeline.
    """
    import io
    import traceback

    logger.info(f"Upload request: file={file.filename}, location={location_name}, "
                f"lat={latitude}, lon={longitude}")

    # --- 1. RESOLVE COORDINATES ---
    lat, lon = latitude, longitude
    if lat == 0.0 and lon == 0.0 and location_name:
        try:
            lat, lon = resolve_city_coordinates(location_name)
            logger.info(f"Resolved '{location_name}' -> ({lat}, {lon})")
        except Exception:
            raise HTTPException(status_code=400, detail={
                "error": "geocoding_failed",
                "message": f"Could not resolve coordinates for '{location_name}'. "
                           f"Please provide latitude and longitude manually."
            })
    if lat == 0.0 and lon == 0.0:
        raise HTTPException(status_code=400, detail={
            "error": "no_location",
            "message": "Provide a city/state name or latitude and longitude."
        })

    loc_nm = (location_name or "").strip()
    fc_city = loc_nm if loc_nm else f"{lat},{lon}"

    # --- 2. PARSE UPLOADED FILE ---
    try:
        contents = await file.read()
        fname = (file.filename or "").lower()
        if fname.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(io.BytesIO(contents))
        else:
            df_raw = pd.read_csv(io.BytesIO(contents))
        logger.info(f"Parsed upload: {len(df_raw)} rows, columns={list(df_raw.columns)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "error": "file_parse_error",
            "message": f"Could not parse the uploaded file: {e}"
        })

    if len(df_raw) < 24:
        raise HTTPException(status_code=400, detail={
            "error": "insufficient_data",
            "message": f"File has only {len(df_raw)} rows. Need at least 720 hourly data points."
        })

    # --- 3. AUTO-DETECT OR USE SPECIFIED COLUMNS ---
    ts_col = timestamp_column.strip() if timestamp_column.strip() else None
    en_col = energy_column.strip() if energy_column.strip() else None

    if not ts_col:
        ts_candidates = ['timestamp', 'datetime', 'date_time', 'hour_datetime',
                         'date', 'time', 'Timestamp', 'DateTime', 'Date', 'Time']
        for c in ts_candidates:
            if c in df_raw.columns:
                ts_col = c
                break
        if not ts_col:
            for c in df_raw.columns:
                try:
                    pd.to_datetime(df_raw[c].head(20))
                    ts_col = c
                    break
                except Exception:
                    continue
    if not ts_col:
        raise HTTPException(status_code=400, detail={
            "error": "no_timestamp_column",
            "message": f"Could not detect a timestamp column. Available columns: {list(df_raw.columns)}. "
                       f"Please specify the timestamp_column parameter."
        })

    if not en_col:
        skip = {ts_col}
        for c in df_raw.columns:
            if c in skip:
                continue
            if pd.api.types.is_numeric_dtype(df_raw[c]):
                en_col = c
                break
    if not en_col:
        raise HTTPException(status_code=400, detail={
            "error": "no_energy_column",
            "message": f"Could not detect a numeric energy column. Available columns: {list(df_raw.columns)}. "
                       f"Please specify the energy_column parameter."
        })

    logger.info(f"Using columns: timestamp='{ts_col}', energy='{en_col}'")

    # --- 4. BUILD CLEAN DATAFRAME ---
    try:
        df_raw['hour_datetime'] = pd.to_datetime(df_raw[ts_col])
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "error": "datetime_parse_error",
            "message": f"Could not parse column '{ts_col}' as datetime: {e}"
        })

    df_raw[en_col] = pd.to_numeric(df_raw[en_col], errors='coerce')
    df_clean = df_raw[['hour_datetime', en_col]].dropna().copy()
    df_clean = df_clean.sort_values('hour_datetime').reset_index(drop=True)

    if len(df_clean) < 720:
        raise HTTPException(status_code=400, detail={
            "error": "insufficient_valid_data",
            "message": f"Only {len(df_clean)} valid rows after cleaning. Need at least 720."
        })

    # Detect frequency and aggregate to hourly if needed
    diffs = df_clean['hour_datetime'].diff().dropna()
    median_freq_minutes = diffs.dt.total_seconds().median() / 60
    logger.info(f"Detected median frequency: {median_freq_minutes:.1f} minutes")

    if median_freq_minutes < 50:
        logger.info(f"Sub-hourly data detected ({median_freq_minutes:.0f} min), aggregating to hourly")
        df_clean['hour_floor'] = df_clean['hour_datetime'].dt.floor('h')
        df_clean = df_clean.groupby('hour_floor').agg({en_col: 'mean'}).reset_index()
        df_clean = df_clean.rename(columns={'hour_floor': 'hour_datetime'})
        logger.info(f"After hourly aggregation: {len(df_clean)} rows")

    if len(df_clean) < 720:
        raise HTTPException(status_code=400, detail={
            "error": "insufficient_hourly_data",
            "message": f"Only {len(df_clean)} hourly data points after aggregation. Need at least 720."
        })

    # --- 5. FETCH WEATHER DATA ---
    start_date = df_clean['hour_datetime'].min().strftime('%Y-%m-%d')
    end_date = df_clean['hour_datetime'].max().strftime('%Y-%m-%d')
    logger.info(f"Fetching weather: ({lat}, {lon}), {start_date} to {end_date}")

    weather_df = download_weather_openmeteo(lat, lon, start_date, end_date)
    if weather_df is None or len(weather_df) == 0:
        raise HTTPException(status_code=502, detail={
            "error": "weather_fetch_failed",
            "message": "Could not fetch weather data from Open-Meteo for your location and date range. "
                       "Ensure dates are between 1940 and a few days ago."
        })
    logger.info(f"Weather data: {len(weather_df)} rows, {start_date} to {end_date}")

    # --- 6. MERGE ENERGY + WEATHER ---
    df_clean['hour_datetime'] = df_clean['hour_datetime'].dt.tz_localize(None)
    weather_df['hour_datetime'] = weather_df['hour_datetime'].dt.tz_localize(None)

    df = pd.merge(df_clean, weather_df, on='hour_datetime', how='inner')
    df = df.sort_values('hour_datetime').reset_index(drop=True)
    logger.info(f"Merged data: {len(df)} rows (energy={len(df_clean)}, weather={len(weather_df)})")

    if len(df) < 720:
        raise HTTPException(status_code=400, detail={
            "error": "insufficient_merged_data",
            "message": f"Only {len(df)} rows after merging energy with weather (timestamps may not align). "
                       f"Need at least 720."
        })

    building = en_col
    fc_building = building_name.strip() if building_name.strip() else building
    weather_source_used = "OPEN_METEO"
    rows_before_filter = len(df)

    # --- 7. RUN ANALYSIS PIPELINE (same as /api/run) ---
    building_cols = [c for c in df.columns if c not in [
        'hour_datetime', 'Temperature', 'Dew Point', 'Clearsky GHI',
        'Cloud_Type', 'Cloud_Type_Label', 'Wind Speed', 'Pressure',
        'year', 'month', 'day', 'hour'
    ]]

    is_fixed = (feature_mode == "Fixed 3-feature")
    if is_fixed:
        feature_map = {
            "Temperature": ["Temperature"], "Dew Point": ["Dew Point"],
            "Clearsky GHI": ["Clearsky GHI"],
        }
        feature_cols = []
        for canonical, variants in feature_map.items():
            for v in variants:
                if v in df.columns:
                    feature_cols.append(v)
                    break
        if len(feature_cols) < 3:
            raise HTTPException(status_code=400, detail="Required weather features not available after merge")
        selected_features = feature_cols[:3]
        method_used = "Fixed 3-feature"
    else:
        candidate_info = get_candidate_weather_features(
            df, building, exclude_cols=[], building_cols=building_cols
        )
        selection_method = "elasticnet" if feature_mode == "Auto-select (ElasticNet)" else "correlation"
        selection_result = select_weather_features(
            df, building,
            feature_map=candidate_info.get("feature_map", {}),
            method=selection_method, top_k=top_k,
            include_cloud_type=include_cloud_type,
            building_cols=building_cols
        )
        selected_features = selection_result.get("selected_features", [])
        method_used = selection_result.get("method_used", selection_method)

    if not selected_features:
        raise HTTPException(status_code=400, detail="No weather features could be selected for regression")

    fit_result = fit_regression(df, building, selected_features)
    if fit_result.get("error"):
        raise HTTPException(status_code=400, detail={
            "error": "regression_failed", "message": fit_result["error"]
        })

    metrics = fit_result.get("metrics", {})
    r2 = metrics.get("r2")

    if fit_result.get("_model") and fit_result.get("_scaler"):
        upload_cache_key = f"{fc_city}|{fc_building}"
        cache["model_cache"][upload_cache_key] = {
            "model": fit_result["_model"],
            "scaler": fit_result["_scaler"],
            "features": selected_features,
            "residual_std": fit_result.get("_residual_std", 0),
            "r2": r2,
            "city": fc_city,
            "building": fc_building,
            "lat": lat,
            "lon": lon,
        }
        logger.info(f"Cached upload model for forecast: {upload_cache_key}")
        persist_model_for_forecast(fc_city, fc_building, cache["model_cache"][upload_cache_key])

    y_std = df[building].std()
    y_mean = df[building].mean()

    regression_warning = None
    if r2 is not None and (pd.isna(r2) or not np.isfinite(r2)):
        regression_warning = "R² is NaN or infinite"
        metrics = {"r2": None, "rmse": None, "mae": None}
    elif r2 is None:
        regression_warning = "R² unavailable"
    elif y_std < 1e-6:
        regression_warning = f"Near-zero variance (std={y_std:.6f})"

    regression_result = {
        "selected_features": selected_features,
        "method_used": method_used,
        "metrics": metrics,
        "coef_table": fit_result.get("coef_table", pd.DataFrame()).to_dict(orient="records")
            if isinstance(fit_result.get("coef_table"), pd.DataFrame) else [],
        "confidence": fit_result.get("confidence", get_regression_confidence(r2 if r2 is not None else 0)),
        "regression_warning": regression_warning,
        "diagnostics": {
            "rows_before_filter": rows_before_filter,
            "rows_after_year_filter": len(df),
            "y_mean": float(y_mean), "y_std": float(y_std),
            "y_min": float(df[building].min()), "y_max": float(df[building].max()),
            "train_size": fit_result.get("train_size", 0),
            "test_size": fit_result.get("test_size", 0),
            "model_type": fit_result.get("model_type", "unknown"),
        }
    }

    # Anomaly detection
    y_pred_full = fit_result['y_pred']
    y_actual = pd.to_numeric(df[building], errors='coerce').values
    valid_mask = ~np.isnan(y_pred_full) & ~np.isnan(y_actual)
    n_valid = int(valid_mask.sum())
    if n_valid < 200:
        raise HTTPException(status_code=400, detail={
            "error": "insufficient_valid_predictions",
            "message": f"Only {n_valid} valid predictions (need 200+)."
        })

    y = y_actual[valid_mask]
    y_pred = y_pred_full[valid_mask]
    df_model = df[valid_mask].copy()

    residuals = y - y_pred
    res_std = residuals.std()
    z_scores = np.zeros_like(residuals) if res_std < 1e-10 else (residuals - residuals.mean()) / res_std

    anomaly_df = pd.DataFrame({
        'hour_datetime': df_model['hour_datetime'].values,
        'actual': y, 'predicted': y_pred, 'residual': residuals,
        'z_score': z_scores, 'abs_z': np.abs(z_scores),
        'abs_residual': np.abs(residuals),
        'anomaly': np.abs(z_scores) > z_threshold
    })

    if 'Cloud_Type' in df_model.columns:
        anomaly_df['Cloud_Type'] = df_model['Cloud_Type'].values

    anomaly_df['anomaly'] = anomaly_df['abs_z'] >= z_threshold
    anomaly_rate = float(anomaly_df['anomaly'].mean() * 100)
    anomaly_hours = int(anomaly_df['anomaly'].sum())

    filtered_anomalies = anomaly_df[anomaly_df['abs_z'] >= z_threshold].copy()

    # Top-N anomalies per year
    if len(filtered_anomalies) > 0:
        top_anomalies = []
        for year in sorted(filtered_anomalies['hour_datetime'].dt.year.unique()):
            year_data = filtered_anomalies[filtered_anomalies['hour_datetime'].dt.year == year]
            top_anomalies.append(year_data.nlargest(top_n, 'abs_z'))
        top_anomalies_df = pd.concat(top_anomalies).sort_values('abs_z', ascending=False).reset_index(drop=True)
    else:
        top_anomalies_df = pd.DataFrame()

    # Insights
    insights_result = None
    if enable_insights and MODULES_AVAILABLE:
        try:
            feature_map_for_insights = {
                "Temperature": ["Temperature"], "Dew Point": ["Dew Point"],
                "Clearsky GHI": ["Clearsky GHI"],
                "Wind Speed": ["Wind Speed"], "Pressure": ["Pressure"]
            }
            explanations_df = generate_anomaly_explanations(
                top_anomalies_df.head(50), df_model, feature_map_for_insights, building
            )
            actions = explanations_df.to_dict(orient="records") if isinstance(explanations_df, pd.DataFrame) and len(explanations_df) > 0 else []

            summary_cards = []
            if len(top_anomalies_df) > 0:
                patterns = detect_recurring_patterns(filtered_anomalies) if enable_recurrence else {}
                summary_cards = generate_executive_summary(
                    anomaly_df, building, "All", patterns, feature_map_for_insights
                )

            recurrence = detect_recurring_patterns(filtered_anomalies) if enable_recurrence else None
            insights_result = {
                "summary_cards": summary_cards or [],
                "actions": actions,
                "recurrence": recurrence,
            }
        except Exception as e:
            logger.exception(f"Upload insights error: {e}")
            insights_result = {"summary_cards": [], "actions": [], "recurrence": None, "error": str(e)}

    occupancy_result = None
    try:
        occupancy_result = generate_occupancy_insights(df_model, top_anomalies_df, building)
    except Exception as e:
        logger.warning(f"Upload occupancy insights error: {e}")

    cost_result = None
    if enable_cost_estimates and MODULES_AVAILABLE:
        try:
            cost_result = estimate_cost_impact(filtered_anomalies, building, electricity_rate)
        except Exception:
            pass

    response = {
        "anomaly_summary": {
            "total_hours": len(anomaly_df),
            "anomaly_hours": anomaly_hours,
            "anomaly_rate": anomaly_rate,
            "avg_abs_z": float(anomaly_df.loc[anomaly_df['anomaly'], 'abs_z'].mean()) if anomaly_hours > 0 else 0.0
        },
        "top_anomalies": top_anomalies_df.to_dict(orient="records"),
        "regression": regression_result,
        "insights": insights_result or {"summary_cards": [], "actions": [], "recurrence": None},
        "occupancy": occupancy_result,
        "cost": cost_result if enable_cost_estimates else None,
        "z_threshold_used": z_threshold,
        "top_n_used": top_n,
        "year_filter_used": "All",
        "weather_source_used": weather_source_used,
        "upload_info": {
            "filename": file.filename,
            "original_rows": len(df_raw),
            "valid_rows": len(df_clean),
            "merged_rows": len(df),
            "timestamp_column": ts_col,
            "energy_column": en_col,
            "building_name": building_name.strip() if building_name.strip() else en_col,
            "location": location_name or f"({lat}, {lon})",
            "date_range": f"{start_date} to {end_date}",
        }
    }

    # Drilldown data
    drilldown_data = anomaly_df.copy()
    if len(drilldown_data) > 5000:
        drilldown_data = drilldown_data.sort_values('hour_datetime')
        step = len(drilldown_data) // 5000
        drilldown_data = drilldown_data.iloc[::step].copy()
    response["drilldown_anomalies"] = drilldown_data.to_dict(orient="records")
    response["city"] = fc_city
    response["building"] = fc_building

    logger.info(f"Upload analysis complete: {anomaly_hours} anomalies ({anomaly_rate:.2f}%), "
                f"R²={r2}, {len(top_anomalies_df)} top anomalies")
    return response


class ForecastRequest(BaseModel):
    city: str
    building: str
    forecast_days: int = 7


@app.post("/api/forecast")
async def get_forecast(request: ForecastRequest):
    """
    Generate energy consumption forecast using the cached regression model
    and Open-Meteo 7-day weather forecast.
    """
    cache_key = f"{request.city}|{request.building}"
    model_data = cache.get("model_cache", {}).get(cache_key)
    if not model_data:
        model_data = load_model_for_forecast_from_disk(request.city, request.building)
        if model_data:
            cache["model_cache"][cache_key] = model_data
            logger.info(f"Loaded forecast model from disk: {cache_key}")

    if not model_data:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_model",
                "message": "Run analysis first to train the model before forecasting."
            }
        )

    model = model_data["model"]
    scaler = model_data["scaler"]
    features = model_data["features"]
    residual_std = model_data.get("residual_std", 0)
    r2 = model_data.get("r2", 0)

    if "lat" in model_data and "lon" in model_data:
        lat, lon = model_data["lat"], model_data["lon"]
    else:
        try:
            lat, lon = resolve_city_coordinates(request.city)
        except Exception as e:
            raise HTTPException(status_code=400, detail={"error": "geocoding_failed", "message": str(e)})

    forecast_days = min(request.forecast_days, 16)
    weather_df = download_weather_forecast_openmeteo(lat, lon, days=forecast_days)
    if weather_df is None or weather_df.empty:
        raise HTTPException(
            status_code=500,
            detail={"error": "weather_fetch_failed", "message": "Could not fetch forecast weather data."}
        )

    missing_features = [f for f in features if f not in weather_df.columns]
    if missing_features:
        raise HTTPException(
            status_code=500,
            detail={"error": "feature_mismatch", "message": f"Forecast weather missing features: {missing_features}"}
        )

    X_forecast = weather_df[features].copy()
    X_forecast = X_forecast.ffill().bfill().fillna(0)
    X_scaled = scaler.transform(X_forecast.values)
    predictions = model.predict(X_scaled)
    predictions = np.maximum(predictions, 0)

    hourly_data = []
    for i, row in weather_df.iterrows():
        dt = row["hour_datetime"]
        pred = float(predictions[i])
        hourly_data.append({
            "datetime": dt.isoformat(),
            "hour": dt.hour,
            "day_of_week": dt.strftime("%A"),
            "date": dt.strftime("%Y-%m-%d"),
            "predicted_kwh": round(pred, 2),
            "lower_bound": round(max(0, pred - 1.96 * residual_std), 2),
            "upper_bound": round(pred + 1.96 * residual_std, 2),
            "temperature": float(row.get("Temperature", 0)),
            "dew_point": float(row.get("Dew Point", 0)),
            "ghi": float(row.get("Clearsky GHI", 0)),
        })

    daily_summary = []
    weather_df["predicted"] = predictions
    weather_df["date_str"] = weather_df["hour_datetime"].dt.strftime("%Y-%m-%d")
    for date_str, group in weather_df.groupby("date_str"):
        preds = group["predicted"].values
        temps = group["Temperature"].values
        peak_idx = int(np.argmax(preds))
        peak_hour = group.iloc[peak_idx]["hour_datetime"]
        daily_summary.append({
            "date": date_str,
            "day_of_week": pd.to_datetime(date_str).strftime("%A"),
            "total_kwh": round(float(np.sum(preds)), 1),
            "avg_kwh": round(float(np.mean(preds)), 2),
            "peak_kwh": round(float(np.max(preds)), 2),
            "peak_hour": peak_hour.strftime("%I:%M %p"),
            "avg_temp": round(float(np.mean(temps)), 1),
            "max_temp": round(float(np.max(temps)), 1),
            "min_temp": round(float(np.min(temps)), 1),
        })

    return {
        "city": request.city,
        "building": request.building,
        "forecast_days": forecast_days,
        "r2": r2,
        "residual_std": round(residual_std, 4),
        "hourly_forecast": hourly_data,
        "daily_summary": daily_summary,
        "model_features": features,
    }


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "modules_available": MODULES_AVAILABLE}


# --- Production: serve React build if frontend/dist exists ---
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA — any non-API route gets index.html."""
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
