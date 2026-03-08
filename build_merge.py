"""
Build Merged Dataset Module

Aggregates 30-minute load profiles to hourly and merges with weather data
to create the final merged dataset matching Chicago format.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Tuple


def aggregate_load_profile(city: str, project_root: Path = None, load_file_path: Optional[Path] = None) -> Optional[pd.DataFrame]:
    """
    Load and aggregate 30-minute load profile to hourly
    
    Args:
        city: City name
        project_root: Project root directory
        load_file_path: Optional explicit path to load file (for OpenEI downloaded files)
    
    Returns:
        DataFrame with hourly load data and hour_datetime column
    """
    if project_root is None:
        project_root = Path.cwd()
    
    # Determine load file path
    if load_file_path is None:
        # Try LoadProfiles folder first (for OpenEI downloads)
        load_file = project_root / "LoadProfiles" / f"{city}_SimulatedLoadProfile.csv"
        if not load_file.exists():
            # Fallback to project root (legacy location)
            load_file = project_root / f"{city}_SimulatedLoadProfile.csv"
    else:
        load_file = load_file_path
    
    if not load_file.exists():
        return None
    
    # Load CSV - use openei_loader for proper parsing if available
    try:
        from openei_loader import load_openei_csv
        load_df = load_openei_csv(load_file)
    except ImportError:
        # Fallback to standard pandas read
        load_df = pd.read_csv(load_file, header=0, low_memory=False)
        # Strip whitespace and remove unnamed columns
        load_df.columns = load_df.columns.str.strip()
        load_df = load_df.loc[:, ~load_df.columns.str.contains('^Unnamed', case=False)]
    
    if load_df is None or len(load_df) == 0:
        return None
    
    # Exclude unnamed/index columns and identify building columns
    exclude_cols = [c for c in load_df.columns if c.startswith('Unnamed') or c == '' or c.lower() in ['index', 'time', 'datetime', 'date']]
    
    # All remaining columns should be building load data (numeric)
    # Convert to numeric, coercing errors
    building_cols = []
    for col in load_df.columns:
        if col not in exclude_cols:
            load_df[col] = pd.to_numeric(load_df[col], errors='coerce')
            building_cols.append(col)
    
    if len(building_cols) == 0:
        return None
    
    # Aggregate 30-min to hourly (mean of every 2 rows)
    # Group by hour (assuming 2 rows per hour for 30-min data)
    load_df['hour_index'] = load_df.index // 2
    hourly_load = load_df.groupby('hour_index')[building_cols].mean().reset_index(drop=True)
    
    # Create hour_datetime starting from 1998-01-01 00:00:00
    hourly_load['hour_datetime'] = pd.date_range(
        '1998-01-01 00:00:00',
        periods=len(hourly_load),
        freq='h'
    )
    
    # Ensure hour_datetime is datetime64[ns]
    hourly_load['hour_datetime'] = pd.to_datetime(hourly_load['hour_datetime'], errors='coerce')
    
    return hourly_load


def merge_load_weather(
    city: str,
    project_root: Path = None,
    use_nsrdb: bool = False,
    weather_df: Optional[pd.DataFrame] = None,
    load_file_path: Optional[Path] = None
) -> Optional[pd.DataFrame]:
    """
    Merge hourly load profile with weather data
    
    Args:
        city: City name
        project_root: Project root directory
        use_nsrdb: If True, use NSRDB weather data; if False, use local weather files
        weather_df: Optional pre-loaded weather DataFrame (if provided, use this instead)
        load_file_path: Optional explicit path to load file
    
    Returns:
        Merged DataFrame with hour_datetime, building columns, and weather columns
    """
    if project_root is None:
        project_root = Path.cwd()
    
    # Aggregate load profile - this creates hour_datetime from load data
    load_df = aggregate_load_profile(city, project_root, load_file_path=load_file_path)
    if load_df is None:
        return None
    
    # CRITICAL: hour_datetime must come from load_df (already created in aggregate_load_profile)
    # Ensure it's datetime64[ns] type and has no NaT values
    if 'hour_datetime' not in load_df.columns:
        load_df['hour_datetime'] = pd.date_range('1998-01-01 00:00:00', periods=len(load_df), freq='h')
    
    # Ensure hour_datetime is proper datetime type
    load_df['hour_datetime'] = pd.to_datetime(load_df['hour_datetime'], errors='coerce')
    
    # Load weather data
    if weather_df is not None:
        # Use provided weather DataFrame - create hour_datetime for merging
        weather_df = weather_df.copy()
        if 'hour_datetime' not in weather_df.columns:
            weather_df['hour_datetime'] = pd.to_datetime(
                weather_df[['Year', 'Month', 'Day', 'Hour']],
                errors='coerce'
            )
    elif use_nsrdb:
        # Use NSRDB weather data from files
        weather_df = combine_nsrdb_weather_files(city, project_root)
        if weather_df is not None:
            weather_df = weather_df.copy()
            weather_df['hour_datetime'] = pd.to_datetime(
                weather_df[['Year', 'Month', 'Day', 'Hour']],
                errors='coerce'
            )
    else:
        # Use local weather files (for Chicago)
        weather_df = load_local_weather(city, project_root)
        if weather_df is not None:
            weather_df = weather_df.copy()
            weather_df['hour_datetime'] = pd.to_datetime(
                weather_df[['Year', 'Month', 'Day', 'Hour']],
                errors='coerce'
            )
    
    if weather_df is None:
        return None
    
    # Ensure weather hour_datetime exists and is datetime type
    if 'hour_datetime' not in weather_df.columns:
        weather_df['hour_datetime'] = pd.to_datetime(
            weather_df[['Year', 'Month', 'Day', 'Hour']],
            errors='coerce'
        )
    else:
        weather_df['hour_datetime'] = pd.to_datetime(weather_df['hour_datetime'], errors='coerce')
    
    # Select weather columns (match Chicago format exactly)
    weather_cols = ['hour_datetime', 'Temperature', 'Dew Point', 'Clearsky GHI', 'Cloud_Type']
    if 'Cloud_Type_Label' in weather_df.columns:
        weather_cols.append('Cloud_Type_Label')
    
    # Ensure all weather columns exist
    available_weather_cols = [c for c in weather_cols if c in weather_df.columns]
    weather_subset = weather_df[available_weather_cols].copy()
    
    # Merge on hour_datetime using left join (preserve all load rows, match weather where available)
    # This matches SAS logic: keep all hourly load rows, join weather by time
    # CRITICAL: load_df's hour_datetime is the source of truth - it determines the timeline
    merged_df = pd.merge(
        load_df,
        weather_subset,
        on='hour_datetime',
        how='left'  # Left join to preserve all load profile rows
    )
    
    # Ensure hour_datetime is preserved and is datetime64[ns] type
    merged_df['hour_datetime'] = pd.to_datetime(merged_df['hour_datetime'], errors='coerce')
    
    # Remove any rows where hour_datetime is NaT (shouldn't happen, but safety check)
    merged_df = merged_df.dropna(subset=['hour_datetime'])
    
    # Reorder columns: hour_datetime first, then building columns, then weather
    # Match Chicago format exactly: hour_datetime, building_cols..., Temperature, Dew Point, Clearsky GHI, Cloud_Type
    building_cols = [c for c in merged_df.columns 
                     if c not in ['hour_datetime', 'Temperature', 'Dew Point', 
                                 'Clearsky GHI', 'Cloud_Type', 'Cloud_Type_Label',
                                 'Year', 'Month', 'Day', 'Hour']]
    
    col_order = ['hour_datetime'] + building_cols + ['Temperature', 'Dew Point', 
                                                      'Clearsky GHI', 'Cloud_Type']
    if 'Cloud_Type_Label' in merged_df.columns:
        col_order.append('Cloud_Type_Label')
    
    # Ensure all columns exist
    col_order = [c for c in col_order if c in merged_df.columns]
    merged_df = merged_df[col_order]
    
    return merged_df


def load_local_weather(city: str, project_root: Path = None) -> Optional[pd.DataFrame]:
    """
    Load local weather files (for Chicago)
    
    This is the existing method for loading Chicago weather from W*.csv files
    """
    if project_root is None:
        project_root = Path.cwd()
    
    if city.lower() != "chicago":
        return None
    
    weather_dir = project_root / "Weather data" / "Weather_Chicago"
    if not weather_dir.exists():
        return None
    
    weather_files = sorted(weather_dir.glob("W*.csv"))
    if not weather_files:
        return None
    
    dfs = []
    for file in weather_files:
        df = pd.read_csv(file)
        dfs.append(df)
    
    weather_df = pd.concat(dfs, ignore_index=True)
    
    # Standardize column names
    weather_df.columns = weather_df.columns.str.strip()
    
    # Ensure required columns exist
    required = ['Year', 'Month', 'Day', 'Hour', 'Temperature', 'Dew Point', 'Clearsky GHI']
    if not all(c in weather_df.columns for c in required):
        return None
    
    # Add Cloud_Type if missing
    if 'Cloud_Type' not in weather_df.columns and 'Cloud Type' in weather_df.columns:
        weather_df['Cloud_Type'] = weather_df['Cloud Type']
    
    # Add Cloud_Type_Label using metadata
    metadata_file = project_root / "Weather data" / "Metadata_legend.xlsx"
    if metadata_file.exists():
        try:
            from nsrdb_downloader import load_cloud_type_mapping
            cloud_mapping = load_cloud_type_mapping(metadata_file)
            if cloud_mapping and 'Cloud_Type' in weather_df.columns:
                weather_df['Cloud_Type_Label'] = weather_df['Cloud_Type'].map(
                    cloud_mapping
                ).fillna('Unknown')
        except:
            pass
    
    if 'Cloud_Type_Label' not in weather_df.columns:
        weather_df['Cloud_Type_Label'] = 'Unknown'
    
    return weather_df


def combine_nsrdb_weather_files(city: str, project_root: Path = None) -> Optional[pd.DataFrame]:
    """
    Combine NSRDB weather files for a city into one DataFrame
    Uses Weather_<city> folder structure (e.g., Weather_Houston)
    """
    if project_root is None:
        project_root = Path.cwd()
    
    city_lower = city.lower()
    # Use Weather_<city> folder structure
    weather_dir = project_root / f"Weather_{city}"
    
    if not weather_dir.exists():
        return None
    
    # Find all weather files (W*.csv format)
    weather_files = sorted(weather_dir.glob("W*.csv"))
    if not weather_files:
        return None
    
    # Process and combine
    try:
        from nsrdb_downloader import process_nsrdb_file
        metadata_legend_path = project_root / "Weather data" / "Metadata_legend.xlsx"
        
        dfs = []
        for file_path in weather_files:
            df = process_nsrdb_file(file_path, metadata_legend_path)
            if df is not None:
                dfs.append(df)
        
        if not dfs:
            return None
        
        # Combine
        combined_df = pd.concat(dfs, ignore_index=True)
        combined_df = combined_df.sort_values(['Year', 'Month', 'Day', 'Hour']).reset_index(drop=True)
        
        return combined_df
    except Exception as e:
        print(f"Error combining NSRDB weather files: {e}")
        return None


def build_and_save_merged(
    city: str,
    project_root: Path = None,
    use_nsrdb: bool = False,
    weather_df: Optional[pd.DataFrame] = None,
    load_file_path: Optional[Path] = None
) -> Tuple[bool, str]:
    """
    Build merged dataset and save to CSV
    
    Args:
        city: City name
        project_root: Project root directory
        use_nsrdb: If True, use NSRDB weather; if False, use local files
        weather_df: Optional pre-loaded weather DataFrame
        load_file_path: Optional explicit path to load file
    
    Returns:
        (success: bool, message: str)
    """
    if project_root is None:
        project_root = Path.cwd()
    
    # Build merged dataset
    merged_df = merge_load_weather(city, project_root, use_nsrdb=use_nsrdb, weather_df=weather_df, load_file_path=load_file_path)
    
    if merged_df is None:
        return False, "Failed to build merged dataset. Check that load profile and weather data exist."
    
    # Validate merged dataset
    # Check hour_datetime
    if 'hour_datetime' not in merged_df.columns:
        return False, "Validation failed: hour_datetime column missing in merged dataset"
    
    nat_count = merged_df['hour_datetime'].isna().sum()
    if nat_count > 0:
        return False, f"Validation failed: hour_datetime contains {nat_count} NaT values"
    
    # Check weather columns exist (can have missing values but must exist)
    required_weather_cols = ['Temperature', 'Dew Point', 'Clearsky GHI', 'Cloud_Type']
    missing_cols = [c for c in required_weather_cols if c not in merged_df.columns]
    if missing_cols:
        return False, f"Validation failed: Missing weather columns: {missing_cols}"
    
    # Expected row count: 148,920 hours for 1998-2014 (17 years * 365.25 days * 24 hours)
    expected_rows = 148920
    if len(merged_df) != expected_rows:
        print(f"Warning: Merged dataset has {len(merged_df)} rows, expected {expected_rows} (1998-2014 hourly)")
    
    # Save to CSV
    city_lower = city.lower()
    output_file = project_root / f"{city_lower}_load_weather_merged.csv"
    
    # Safety: Do NOT overwrite existing merged files (especially Chicago)
    if output_file.exists() and city_lower == "chicago":
        return False, f"Cannot overwrite Chicago merged file: {output_file.name}"
    
    try:
        merged_df.to_csv(output_file, index=False)
        return True, f"Successfully created merged dataset: {output_file.name} ({len(merged_df):,} rows)"
    except Exception as e:
        return False, f"Error saving merged dataset: {e}"
