"""
NSRDB Weather Data Downloader Module

Automatically downloads weather data from NREL NSRDB API using the GOES Aggregated v4 endpoint
and processes it to match Chicago weather format with standardized column names.
"""

import requests
import pandas as pd
import numpy as np
from pathlib import Path
import time
from typing import Optional, Tuple, Dict, List
import os
import json

# City coordinates (lat, lon)
# Must align with VALID_CITIES in app.py
# Cities without coordinates will have weather download disabled but can still load if merged file exists
CITY_COORDS = {
    'albuquerque': (35.0844, -106.6504),
    'atlanta': (33.7490, -84.3880),
    'baltimore': (39.2904, -76.6122),
    'boston': (42.3601, -71.0589),
    'boulder': (40.0150, -105.2705),
    'chicago': (41.8781, -87.6298),
    'dallas': (32.7767, -96.7970),
    'denver': (39.7392, -104.9903),
    'duluth': (46.7867, -92.1005),
    'helena': (46.5887, -112.0245),
    'houston': (29.7604, -95.3698),
    'las vegas': (36.1699, -115.1398),
    'los angeles': (34.0522, -118.2437),
    'miami': (25.7617, -80.1918),
    'minneapolis': (44.9778, -93.2650),
    'new york': (40.7128, -74.0060),
    'phoenix': (33.4484, -112.0740),
    'san francisco': (37.7749, -122.4194),
    'seattle': (47.6062, -122.3321),
}

# NSRDB GOES Aggregated v4 API endpoint (for 1998+ data)
NSRDB_API_BASE = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"

# NSRDB attribute codes (API parameter names)
# Using surface_pressure instead of pressure for GOES aggregated endpoint
NSRDB_ATTRIBUTES = "air_temperature,dew_point,clearsky_ghi,cloud_type,wind_speed,surface_pressure"

# API key: read from environment variable, or use hardcoded fallback
NSRDB_API_KEY_FALLBACK = "LfZhpSpp5GSAPgVvNpl84ju37ocT3uWR1yqSFOUe"  # Fallback if env var not set
NSRDB_EMAIL = "atulumar.kar@tamu.edu"

# Years to download
DEFAULT_YEARS = list(range(1998, 2015))  # 1998-2014


def load_cloud_type_mapping(metadata_file: Path) -> Optional[Dict[int, str]]:
    """
    Load cloud type mapping from Metadata_legend.xlsx
    
    Returns dict mapping numeric codes to labels, or None if file not found
    """
    if not metadata_file.exists():
        return None
    
    try:
        df = pd.read_excel(metadata_file, sheet_name=0)
        
        # Look for cloud type columns (case-insensitive)
        cloud_cols = [c for c in df.columns if 'cloud' in c.lower() and 'type' in c.lower()]
        code_cols = [c for c in df.columns if any(x in c.lower() for x in ['code', 'value', 'id', 'number'])]
        label_cols = [c for c in df.columns if any(x in c.lower() for x in ['label', 'name', 'description', 'meaning'])]
        
        if cloud_cols and (code_cols or label_cols):
            code_col = code_cols[0] if code_cols else df.columns[0]
            label_col = label_cols[0] if label_cols else df.columns[1] if len(df.columns) > 1 else code_col
            
            mapping = {}
            for _, row in df.iterrows():
                try:
                    code = int(row[code_col])
                    label = str(row[label_col])
                    mapping[code] = label
                except (ValueError, KeyError):
                    continue
            
            return mapping if mapping else None
        
        return get_default_cloud_mapping()
        
    except Exception as e:
        print(f"Warning: Could not load cloud type mapping: {e}")
        return get_default_cloud_mapping()


def get_default_cloud_mapping() -> Dict[int, str]:
    """Default cloud type mapping (NSRDB standard)"""
    return {
        0: 'Clear',
        1: 'Probably Clear',
        2: 'Fog',
        3: 'Water',
        4: 'Super-Cooled Water',
        5: 'Mixed',
        6: 'Opaque Ice',
        7: 'Cirrus',
        8: 'Overlapping',
        9: 'Overshooting',
        10: 'Unknown',
        11: 'Dust',
        12: 'Smoke',
    }


