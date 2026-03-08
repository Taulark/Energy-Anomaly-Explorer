"""
NSRDB Weather Data Download and Processing Module

Downloads weather data from NREL NSRDB API and processes it to match
Chicago weather format with columns: Temperature, Dew Point, Clearsky GHI, Cloud_Type
"""

import requests
import pandas as pd
import numpy as np
from pathlib import Path
import time
import os
from typing import Optional, Tuple, Dict

# City coordinates (lat, lon)
CITY_COORDS = {
    'chicago': (41.8781, -87.6298),
    'houston': (29.7604, -95.3698),
}

# NSRDB API configuration
NSRDB_API_BASE = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb_data_download.json"
NSRDB_ATTRIBUTES = {
    'temperature': 'air_temperature',  # Dry bulb temperature
    'dew_point': 'dew_point',          # Dew point temperature
    'clearsky_ghi': 'clearsky_ghi',    # Clearsky GHI
    'cloud_type': 'cloud_type',        # Cloud type (if available)
    'cloud_cover': 'cloud_type',       # Fallback if cloud_type not available
}

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
        # Try to read the Excel file
        df = pd.read_excel(metadata_file, sheet_name=0)
        
        # Look for cloud type columns (case-insensitive)
        cloud_cols = [c for c in df.columns if 'cloud' in c.lower() and 'type' in c.lower()]
        code_cols = [c for c in df.columns if any(x in c.lower() for x in ['code', 'value', 'id', 'number'])]
        label_cols = [c for c in df.columns if any(x in c.lower() for x in ['label', 'name', 'description', 'meaning'])]
        
        if cloud_cols and (code_cols or label_cols):
            # Try to find code and label columns
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
        
        # Fallback: if structure is unclear, return default mapping
        return get_default_cloud_mapping()
        
    except Exception as e:
        print(f"Warning: Could not load cloud type mapping from {metadata_file}: {e}")
        return get_default_cloud_mapping()


def get_default_cloud_mapping() -> Dict[int, str]:
    """
    Default cloud type mapping (NSRDB standard)
    Based on common cloud type codes
    """
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
    email: str = "example@example.com",
    interval: int = 60,
    output_dir: Path = None
) -> Optional[Path]:
    """
    Download NSRDB data for a single year
    
    Args:
        lat: Latitude
        lon: Longitude
        year: Year to download
        api_key: NSRDB API key
        email: Email for API (required by NSRDB)
        interval: Time interval in minutes (60 for hourly)
        output_dir: Directory to save the file
    
    Returns:
        Path to downloaded file, or None if failed
    """
    if output_dir is None:
        output_dir = Path.cwd()
    
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"NSRDB_{year}.csv"
    
    # Check if file already exists (caching)
    if output_file.exists():
        print(f"  Using cached file: {output_file}")
        return output_file
    
    # Prepare API request
    params = {
        'api_key': api_key,
        'email': email,
        'lat': lat,
        'lon': lon,
        'year': year,
        'interval': interval,
        'attributes': ','.join([
            NSRDB_ATTRIBUTES['temperature'],
            NSRDB_ATTRIBUTES['dew_point'],
            NSRDB_ATTRIBUTES['clearsky_ghi'],
            NSRDB_ATTRIBUTES['cloud_type'],
        ]),
        'utc': 'false',  # Local time
    }
    
    try:
        print(f"  Downloading {year}...")
        response = requests.get(NSRDB_API_BASE, params=params, timeout=300)
        response.raise_for_status()
        
        data = response.json()
        
        # Check for errors
        if 'errors' in data:
            error_msg = data.get('errors', ['Unknown error'])
            raise Exception(f"NSRDB API error: {error_msg}")
        
        if 'outputs' in data:
            outputs = data['outputs']
            
            # Try downloadUrl first
            if 'downloadUrl' in outputs:
                download_url = outputs['downloadUrl']
                print(f"  Fetching from URL: {download_url}")
                file_response = requests.get(download_url, timeout=600)
                file_response.raise_for_status()
                
                # Save to file
                with open(output_file, 'wb') as f:
                    f.write(file_response.content)
            
            # Try direct CSV data
            elif 'csv' in outputs:
                csv_data = outputs['csv']
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(csv_data)
            
            # Try downloadUrl in nested structure
            elif isinstance(outputs, dict):
                for key, value in outputs.items():
                    if isinstance(value, dict) and 'downloadUrl' in value:
                        download_url = value['downloadUrl']
                        print(f"  Fetching from URL: {download_url}")
                        file_response = requests.get(download_url, timeout=600)
                        file_response.raise_for_status()
                        
                        with open(output_file, 'wb') as f:
                            f.write(file_response.content)
                        break
                else:
                    raise Exception("No download URL or CSV data found in API response")
            else:
                raise Exception("Unexpected API response format")
        else:
            raise Exception("No 'outputs' key in API response")
        
        print(f"  Saved to: {output_file}")
        return output_file
        
    except requests.exceptions.RequestException as e:
        print(f"  Error downloading {year}: {e}")
        return None
    except Exception as e:
        print(f"  Error processing {year}: {e}")
        if output_file.exists():
            output_file.unlink()  # Remove partial file
        return None


