# ⚡ Energy Anomaly Explorer

A Streamlit dashboard for detecting energy consumption anomalies in building load profiles using linear regression and z-score analysis.

## Features

- **Multi-city support**: Auto-detects cities from data files
- **Automatic data loading**: Uses merged data if available, otherwise builds from raw load profiles and weather data
- **Anomaly detection**: Linear regression baseline with z-score thresholding
- **Interactive visualizations**: Plotly charts showing actual vs predicted load and anomalies
- **Public URL**: Automatically creates a public tunnel (Cloudflare or ngrok) for easy access

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Tunnel Software (Choose One)

#### Option A: Cloudflare Tunnel (Recommended)

**macOS:**
```bash
brew install cloudflare/cloudflare/cloudflared
```

**Linux:**
```bash
# Download and install from:
# https://github.com/cloudflare/cloudflared/releases
```

**Windows:**
Download from: https://github.com/cloudflare/cloudflared/releases

**Verify installation:**
```bash
cloudflared --version
```

#### Option B: ngrok (Fallback)

If Cloudflare Tunnel is not available, the script will automatically use `pyngrok` (installed via pip). Alternatively, you can install ngrok manually:

**macOS:**
```bash
brew install ngrok/ngrok/ngrok
```

**Linux/Windows:**
Download from: https://ngrok.com/download

## Usage

### Quick Start

Simply run:

```bash
python run_public.py
```

This will:
1. Start Streamlit on port 8501
2. Create a public tunnel (Cloudflare or ngrok)
3. Print the public URL to the console
4. Keep running until you press Ctrl+C

### Manual Streamlit (Local Only)

If you only want to run locally without a tunnel:

```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Data Requirements

The dashboard expects data files in the project root directory:

### Required Files

- **Merged data (preferred)**: `<city>_load_weather_merged.csv`
  - Example: `chicago_load_weather_merged.csv`
  - Must contain: `hour_datetime`, building columns, weather columns

- **Raw load profiles**: `<City>_SimulatedLoadProfile.csv`
  - Example: `Chicago_SimulatedLoadProfile.csv`
  - 30-minute interval data (will be aggregated to hourly)

- **Weather data**:
  - **Chicago (local)**: `Weather data/Weather/W*.csv`
    - Example: `Weather data/Weather/W1998.csv`, `W1999.csv`, etc.
    - Must contain: `Year`, `Month`, `Day`, `Hour`, `Temperature`, `Dew Point`, `Clearsky GHI`
  - **Other cities (NSRDB)**: `Weather data/<City>/NSRDB_*.csv`
    - Automatically downloaded from NSRDB API
    - Contains same columns as Chicago format

### Data Loading Logic

1. If `<city>_load_weather_merged.csv` exists → load directly
2. Else if `<City>_SimulatedLoadProfile.csv` exists:
   - Aggregate 30-min data to hourly (mean)
   - Load weather files:
     - **Chicago**: From `Weather data/Weather/`
     - **Other cities**: From `Weather data/<City>/` (NSRDB downloaded)
   - Merge load and weather data
3. If weather data is missing → show download/build button in sidebar

## NSRDB Weather Data Download (Houston & Other Cities)

For cities without pre-existing weather data (like Houston), the dashboard can automatically download weather data from the NREL NSRDB API.

### Getting an NSRDB API Key

1. Visit https://developer.nrel.gov/
2. Sign up for a free account
3. Generate an API key from the dashboard
4. Copy your API key

### Setting Up the API Key

**Option 1: Environment Variable (Recommended)**
```bash
export NSRDB_API_KEY="your_api_key_here"
```

**Option 2: Enter in Dashboard**
- When you select a city without merged data, a sidebar section will appear
- Enter your API key and email in the input fields
- Click "Download Weather + Build Merged Dataset"

### How It Works

1. **Download**: Fetches hourly weather data from NSRDB for years 1998-2014
   - Saves to `Weather data/<City>/NSRDB_<year>.csv`
   - Caches files (won't re-download if they exist)

2. **Processing**: 
   - Maps NSRDB columns to Chicago format:
     - `air_temperature` → `Temperature`
     - `dew_point` → `Dew Point`
     - `clearsky_ghi` → `Clearsky GHI`
     - `cloud_type` → `Cloud_Type`
   - If cloud type is percentage, converts to discrete categories (0-5)
   - Maps cloud codes to labels using `Metadata_legend.xlsx`

3. **Merging**:
   - Aggregates 30-min load profile to hourly
   - Merges with weather data on `hour_datetime`
   - Saves as `<city>_load_weather_merged.csv`

### Cloud Type Handling

- If NSRDB provides `cloud_type` directly → uses as-is
- If NSRDB provides `cloud_cover` (percentage) → converts to discrete categories:
  - 0-10% = 0 (Clear)
  - 10-25% = 1
  - 25-50% = 2
  - 50-75% = 3
  - 75-90% = 4
  - 90-100% = 5
- Cloud type labels are mapped using `Weather data/Metadata_legend.xlsx`
- If metadata file is missing, uses default NSRDB cloud type mapping

## Dashboard Features

### Controls (Sidebar)

- **City Selection**: Auto-detected from available data files
- **Building Type**: Select from available building columns
- **Z-Threshold**: Threshold for anomaly detection (default: 2.0)
- **Top-N per Year**: Number of top anomalies to display per year (default: 50)

### Outputs

1. **Summary Metrics**:
   - Total hours
   - Anomaly hours
   - Anomaly rate (%)
   - Average |Z-Score|

2. **Top-N Severity Summary**:
   - Aggregated across all buildings
   - Shows average and max |Z-Score| per year
   - Shows average |Residual| per year

3. **Building Drilldown**:
   - Interactive plot showing:
     - Actual vs Predicted load
     - Residuals with anomaly markers
     - Threshold lines
   - Top-N anomalies table with:
     - DateTime, Actual, Predicted, Residual
     - Z-Score, |Z-Score|, |Residual|
     - Cloud_Type (if available)

## Anomaly Detection Method

1. **Baseline Model**: Linear regression for each building
   - Features: Temperature, DewPoint, ClearskyGHI
   - Target: Building load

2. **Residual Analysis**:
   - Compute residuals: `residual = actual - predicted`
   - Compute z-scores: `z = (residual - mean) / std`

3. **Anomaly Flagging**:
   - Anomaly if `|z-score| > threshold`

## Troubleshooting

### Streamlit won't start

- Check that port 8501 is not in use
- Verify Python and dependencies are installed correctly

### Tunnel URL not appearing

- Verify `cloudflared` is installed and in PATH (for Cloudflare)
- Or verify `pyngrok` is installed (for ngrok fallback)
- Check firewall settings

### Data not loading

- Verify CSV files are in the project root
- Check file names match expected patterns
- Ensure datetime columns are parseable

### No anomalies detected

- Check that weather columns (Temperature, DewPoint, ClearskyGHI) exist
- Verify data has sufficient rows (>10)
- Try adjusting Z-threshold

## Project Structure

```
MSA Capstone/
├── app.py                 # Streamlit dashboard
├── run_public.py          # Runner script with tunnel
├── weather_nsrdb.py       # NSRDB API download module
├── build_merge.py         # Load/weather merge module
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── chicago_load_weather_merged.csv
├── Chicago_SimulatedLoadProfile.csv
├── Houston_SimulatedLoadProfile.csv
└── Weather data/
    ├── Metadata_legend.xlsx
    ├── Weather/            # Chicago weather (local)
    │   ├── W1998.csv
    │   ├── W1999.csv
    │   └── ...
    └── Houston/            # Houston weather (NSRDB)
        ├── NSRDB_1998.csv
        ├── NSRDB_1999.csv
        └── ...
```

## Notes

- The dashboard uses Streamlit caching for performance (`@st.cache_data` and `@st.cache_resource`)
- Cloud_Type column (if exists) is displayed but not used in regression
- Column name variations are handled automatically (case-insensitive, space variations)
- The dashboard works immediately for Chicago using `chicago_load_weather_merged.csv`
- Houston and other cities can automatically download weather data via NSRDB API
- Weather downloads are cached - files won't be re-downloaded if they already exist
- City coordinates are configured in `weather_nsrdb.py` (easy to add more cities)

## License

This project is for educational/research purposes.