def download_nsrdb_year(
    lat: float,
    lon: float,
    year: int,
    api_key: str,
    email: str,
    output_dir: Path,
    progress_callback=None
) -> Optional[Path]:
    """
    Download NSRDB GOES Aggregated v4 data for a single year
    
    Args:
        lat: Latitude
        lon: Longitude
        year: Year to download
        api_key: NSRDB API key
        email: Email for API
        output_dir: Directory to save the file
        progress_callback: Optional function(year, message) for progress updates
    
    Returns:
        Path to downloaded file, or None if failed
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"W{year}.csv"
    
    # Check if file already exists (caching)
    if output_file.exists():
        if progress_callback:
            progress_callback(year, f"Using cached file for {year}")
        return output_file
    
    # Prepare API request parameters
    # Note: NSRDB uses WKT format: POINT(lon lat) - longitude first!
    wkt = f"POINT({lon} {lat})"
    
    params = {
        'wkt': wkt,
        'names': str(year),  # Single year as string
        'interval': 60,  # 60 minutes (hourly)
        'utc': 'false',
        'leap_day': 'false',
        'attributes': NSRDB_ATTRIBUTES,
        'full_name': 'Energy Anomaly Explorer',
        'email': email,
        'affiliation': 'Texas A&M University',
        'reason': 'Research',
        'mailing_list': 'false',
        'api_key': api_key,
    }
    
    try:
        if progress_callback:
            progress_callback(year, f"Downloading {year}...")
        
        # Make request
        response = requests.get(NSRDB_API_BASE, params=params, timeout=300)
        
        # Debug logging
        request_url = f"{NSRDB_API_BASE}?wkt={wkt}&names={year}&interval=60&utc=false&leap_day=false&attributes={NSRDB_ATTRIBUTES}&full_name=Energy+Anomaly+Explorer&email={email}&affiliation=Texas+A%26M+University&reason=Research&mailing_list=false&api_key=***"
        
        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text[:500]}"
            if progress_callback:
                progress_callback(year, f"Error: {error_msg}")
            print(f"NSRDB API Error for {year}:")
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.text[:500]}")
            print(f"  URL: {request_url}")
            return None
        
        # Check if response is CSV or JSON
        content_type = response.headers.get('Content-Type', '')
        
        # GOES aggregated endpoint typically returns CSV directly
        # Check if it's CSV first
        if 'csv' in content_type.lower() or 'text' in content_type.lower() or response.text.strip().startswith('Year') or response.text.strip().startswith('year'):
            # Direct CSV response - save it
            with open(output_file, 'wb') as f:
                f.write(response.content)
        else:
            # Try to parse as JSON (may return JSON with download URL or error)
            try:
                json_data = response.json()
                
                # Check for errors
                if 'errors' in json_data:
                    error_msg = str(json_data.get('errors', json_data))
                    if progress_callback:
                        progress_callback(year, f"API Error: {error_msg}")
                    print(f"NSRDB API Error for {year}: {error_msg}")
                    print(f"  URL: {request_url}")
                    return None
                
                # Check for download URL or CSV data in outputs
                if 'outputs' in json_data:
                    outputs = json_data['outputs']
                    
                    # Try downloadUrl
                    if 'downloadUrl' in outputs:
                        download_url = outputs['downloadUrl']
                        if progress_callback:
                            progress_callback(year, f"Fetching {year} from download URL...")
                        file_response = requests.get(download_url, timeout=600)
                        file_response.raise_for_status()
                        with open(output_file, 'wb') as f:
                            f.write(file_response.content)
                    # Try direct CSV in outputs
                    elif 'csv' in outputs:
                        csv_data = outputs['csv']
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(csv_data)
                    else:
                        raise Exception("No download URL or CSV data in JSON response")
                else:
                    raise Exception("No 'outputs' key in JSON response")
                    
            except (ValueError, KeyError, AttributeError):
                # Not JSON and not CSV - might be an error
                error_msg = f"Unexpected content type: {content_type}"
                if progress_callback:
                    progress_callback(year, f"Error: {error_msg}")
                print(f"NSRDB API Error for {year}: {error_msg}")
                print(f"  Response: {response.text[:500]}")
                print(f"  URL: {request_url}")
                return None
        
        if progress_callback:
            progress_callback(year, f"Saved {year}")
        
        return output_file
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error: {str(e)}"
        if progress_callback:
            progress_callback(year, f"Error: {error_msg}")
        print(f"NSRDB Download Error for {year}: {error_msg}")
        if output_file.exists():
            output_file.unlink()  # Remove partial file
        return None
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        if progress_callback:
            progress_callback(year, f"Error: {error_msg}")
        print(f"NSRDB Processing Error for {year}: {error_msg}")
        if output_file.exists():
            output_file.unlink()  # Remove partial file
        return None


def standardize_weather_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize NSRDB weather columns to match Chicago format
    
    Maps NSRDB output columns to:
    - Temperature
    - Dew Point
    - Clearsky GHI
    - Cloud_Type (or Cloud Type)
    
    Returns DataFrame with standardized column names
    """
    # Create a copy to avoid modifying original
    df = df.copy()
    
    # Standardize column names (case-insensitive, handle spaces/underscores)
    original_cols = df.columns.tolist()
    df.columns = df.columns.str.strip()
    
    # Map NSRDB output columns to our standard names
    column_mapping = {}
    
    # Temperature - try various names
    temp_names = ['Temperature', 'Air Temperature', 'air_temperature', 'T2M', 'Temperature (C)']
    for col in df.columns:
        col_lower = col.lower()
        if any(name.lower() in col_lower for name in temp_names) or 'temp' in col_lower:
            if 'dew' not in col_lower and 'point' not in col_lower:
                column_mapping[col] = 'Temperature'
                break
    
    # Dew Point
    dew_names = ['Dew Point', 'dew_point', 'Dewpoint', 'Dew Point (C)']
    for col in df.columns:
        col_lower = col.lower()
        if any(name.lower() in col_lower for name in dew_names) or ('dew' in col_lower and 'point' in col_lower):
            column_mapping[col] = 'Dew Point'
            break
    
    # Clearsky GHI
    ghi_names = ['Clearsky GHI', 'clearsky_ghi', 'Clearsky DNI', 'GHI', 'Clearsky GHI (W/m^2)']
    for col in df.columns:
        col_lower = col.lower()
        if any(name.lower() in col_lower for name in ghi_names) or ('clearsky' in col_lower and 'ghi' in col_lower):
            column_mapping[col] = 'Clearsky GHI'
            break
    
    # Cloud Type
    cloud_names = ['Cloud Type', 'cloud_type', 'CloudType', 'Cloud Type Code']
    for col in df.columns:
        col_lower = col.lower()
        if any(name.lower() in col_lower for name in cloud_names) or ('cloud' in col_lower and 'type' in col_lower):
            column_mapping[col] = 'Cloud_Type_Raw'
            break
    
    # Apply mapping
    if column_mapping:
        df = df.rename(columns=column_mapping)
    
    # Ensure standard names exist (handle case variations)
    col_lower_map = {c.lower().replace(' ', '_'): c for c in df.columns}
    
    # Temperature
    if 'Temperature' not in df.columns:
        for key in ['temperature', 'air_temperature', 't2m']:
            if key in col_lower_map:
                df['Temperature'] = df[col_lower_map[key]]
                break
    
    # Dew Point
    if 'Dew Point' not in df.columns:
        for key in ['dew_point', 'dewpoint']:
            if key in col_lower_map:
                df['Dew Point'] = df[col_lower_map[key]]
                break
    
    # Clearsky GHI
    if 'Clearsky GHI' not in df.columns:
        for key in ['clearsky_ghi', 'ghi', 'clearsky']:
            if key in col_lower_map:
                df['Clearsky GHI'] = df[col_lower_map[key]]
                break
    
    # Cloud Type (raw)
    if 'Cloud_Type_Raw' not in df.columns:
        for key in ['cloud_type', 'cloudtype']:
            if key in col_lower_map:
                df['Cloud_Type_Raw'] = df[col_lower_map[key]]
                break
    
    return df