def process_nsrdb_file(file_path: Path) -> Optional[pd.DataFrame]:
    """
    Process a downloaded NSRDB CSV file to match Chicago format
    
    Returns DataFrame with columns: Year, Month, Day, Hour, Temperature, Dew Point, Clearsky GHI, Cloud_Type
    """
    try:
        # Read CSV - NSRDB format varies, try common formats
        # Try reading with different skiprow values
        df = None
        for skip_rows in [0, 1, 2]:
            try:
                df = pd.read_csv(file_path, skiprows=skip_rows, low_memory=False)
                # Check if we have reasonable columns
                if len(df.columns) > 3 and len(df) > 100:
                    break
            except:
                continue
        
        if df is None or len(df) == 0:
            raise ValueError("Could not read NSRDB file")
        
        # Standardize column names (case-insensitive, handle spaces)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Map NSRDB columns to our standard names
        column_mapping = {}
        
        # Temperature (dry bulb)
        temp_cols = [c for c in df.columns if any(x in c for x in ['temp', 'air_temp', 'temperature'])]
        if temp_cols:
            column_mapping[temp_cols[0]] = 'Temperature'
        
        # Dew Point
        dew_cols = [c for c in df.columns if 'dew' in c and 'point' in c]
        if dew_cols:
            column_mapping[dew_cols[0]] = 'Dew Point'
        
        # Clearsky GHI
        ghi_cols = [c for c in df.columns if 'ghi' in c or 'clearsky' in c]
        if ghi_cols:
            column_mapping[ghi_cols[0]] = 'Clearsky GHI'
        
        # Cloud Type
        cloud_cols = [c for c in df.columns if 'cloud' in c and 'type' in c]
        if not cloud_cols:
            # Try cloud cover as fallback
            cloud_cols = [c for c in df.columns if 'cloud' in c and 'cover' in c]
        
        if cloud_cols:
            column_mapping[cloud_cols[0]] = 'Cloud_Type_Raw'
        
        # Rename columns
        df = df.rename(columns=column_mapping)
        
        # Extract datetime components
        # NSRDB typically has Year, Month, Day, Hour columns or a datetime column
        col_lower = {c.lower(): c for c in df.columns}
        if all(c in col_lower for c in ['year', 'month', 'day', 'hour']):
            # Already have components - standardize case
            df['Year'] = df[col_lower['year']]
            df['Month'] = df[col_lower['month']]
            df['Day'] = df[col_lower['day']]
            df['Hour'] = df[col_lower['hour']]
        elif 'datetime' in df.columns or 'date' in df.columns or 'time' in df.columns:
            # Parse datetime
            dt_col = next((c for c in ['datetime', 'date', 'time'] if c in df.columns), None)
            if dt_col:
                df[dt_col] = pd.to_datetime(df[dt_col], errors='coerce')
                df['Year'] = df[dt_col].dt.year
                df['Month'] = df[dt_col].dt.month
                df['Day'] = df[dt_col].dt.day
                df['Hour'] = df[dt_col].dt.hour
            else:
                raise ValueError("Could not find datetime column")
        else:
            # Create from index (assume hourly data starting from year in filename or 1998)
            # Try to extract year from filename
            try:
                year_from_file = int(file_path.stem.split('_')[-1])
            except:
                year_from_file = 1998
            
            # Create datetime index
            start_date = pd.Timestamp(f'{year_from_file}-01-01 00:00:00')
            df['hour_datetime'] = pd.date_range(start_date, periods=len(df), freq='H')
            df['Year'] = df['hour_datetime'].dt.year
            df['Month'] = df['hour_datetime'].dt.month
            df['Day'] = df['hour_datetime'].dt.day
            df['Hour'] = df['hour_datetime'].dt.hour
        
        # Ensure required columns exist
        required_cols = ['Year', 'Month', 'Day', 'Hour', 'Temperature', 'Dew Point', 'Clearsky GHI']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Process Cloud_Type
        if 'Cloud_Type_Raw' in df.columns:
            # Convert cloud cover % to discrete categories if needed
            cloud_raw = df['Cloud_Type_Raw']
            
            # Check if it's already discrete (integers 0-12)
            if cloud_raw.dtype in [np.int64, np.int32, np.int16]:
                df['Cloud_Type'] = cloud_raw.astype(int)
            else:
                # Convert percentage to discrete categories
                # 0-10% = 0 (Clear), 10-25% = 1, 25-50% = 2, etc.
                df['Cloud_Type'] = pd.cut(
                    cloud_raw,
                    bins=[-1, 10, 25, 50, 75, 90, 100],
                    labels=[0, 1, 2, 3, 4, 5]
                ).astype(int)
            
            df = df.drop(columns=['Cloud_Type_Raw'])
        else:
            # Default to clear sky
            df['Cloud_Type'] = 0
        
        # Select and reorder columns
        output_cols = ['Year', 'Month', 'Day', 'Hour', 'Temperature', 'Dew Point', 'Clearsky GHI', 'Cloud_Type']
        df = df[output_cols].copy()
        
        # Remove rows with missing critical data
        df = df.dropna(subset=['Temperature', 'Dew Point', 'Clearsky GHI'])
        
        return df
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None


