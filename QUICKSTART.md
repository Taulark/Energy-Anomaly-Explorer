# Quick Start Guide - React + FastAPI Version

## Prerequisites

- Python 3.8+
- Node.js 18+
- npm or yarn

## Setup Steps

### 1. Backend Setup

```bash
# Install Python dependencies
cd backend
pip install -r requirements.txt

# Set environment variables (optional, for NSRDB weather downloads)
export NSRDB_API_KEY="your_api_key_here"
export NSRDB_EMAIL="your_email@example.com"
```

### 2. Frontend Setup

```bash
# Install Node.js dependencies
cd frontend
npm install
```

### 3. Start Development Servers

**Terminal 1 - Backend:**
```bash
cd backend
python main.py
# Or: uvicorn main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### 4. Access the Application

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Testing with Chicago

1. Open http://localhost:5173
2. Select "Chicago" from the city dropdown
3. Wait for data to load (Chicago uses existing merged file)
4. Select a building (e.g., "SuperMarketPre1980")
5. Click "Run Anomaly Detection"
6. View results in tabs

## Testing with Houston

1. Select "Houston" from the city dropdown
2. The app will automatically:
   - Download load profile from OpenEI (if missing)
   - Download weather data from NSRDB (if missing)
   - Build merged dataset
3. Select a building and run analysis

## Troubleshooting

### Backend Issues

- **Module import errors**: Ensure you're running from the project root, and all Python modules (openei_loader.py, nsrdb_downloader.py, etc.) are in the parent directory
- **NSRDB errors**: Set `NSRDB_API_KEY` and `NSRDB_EMAIL` environment variables
- **Port already in use**: Change port in `backend/main.py` or use `uvicorn main:app --port 8001`

### Frontend Issues

- **npm install fails**: Try `npm install --legacy-peer-deps`
- **Port already in use**: Change port in `frontend/vite.config.ts`
- **API connection errors**: Ensure backend is running on port 8000

## Notes

- Streamlit version (`app.py`) is preserved and still functional
- All Python logic is reused (no TypeScript re-implementation)
- Chicago requires `chicago_load_weather_merged.csv` to exist
- Other cities auto-download weather if coordinates are available