def apply_cloud_type_mapping(df: pd.DataFrame, metadata_legend_path: Path) -> pd.DataFrame:
    """
    Apply cloud type mapping from metadata legend
    
    Converts Cloud_Type_Raw to Cloud_Type using the mapping from Metadata_legend.xlsx
    """
    if 'Cloud_Type_Raw' not in df.columns:
        # Default to clear sky
        df['Cloud_Type'] = 0
        return df
    
    cloud_raw = df['Cloud_Type_Raw']
    
    # Check if it's already discrete (integers 0-12)
    if cloud_raw.dtype in [np.int64, np.int32, np.int16, np.int8]:
        df['Cloud_Type'] = cloud_raw.astype(int)
    else:
        # Convert percentage to discrete categories (if needed)
        # This matches SAS logic: 0-10% = 0, 10-25% = 1, etc.
        df['Cloud_Type'] = pd.cut(
            cloud_raw,
            bins=[-1, 10, 25, 50, 75, 90, 100],
            labels=[0, 1, 2, 3, 4, 5]
        ).astype(int)
    
    # Remove raw column
    if 'Cloud_Type_Raw' in df.columns:
        df = df.drop(columns=['Cloud_Type_Raw'])
    
    return df


def detect_header_row(file_path: Path, max_lines: int = 40) -> int:
    """
    Dynamically detect the header row in NSRDB CSV file.
    
    Looks for the first line that contains all required columns:
    Year, Month, Day, Hour, and preferably Temperature.
    
    Returns:
        Row index (0-based) of the header row, or 0 if not found
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [f.readline() for _ in range(max_lines)]
        
        required_keywords = ['year', 'month', 'day', 'hour']
        preferred_keywords = ['temperature', 'temp']
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            # Check if line contains all required keywords
            if all(keyword in line_lower for keyword in required_keywords):
                # Prefer lines that also have temperature
                if any(keyword in line_lower for keyword in preferred_keywords):
                    return i
                # But accept if it has all required
                return i
        
        # Fallback: return 0 if no header found
        return 0
    except Exception as e:
        print(f"Warning: Could not detect header row in {file_path}: {e}")
        return 0


def process_nsrdb_file(file_path: Path, metadata_legend_path: Path) -> Optional[pd.DataFrame]:
    """
    Process a downloaded NSRDB CSV file to match Chicago format
    
    Returns DataFrame with columns: Year, Month, Day, Hour, Temperature, Dew Point, Clearsky GHI, Cloud_Type
    """
    try:
        # Detect header row dynamically
        header_row = detect_header_row(file_path)
        
        # Read CSV starting from detected header row
        df = pd.read_csv(
            file_path,
            skiprows=header_row,
            low_memory=False,
            encoding='utf-8',
            on_bad_lines='skip'
        )
        
        if df is None or len(df) == 0:
            raise ValueError("Could not read NSRDB file or file is empty after parsing")
        
        # Clean column names (strip whitespace, handle quotes)
        df.columns = df.columns.str.strip().str.replace('"', '').str.replace("'", '')
        
        # Standardize columns to match Chicago format
        df = standardize_weather_columns(df)
        
        # Apply cloud type mapping (keeps numeric codes 0-12)
        df = apply_cloud_type_mapping(df, metadata_legend_path)
        
        # Extract datetime components - must have Year, Month, Day, Hour
        col_lower = {c.lower().replace(' ', '_').replace('-', '_'): c for c in df.columns}
        
        required_cols_lower = ['year', 'month', 'day', 'hour']
        if not all(c in col_lower for c in required_cols_lower):
            # Print first few lines for debugging
            print(f"Error in {file_path}: Missing required datetime columns")
            print(f"  Available columns: {list(df.columns)}")
            print(f"  First 5 rows:\n{df.head()}")
            raise ValueError(f"Missing required datetime columns. Available: {list(df.columns)}")
        
        # Extract Year, Month, Day, Hour as integers
        df['Year'] = pd.to_numeric(df[col_lower['year']], errors='coerce').astype('Int64')
        df['Month'] = pd.to_numeric(df[col_lower['month']], errors='coerce').astype('Int64')
        df['Day'] = pd.to_numeric(df[col_lower['day']], errors='coerce').astype('Int64')
        df['Hour'] = pd.to_numeric(df[col_lower['hour']], errors='coerce').astype('Int64')
        
        # Ensure Temperature, Dew Point, Clearsky GHI are numeric floats
        if 'Temperature' in df.columns:
            df['Temperature'] = pd.to_numeric(df['Temperature'], errors='coerce')
        if 'Dew Point' in df.columns:
            df['Dew Point'] = pd.to_numeric(df['Dew Point'], errors='coerce')
        if 'Clearsky GHI' in df.columns:
            df['Clearsky GHI'] = pd.to_numeric(df['Clearsky GHI'], errors='coerce')
        
        # Ensure Cloud_Type is integer (0-12)
        if 'Cloud_Type' in df.columns:
            df['Cloud_Type'] = pd.to_numeric(df['Cloud_Type'], errors='coerce').fillna(0).astype('Int64')
        
        # Remove rows with missing critical data
        df = df.dropna(subset=['Year', 'Month', 'Day', 'Hour', 'Temperature', 'Dew Point', 'Clearsky GHI'])
        
        # Select and reorder columns to match Chicago format exactly
        output_cols = ['Year', 'Month', 'Day', 'Hour', 'Temperature', 'Dew Point', 'Clearsky GHI', 'Cloud_Type']
        missing_output = [c for c in output_cols if c not in df.columns]
        if missing_output:
            raise ValueError(f"Missing required output columns: {missing_output}. Available: {list(df.columns)}")
        
        df = df[output_cols].copy()
        
        # Convert to proper types
        df['Year'] = df['Year'].astype(int)
        df['Month'] = df['Month'].astype(int)
        df['Day'] = df['Day'].astype(int)
        df['Hour'] = df['Hour'].astype(int)
        df['Temperature'] = df['Temperature'].astype(float)
        df['Dew Point'] = df['Dew Point'].astype(float)
        df['Clearsky GHI'] = df['Clearsky GHI'].astype(float)
        df['Cloud_Type'] = df['Cloud_Type'].astype(int)
        
        return df
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        # Print first few lines for debugging
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_lines = [f.readline() for _ in range(10)]
            print(f"First 10 lines of {file_path}:")
            for i, line in enumerate(first_lines):
                print(f"  Line {i}: {line[:100]}")
        except:
            pass
        import traceback
        traceback.print_exc()
        return None


def get_nsrdb_api_key() -> str:
    """Get NSRDB API key from environment variable or fallback constant"""
    return os.getenv("NSRDB_API_KEY", NSRDB_API_KEY_FALLBACK)


def fetch_nsrdb_weather(
    city: str,
    api_key: str = None,
    email: str = None,
    years: List[int] = None,
    project_root: Path = None,
    progress_callback=None
) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    Fetch NSRDB weather data for a city
    
    Args:
        city: City name (will be lowercased)
        api_key: NSRDB API key
        email: Email for API
        years: List of years to download (default: 1998-2014)
        project_root: Project root directory
        progress_callback: Optional function(year, message) for progress updates
    
    Returns:
        (success: bool, message: str, combined_df: Optional[DataFrame])
    """
    if project_root is None:
        project_root = Path.cwd()
    
    # Get API key if not provided
    if api_key is None:
        api_key = get_nsrdb_api_key()
    
    if email is None:
        email = NSRDB_EMAIL
    
    city_lower = city.lower()
    
    # Try CITY_COORDS first (existing behavior)
    if city_lower in CITY_COORDS:
        lat, lon = CITY_COORDS[city_lower]
    else:
        # Fallback to geocoding API if not in CITY_COORDS
        coords = resolve_city_coords_fallback(city)
        if coords is None:
            return False, f"City '{city}' not in configured coordinates and could not be auto-resolved. Available: {list(CITY_COORDS.keys())}", None
        lat, lon = coords
        # Note: We don't write back to CITY_COORDS, only cache to JSON
    
    if years is None:
        years = DEFAULT_YEARS
    
    # Create output directory: Weather_<city> (e.g., Weather_Houston)
    save_dir = project_root / f"Weather_{city}"
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Download each year
    downloaded_files = []
    for i, year in enumerate(years):
        if progress_callback:
            progress_callback(year, f"Downloading {year} ({i+1}/{len(years)})...")
        
        file_path = download_nsrdb_year(lat, lon, year, api_key, email, save_dir, progress_callback)
        if file_path:
            downloaded_files.append(file_path)
        else:
            return False, f"Failed to download weather data for {year}. Check console for details.", None
        
        # Rate limiting
        if i < len(years) - 1:
            time.sleep(1)
    
    if not downloaded_files:
        return False, "No files were downloaded", None
    
    # Process and combine files
    if progress_callback:
        progress_callback(None, "Processing weather files...")
    
    metadata_legend_path = project_root / "Weather data" / "Metadata_legend.xlsx"
    dfs = []
    
    for file_path in downloaded_files:
        df = process_nsrdb_file(file_path, metadata_legend_path)
        if df is not None:
            dfs.append(df)
        else:
            print(f"Warning: Failed to process {file_path}")
    
    if not dfs:
        return False, "Failed to process weather files", None
    
    # Combine
    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df = combined_df.sort_values(['Year', 'Month', 'Day', 'Hour']).reset_index(drop=True)
    
    return True, f"Successfully downloaded and processed {len(downloaded_files)} year(s) of weather data", combined_df


