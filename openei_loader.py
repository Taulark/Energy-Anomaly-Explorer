"""
OpenEI Load Profile Downloader Module

Fetches city list and downloads load profiles from OpenEI Submission 515:
https://data.openei.org/submissions/515
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Tuple
import re
import time


OPENEI_SUBMISSION_URL = "https://data.openei.org/submissions/515"


def fetch_openei_city_resources() -> Dict[str, Dict[str, str]]:
    """
    Fetch and parse OpenEI submission 515 to extract city resources.
    
    Returns:
        Dict mapping clean city key to city info:
        {
            "Houston": {
                "display": "Houston TX",
                "url": "https://data.openei.org/.../file.csv"
            },
            ...
        }
    """
    try:
        print(f"Fetching OpenEI submission 515 from {OPENEI_SUBMISSION_URL}")
        response = requests.get(OPENEI_SUBMISSION_URL, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all resource links that match the pattern: "<City> <State> Commercial Simulated Load Profiles 1998-2014.csv"
        city_resources = {}
        
        # Look for download links in the resources section
        # OpenEI typically has links in <a> tags with href containing the file
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Pattern: "<City> <State> Commercial Simulated Load Profiles 1998-2014.csv"
            # Or variations like "Download ...MB" with the city name nearby
            if 'Commercial Simulated Load Profiles' in text or 'Simulated Load Profile' in text:
                # Extract city name from text
                # Pattern: "City State Commercial Simulated Load Profiles..."
                match = re.search(r'^([A-Z][a-zA-Z\s]+?)\s+([A-Z]{2})\s+Commercial', text)
                if match:
                    city_name = match.group(1).strip()
                    state = match.group(2).strip()
                    display_name = f"{city_name} {state}"
                    
                    # Create clean city key (just city name, title case)
                    clean_key = city_name.strip()
                    
                    # Get download URL
                    if href.startswith('http'):
                        url = href
                    elif href.startswith('/'):
                        url = f"https://data.openei.org{href}"
                    else:
                        # Look for data-openei.org base
                        url = f"https://data.openei.org{href}" if not href.startswith('http') else href
                    
                    if clean_key and url:
                        city_resources[clean_key] = {
                            "display": display_name,
                            "url": url
                        }
        
        # Alternative: Look for download buttons or resource tables
        if not city_resources:
            # Try finding resource table or list
            resource_divs = soup.find_all(['div', 'table', 'ul'], class_=re.compile(r'resource|file|download', re.I))
            
            for div in resource_divs:
                # Look for text containing city names and CSV files
                text_content = div.get_text()
                if 'Simulated Load Profile' in text_content or 'Commercial' in text_content:
                    # Try to extract city names and URLs from this section
                    links_in_div = div.find_all('a', href=True)
                    for link in links_in_div:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        
                        # Check if this looks like a download link
                        if '.csv' in href.lower() or 'download' in text.lower() or 'mb' in text.lower():
                            # Try to find city name in nearby text
                            parent_text = div.get_text()
                            match = re.search(r'([A-Z][a-zA-Z\s]+?)\s+([A-Z]{2})\s+Commercial', parent_text)
                            if match:
                                city_name = match.group(1).strip()
                                state = match.group(2).strip()
                                display_name = f"{city_name} {state}"
                                clean_key = city_name.strip()
                                
                                if href.startswith('http'):
                                    url = href
                                elif href.startswith('/'):
                                    url = f"https://data.openei.org{href}"
                                else:
                                    url = f"https://data.openei.org{href}"
                                
                                if clean_key and url and clean_key not in city_resources:
                                    city_resources[clean_key] = {
                                        "display": display_name,
                                        "url": url
                                    }
        
        print(f"Found {len(city_resources)} cities in OpenEI submission 515")
        return city_resources
        
    except Exception as e:
        print(f"Error fetching OpenEI resources: {e}")
        # Return empty dict on error - app will handle gracefully
        return {}


def download_load_profile(city: str, url: str, dest_path: Path, progress_callback=None) -> Tuple[bool, str]:
    """
    Download load profile CSV from OpenEI URL.
    
    Args:
        city: City name (for logging)
        url: Download URL
        dest_path: Destination file path
        progress_callback: Optional callback function(year, message)
    
    Returns:
        (success: bool, message: str)
    """
    # Check if file already exists (caching)
    if dest_path.exists():
        if progress_callback:
            progress_callback(None, f"Load profile already exists: {dest_path.name}")
        return True, f"Load profile already cached: {dest_path.name}"
    
    try:
        if progress_callback:
            progress_callback(None, f"Downloading load profile from OpenEI...")
        
        print(f"Downloading {city} load profile from {url}")
        response = requests.get(url, timeout=120, stream=True)
        response.raise_for_status()
        
        # Save to file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        if progress_callback:
            progress_callback(None, f"Downloaded: {dest_path.name}")
        
        print(f"Successfully downloaded {city} load profile to {dest_path}")
        return True, f"Downloaded load profile: {dest_path.name}"
        
    except Exception as e:
        error_msg = f"Error downloading load profile for {city}: {e}"
        print(error_msg)
        if progress_callback:
            progress_callback(None, f"Error: {error_msg}")
        return False, error_msg


def load_openei_csv(file_path: Path) -> Optional[pd.DataFrame]:
    """
    Load OpenEI CSV file with proper header handling.
    
    OpenEI CSVs have:
    - Row 1: Building type names (header)
    - Row 2+: Actual load data (30-min samples from 1998-01-01 00:00 to 2014-12-31 23:30)
    - First column: 30-min timestamps or indices
    
    Returns:
        DataFrame with building columns as numeric
    """
    try:
        # Read CSV - first row is header
        df = pd.read_csv(file_path, header=0, low_memory=False)
        
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        
        # Remove unnamed columns (typically index columns)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False)]
        
        # Remove empty columns
        df = df.dropna(axis=1, how='all')
        
        # Convert building columns to numeric (exclude any datetime/index columns)
        # The first column might be timestamps or indices - keep it as is for now
        # All other columns should be building load data (numeric)
        for col in df.columns[1:]:  # Skip first column
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove any columns that are all NaN
        df = df.dropna(axis=1, how='all')
        
        return df
        
    except Exception as e:
        print(f"Error loading OpenEI CSV {file_path}: {e}")
        return None