def download_city_weather(
    city: str,
    api_key: str,
    email: str = "example@example.com",
    years: list = None,
    project_root: Path = None,
    progress_callback=None
) -> Tuple[bool, str]:
    """
    Download weather data for a city from NSRDB
    
    Args:
        city: City name (will be lowercased)
        api_key: NSRDB API key
        email: Email for API
        years: List of years to download (default: 1998-2014)
        project_root: Project root directory
        progress_callback: Optional function(year, total) for progress updates
    
    Returns:
        (success: bool, message: str)
    """
    if project_root is None:
        project_root = Path.cwd()
    
    city_lower = city.lower()
    
    if city_lower not in CITY_COORDS:
        return False, f"City '{city}' not in configured coordinates. Available: {list(CITY_COORDS.keys())}"
    
    lat, lon = CITY_COORDS[city_lower]
    
    if years is None:
        years = DEFAULT_YEARS
    
    # Create output directory
    output_dir = project_root / "Weather data" / city
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Download each year
    downloaded_files = []
    for i, year in enumerate(years):
        if progress_callback:
            progress_callback(i + 1, len(years))
        
        file_path = download_nsrdb_year(lat, lon, year, api_key, email, output_dir=output_dir)
        if file_path:
            downloaded_files.append(file_path)
        else:
            return False, f"Failed to download weather data for {year}"
        
        # Rate limiting
        if i < len(years) - 1:
            time.sleep(1)
    
    if not downloaded_files:
        return False, "No files were downloaded"
    
    return True, f"Successfully downloaded {len(downloaded_files)} year(s) of weather data"


def combine_weather_files(city: str, project_root: Path = None) -> Optional[pd.DataFrame]:
    """
    Combine all NSRDB weather files for a city into one DataFrame
    
    Returns DataFrame with standardized columns matching Chicago format
    """
    if project_root is None:
        project_root = Path.cwd()
    
    city_lower = city.lower()
    weather_dir = project_root / "Weather data" / city
    
    if not weather_dir.exists():
        return None
    
    # Find all NSRDB files
    weather_files = sorted(weather_dir.glob("NSRDB_*.csv"))
    if not weather_files:
        return None
    
    # Process and combine
    dfs = []
    for file_path in weather_files:
        df = process_nsrdb_file(file_path)
        if df is not None:
            dfs.append(df)
    
    if not dfs:
        return None
    
    # Combine
    combined_df = pd.concat(dfs, ignore_index=True)
    
    # Sort by datetime
    combined_df = combined_df.sort_values(['Year', 'Month', 'Day', 'Hour']).reset_index(drop=True)
    
    # Add Cloud_Type_Label using metadata
    metadata_file = project_root / "Weather data" / "Metadata_legend.xlsx"
    cloud_mapping = load_cloud_type_mapping(metadata_file)
    
    if cloud_mapping:
        combined_df['Cloud_Type_Label'] = combined_df['Cloud_Type'].map(
            cloud_mapping
        ).fillna('Unknown')
    else:
        combined_df['Cloud_Type_Label'] = 'Unknown'
    
    return combined_df