def debug_compare(project_root: Path = None):
    """
    Validation function to compare Chicago and Houston weather file processing.
    
    Usage: python -c "from nsrdb_downloader import debug_compare; debug_compare()"
    """
    if project_root is None:
        project_root = Path.cwd()
    
    metadata_legend_path = project_root / "Weather data" / "Metadata_legend.xlsx"
    
    print("=" * 80)
    print("WEATHER FILE PROCESSING VALIDATION")
    print("=" * 80)
    
    # Process Chicago file
    chicago_file = project_root / "Weather data" / "Weather_Chicago" / "W1998.csv"
    if chicago_file.exists():
        print(f"\n1. Processing Chicago file: {chicago_file}")
        chicago_df = process_nsrdb_file(chicago_file, metadata_legend_path)
        if chicago_df is not None:
            print(f"   ✓ Successfully processed")
            print(f"   Columns: {list(chicago_df.columns)}")
            print(f"   Dtypes:\n{chicago_df.dtypes}")
            print(f"   Shape: {chicago_df.shape}")
            print(f"   First 5 rows:")
            print(chicago_df.head())
        else:
            print(f"   ✗ Failed to process Chicago file")
    else:
        print(f"\n1. Chicago file not found: {chicago_file}")
        chicago_df = None
    
    # Process Houston file
    houston_file = project_root / "Weather_Houston" / "W1998.csv"
    if houston_file.exists():
        print(f"\n2. Processing Houston file: {houston_file}")
        houston_df = process_nsrdb_file(houston_file, metadata_legend_path)
        if houston_df is not None:
            print(f"   ✓ Successfully processed")
            print(f"   Columns: {list(houston_df.columns)}")
            print(f"   Dtypes:\n{houston_df.dtypes}")
            print(f"   Shape: {houston_df.shape}")
            print(f"   First 5 rows:")
            print(houston_df.head())
        else:
            print(f"   ✗ Failed to process Houston file")
    else:
        print(f"\n2. Houston file not found: {houston_file}")
        houston_df = None
    
    # Compare
    print(f"\n3. COMPARISON:")
    if chicago_df is not None and houston_df is not None:
        # Check columns match
        chicago_cols = set(chicago_df.columns)
        houston_cols = set(houston_df.columns)
        required_cols = {'Year', 'Month', 'Day', 'Hour', 'Temperature', 'Dew Point', 'Clearsky GHI', 'Cloud_Type'}
        
        print(f"   Required columns: {required_cols}")
        print(f"   Chicago columns: {chicago_cols}")
        print(f"   Houston columns: {houston_cols}")
        
        if chicago_cols == houston_cols:
            print(f"   ✓ Column names match!")
        else:
            print(f"   ✗ Column names differ")
            print(f"      Missing in Houston: {required_cols - houston_cols}")
            print(f"      Extra in Houston: {houston_cols - required_cols}")
        
        # Check dtypes
        print(f"\n   Dtype comparison:")
        for col in required_cols:
            if col in chicago_df.columns and col in houston_df.columns:
                chicago_dtype = chicago_df[col].dtype
                houston_dtype = houston_df[col].dtype
                match = "✓" if chicago_dtype == houston_dtype else "✗"
                print(f"   {match} {col}: Chicago={chicago_dtype}, Houston={houston_dtype}")
        
        # Check data ranges
        print(f"\n   Data range comparison:")
        for col in ['Year', 'Month', 'Day', 'Hour', 'Temperature', 'Dew Point', 'Clearsky GHI', 'Cloud_Type']:
            if col in chicago_df.columns and col in houston_df.columns:
                chicago_range = f"{chicago_df[col].min()} to {chicago_df[col].max()}"
                houston_range = f"{houston_df[col].min()} to {houston_df[col].max()}"
                print(f"   {col}: Chicago=[{chicago_range}], Houston=[{houston_range}]")
        
        print(f"\n   ✓ Validation complete!")
    elif chicago_df is None:
        print(f"   ✗ Cannot compare: Chicago file processing failed")
    elif houston_df is None:
        print(f"   ✗ Cannot compare: Houston file not found or processing failed")
    else:
        print(f"   ✗ Cannot compare: Both files missing or failed")
    
    print("=" * 80)


