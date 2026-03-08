# Energy Anomaly Explorer - React + FastAPI Version

This is the React + FastAPI version of the Energy Anomaly Explorer. The Streamlit version (`app.py`) is preserved as a backup.

## Architecture

- **Backend**: FastAPI (Python) - reuses existing Python modules
- **Frontend**: React + TypeScript + Tailwind CSS + Framer Motion
- **Data Processing**: All logic remains in Python (no TypeScript re-implementation)

## Setup

### Backend Setup

1. Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Set environment variables (optional, for NSRDB):
```bash
export NSRDB_API_KEY="your_api_key"
export NSRDB_EMAIL="your_email@example.com"
```

3. Start the backend server:
```bash
cd backend
python main.py
```

Or using uvicorn directly:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### Frontend Setup

1. Install Node.js dependencies:
```bash
cd frontend
npm install
```

2. Start the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Development

### Backend Endpoints

- `GET /api/cities` - Get list of available cities
- `POST /api/prepare-city` - Download and prepare city data (load profile + weather + merge)
- `GET /api/buildings?city=...` - Get building columns for a city
- `POST /api/run` - Run regression and anomaly detection
- `GET /api/health` - Health check

### Frontend Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── HeroHeader.tsx      # Animated hero header (Figma design)
│   │   ├── Sidebar.tsx         # Sidebar with controls
│   │   ├── MainContent.tsx     # Main content area with tabs
│   │   └── tabs/               # Tab components
│   ├── api/
│   │   └── client.ts          # API client
│   ├── App.tsx                 # Main app component
│   └── main.tsx                # Entry point
```

## Features

- ✅ City selection from OpenEI submission 515
- ✅ Automatic load profile download
- ✅ Automatic weather data download (NSRDB)
- ✅ Automatic merge dataset creation
- ✅ Regression feature selection (ElasticNet / Correlation / Fixed)
- ✅ Anomaly detection with z-score
- ✅ Insights & Actions tab
- ✅ Occupancy insights
- ✅ Cost impact estimation
- ✅ Interactive charts (Recharts)
- ✅ Animated hero header (Framer Motion)

## Testing

1. Start backend: `cd backend && python main.py`
2. Start frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173`
4. Select a city (e.g., "Chicago" or "Houston")
5. Wait for data preparation
6. Select a building
7. Click "Run Anomaly Detection"
8. View results in tabs

## Notes

- Chicago requires `chicago_load_weather_merged.csv` to exist (cannot be auto-created)
- Other cities will auto-download weather data if coordinates are available
- All Python logic is reused from existing modules (no re-implementation)
- Streamlit version (`app.py`) remains functional as backup