def compare_merged_files(project_root: Path = None):
    """
    Compare Chicago and Houston merged datasets to validate structure match.
    
    Usage: python -c "from nsrdb_downloader import compare_merged_files; compare_merged_files()"
    """
    if project_root is None:
        project_root = Path.cwd()
    
    print("=" * 80)
    print("MERGED DATASET COMPARISON (Chicago vs Houston)")
    print("=" * 80)
    
    # Load Chicago merged file
    chicago_file = project_root / "chicago_load_weather_merged.csv"
    houston_file = project_root / "houston_load_weather_merged.csv"
    
    chicago_df = None
    houston_df = None
    
    if chicago_file.exists():
        print(f"\n1. Loading Chicago merged file: {chicago_file}")
        try:
            chicago_df = pd.read_csv(chicago_file)
            print(f"   ✓ Loaded successfully")
            print(f"   Shape: {chicago_df.shape}")
        except Exception as e:
            print(f"   ✗ Failed to load: {e}")
    else:
        print(f"\n1. Chicago merged file not found: {chicago_file}")
    
    if houston_file.exists():
        print(f"\n2. Loading Houston merged file: {houston_file}")
        try:
            houston_df = pd.read_csv(houston_file)
            print(f"   ✓ Loaded successfully")
            print(f"   Shape: {houston_df.shape}")
        except Exception as e:
            print(f"   ✗ Failed to load: {e}")
    else:
        print(f"\n2. Houston merged file not found: {houston_file}")
    
    if chicago_df is None or houston_df is None:
        print("\n✗ Cannot compare: One or both files missing or failed to load")
        print("=" * 80)
        return
    
    # Standardize hour_datetime
    if 'hour_datetime' in chicago_df.columns:
        chicago_df['hour_datetime'] = pd.to_datetime(chicago_df['hour_datetime'], errors='coerce')
    if 'hour_datetime' in houston_df.columns:
        houston_df['hour_datetime'] = pd.to_datetime(houston_df['hour_datetime'], errors='coerce')
    
    print(f"\n3. COLUMN COMPARISON:")
    chicago_cols = list(chicago_df.columns)
    houston_cols = list(houston_df.columns)
    
    print(f"   Chicago columns ({len(chicago_cols)}): {chicago_cols[:5]}...")
    print(f"   Houston columns ({len(houston_cols)}): {houston_cols[:5]}...")
    
    if chicago_cols == houston_cols:
        print(f"   ✓ Column names and order match!")
    else:
        print(f"   ✗ Column names/order differ")
        if len(chicago_cols) != len(houston_cols):
            print(f"      Column count: Chicago={len(chicago_cols)}, Houston={len(houston_cols)}")
        # Find differences
        for i, (c, h) in enumerate(zip(chicago_cols, houston_cols)):
            if c != h:
                print(f"      Position {i}: Chicago='{c}' vs Houston='{h}'")
                break
    
    print(f"\n4. hour_datetime VALIDATION:")
    for name, df in [("Chicago", chicago_df), ("Houston", houston_df)]:
        if 'hour_datetime' in df.columns:
            nat_count = df['hour_datetime'].isna().sum()
            dtype = df['hour_datetime'].dtype
            is_monotonic = df['hour_datetime'].is_monotonic_increasing
            first_date = df['hour_datetime'].min()
            last_date = df['hour_datetime'].max()
            
            print(f"   {name}:")
            print(f"      dtype: {dtype}")
            print(f"      NaT count: {nat_count} {'✓' if nat_count == 0 else '✗'}")
            print(f"      Monotonic: {is_monotonic} {'✓' if is_monotonic else '✗'}")
            print(f"      Range: {first_date} to {last_date}")
        else:
            print(f"   {name}: ✗ hour_datetime column missing!")
    
    print(f"\n5. DTYPE COMPARISON:")
    common_cols = set(chicago_cols) & set(houston_cols)
    dtype_matches = 0
    dtype_diffs = []
    
    for col in common_cols:
        if col in chicago_df.columns and col in houston_df.columns:
            chicago_dtype = str(chicago_df[col].dtype)
            houston_dtype = str(houston_df[col].dtype)
            if chicago_dtype == houston_dtype:
                dtype_matches += 1
            else:
                dtype_diffs.append((col, chicago_dtype, houston_dtype))
    
    print(f"   Matching dtypes: {dtype_matches}/{len(common_cols)}")
    if dtype_diffs:
        print(f"   ✗ Dtype differences:")
        for col, c_dtype, h_dtype in dtype_diffs[:10]:  # Show first 10
            print(f"      {col}: Chicago={c_dtype}, Houston={h_dtype}")
    else:
        print(f"   ✓ All dtypes match!")
    
    print(f"\n6. ROW COUNT:")
    print(f"   Chicago: {len(chicago_df):,} rows")
    print(f"   Houston: {len(houston_df):,} rows")
    if len(chicago_df) == len(houston_df):
        print(f"   ✓ Row counts match!")
    else:
        print(f"   ✗ Row counts differ by {abs(len(chicago_df) - len(houston_df)):,}")
    
    print(f"\n7. FIRST 5 ROWS COMPARISON:")
    print(f"   Chicago:")
    print(chicago_df.head())
    print(f"\n   Houston:")
    print(houston_df.head())
    
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY:")
    
    all_checks = [
        ("Column names match", chicago_cols == houston_cols),
        ("Row counts match", len(chicago_df) == len(houston_df)),
        ("hour_datetime exists (Chicago)", 'hour_datetime' in chicago_df.columns),
        ("hour_datetime exists (Houston)", 'hour_datetime' in houston_df.columns),
        ("No NaT in hour_datetime (Chicago)", chicago_df['hour_datetime'].isna().sum() == 0 if 'hour_datetime' in chicago_df.columns else False),
        ("No NaT in hour_datetime (Houston)", houston_df['hour_datetime'].isna().sum() == 0 if 'hour_datetime' in houston_df.columns else False),
        ("All dtypes match", len(dtype_diffs) == 0),
    ]
    
    for check_name, check_result in all_checks:
        status = "✓" if check_result else "✗"
        print(f"   {status} {check_name}")
    
    all_passed = all(result for _, result in all_checks)
    if all_passed:
        print("\n   ✓ ALL VALIDATION CHECKS PASSED!")
    else:
        print("\n   ✗ SOME VALIDATION CHECKS FAILED")
    
    print("=" * 80)


def resolve_city_coords_fallback(city_label: str) -> Optional[Tuple[float, float]]:
    """
    Fallback coordinate resolver using Open-Meteo geocoding API.
    Uses local JSON cache to avoid repeated API calls.
    
    Args:
        city_label: City name (e.g., "Albuquerque NM" or "Albuquerque")
    
    Returns:
        (latitude, longitude) tuple if successful, None otherwise
    """
    # Normalize city name for cache key (lowercase, strip)
    cache_key = city_label.lower().strip()
    
    # Load cache file
    cache_file = Path("data") / "city_coords_cache.json"
    cache_file.parent.mkdir(exist_ok=True)
    
    cache = {}
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    
    # Check cache first
    if cache_key in cache:
        coords = cache[cache_key]
        return (coords['lat'], coords['lon'])
    
    # Try geocoding API
    try:
        # Use Open-Meteo geocoding API (free, no key required)
        url = f"https://geocoding-api.open-meteo.com/v1/search"
        params = {
            'name': city_label,
            'count': 1,
            'language': 'en',
            'format': 'json'
        }
        
        # Add timeout to prevent hanging
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if 'results' in data and len(data['results']) > 0:
            result = data['results'][0]
            lat = float(result['latitude'])
            lon = float(result['longitude'])
            
            # Save to cache
            cache[cache_key] = {'lat': lat, 'lon': lon}
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cache, f, indent=2)
            except Exception:
                pass  # Cache write failure is non-fatal
            
            return (lat, lon)
        
    except requests.exceptions.RequestException:
        # Network error, API timeout, etc. - return None gracefully
        pass
    except (KeyError, ValueError, TypeError) as e:
        # Invalid response format - return None gracefully
        pass
    except Exception:
        # Any other error - return None gracefully
        pass
    
    return None


def ensure_city_coordinates(city: str) -> bool:
    """
    Ensure a city has coordinates in CITY_COORDS.
    If missing, attempts to add default coordinates for common US cities.
    
    Args:
        city: City name (title case, e.g., "Houston")
    
    Returns:
        True if coordinates exist or were added, False otherwise
    """
    city_lower = city.lower()
    
    # If already exists, return True
    if city_lower in CITY_COORDS:
        return True
    
    # Default coordinates for common US cities (can be expanded)
    default_coords = {
        'atlanta': (33.7490, -84.3880),
        'boston': (42.3601, -71.0589),
        'charlotte': (35.2271, -80.8431),
        'chicago': (41.8781, -87.6298),
        'dallas': (32.7767, -96.7970),
        'denver': (39.7392, -104.9903),
        'detroit': (42.3314, -83.0458),
        'houston': (29.7604, -95.3698),
        'indianapolis': (39.7684, -86.1581),
        'jacksonville': (30.3322, -81.6557),
        'las vegas': (36.1699, -115.1398),
        'los angeles': (34.0522, -118.2437),
        'memphis': (35.1495, -90.0490),
        'miami': (25.7617, -80.1918),
        'milwaukee': (43.0389, -87.9065),
        'minneapolis': (44.9778, -93.2650),
        'nashville': (36.1627, -86.7816),
        'new orleans': (29.9511, -90.0715),
        'new york': (40.7128, -74.0060),
        'oklahoma city': (35.4676, -97.5164),
        'philadelphia': (39.9526, -75.1652),
        'phoenix': (33.4484, -112.0740),
        'portland': (45.5152, -122.6784),
        'san antonio': (29.4241, -98.4936),
        'san diego': (32.7157, -117.1611),
        'san francisco': (37.7749, -122.4194),
        'san jose': (37.3382, -121.8863),
        'seattle': (47.6062, -122.3321),
        'tucson': (32.2226, -110.9747),
        'washington': (38.9072, -77.0369),
    }
    
    if city_lower in default_coords:
        CITY_COORDS[city_lower] = default_coords[city_lower]
        print(f"Added coordinates for {city}: {CITY_COORDS[city_lower]}")
        return True
    
    return False
