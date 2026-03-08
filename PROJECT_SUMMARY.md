# Energy Anomaly Explorer — Frontend & Backend Summary

A simple, step-by-step overview of what’s built: **code** and **process**.

---

## 1. High-Level Architecture

You have **two ways** to use the app:

| Option | What runs | Who uses it |
|--------|-----------|-------------|
| **Streamlit (app.py)** | Single Python app: UI + logic in one process | Direct use in browser via `streamlit run app.py` |
| **React + FastAPI** | React frontend (Vite) talks to FastAPI backend (Python) | Frontend dev server + backend server; good for a separate UI |

Both use the **same core Python logic**: data loading, regression, anomaly detection, and insights.

---

## 2. Backend — What Exists and How It Works

### 2.1 Core Python Modules (Shared by Streamlit and FastAPI)

These live in the **project root** and do the real work.

| Module | Purpose | Main functions / behavior |
|--------|---------|----------------------------|
| **openei_loader** | Cities and load profiles from OpenEI | `fetch_openei_city_resources()` → list of cities + download URLs; `download_load_profile()` → saves `{City}_SimulatedLoadProfile.csv` under `LoadProfiles/` |
| **nsrdb_downloader** | Weather data | `fetch_nsrdb_weather()` uses NSRDB API (needs API key). Uses `CITY_COORDS` or fallback geocoding. Writes weather CSVs per city. |
| **build_merge** | One merged dataset per city | `build_and_save_merged()` aggregates load profile to hourly, merges with weather, saves `{city}_load_weather_merged.csv` (project root or `data/merged/`). |
| **regression_engine** | Feature selection and regression | `get_candidate_weather_features()` → which weather columns can be used; `select_weather_features()` → ElasticNet or correlation Top-K; `fit_regression()` → sklearn fit, R², coefficients, predictions. |
| **insights** | Explain anomalies and suggest actions | `generate_anomaly_explanations()`, `detect_recurring_patterns()`, `generate_executive_summary()`, `estimate_cost_impact()` — all use the merged data and anomaly list. |
| **occupancy_insights** | Occupancy-related insights | `generate_occupancy_insights()` — time-of-day / occupancy patterns. |
| **icons** | UI icons | `svg_icon(name, size, color)` — returns SVG markup for Streamlit. |

**Process (data pipeline):**

1. **Cities** → From OpenEI (submission 515); each city has a display name and a load-profile download URL.
2. **Load profile** → Downloaded from OpenEI if missing (e.g. `LoadProfiles/Chicago_SimulatedLoadProfile.csv`).
3. **Weather** → NSRDB (or Open-Meteo fallback if no NSRDB key). City coordinates from `CITY_COORDS` or geocoding + cache.
4. **Merged file** → `build_merge` produces one hourly CSV per city: load + weather (e.g. Temperature, Dew Point, Clearsky GHI, Wind, Pressure, Cloud_Type).
5. **Regression** → `regression_engine` picks weather features (ElasticNet or correlation Top-K, or fixed 3), fits a model, returns predictions and metrics.
6. **Anomalies** → Residuals (actual − predicted); z-scores; flag hours where |z| > threshold.
7. **Insights** → Explanations, recurrence, summary, cost (and optionally occupancy) from `insights` / `occupancy_insights`.

---

### 2.2 Streamlit App (`app.py`)

**Role:** One script = UI + flow. No separate frontend; Streamlit renders the pages.

**Process (step by step):**

1. **Page config** — Title “Energy Anomaly Explorer”, wide layout, expanded sidebar.
2. **Theme** — Custom dark CSS (gradients, cards, buttons, sidebar, fonts like Inter).
3. **Hero** — `render_figma_style_hero()`: logo (Zap), “ENERGY ANOMALY EXPLORER” with animated letters, subtitle.
4. **City list** — From `get_openei_cities()` (cached). Dropdown shows display names (e.g. “Chicago IL”).
5. **City validation** — `validate_city_files()` checks for load profile and merged CSV.
6. **Auto-download** — If load profile missing → download via OpenEI. If merged missing and NSRDB available → fetch weather and run `build_and_save_merged()`.
7. **Data load** — `load_data(city)`: for Chicago merged-only; for others merged file or build. `standardize_datetime()` parses `hour_datetime` (flexible or SAS format).
8. **Buildings** — `get_building_columns(df)` → numeric columns that are not datetime/weather.
9. **Sidebar** — Status (load profile, merged, coordinates, regression); city; building; **Detection**: Z-threshold, Top-N, year filter; **Regression**: feature mode (Auto ElasticNet, Auto Correlation Top-K, Fixed 3-feature), Top-K, Include Cloud_Type; **Insights**: toggles (insights, recurrence, cost, AI summary); Developer mode.
10. **Run detection** — Button “Run Anomaly Detection”. For each building, `detect_anomalies()`:
    - Uses cached regression if same building/year/feature mode; else runs `regression_engine` (feature selection + fit).
    - Builds residuals and z-scores; flags anomalies.
    - Stores result per building in `st.session_state['all_anomalies']`.
11. **Main area after run** — KPIs (total hours, anomaly hours, anomaly rate, avg |z|); **tabs**:
    - **Overview** — High-level metrics and summary.
    - **Insights & Actions** — From `insights` (explanations, recurrence, executive summary, cost).
    - **Regression** — Selected features, R², coefficients, diagnostics.
    - **Drilldown** — Time-series / detailed view of load vs predicted and anomalies.
    - **Top Anomalies** — Table of top-N anomalies (e.g. by |z| or residual).

**Code touchpoints:**  
`load_data`, `detect_anomalies`, `resolve_feature_columns`, `standardize_datetime`, `get_building_columns`, `fit_model`, and all `section_header` / `sidebar_section_header` / `metric-card` / tab content.

---

### 2.3 FastAPI Backend (`backend/main.py`)

**Role:** REST API so the React app can run the same pipeline without Streamlit.

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/cities` | List of city display names (from OpenEI). |
| POST | `/api/prepare-city` | Body: `{ "city": "Chicago IL" }`. Ensures merged file exists (download + merge in background if needed). Returns `{ status, message, ready }`. |
| GET | `/api/buildings?city=...` | List of building column names for that city (after data is ready). |
| GET | `/api/years?city=...&building=...` | List of years present in the data for that city/building. |
| POST | `/api/run` | Run full analysis (see below). |
| GET | `/api/health` | Health check. |

**Prepare-city process:**  
`ensure_city_prepared(city_display)` (or equivalent): get canonical city key from OpenEI → if merged CSV missing, download load profile, get coordinates (CITY_COORDS or geocode + cache), fetch weather (NSRDB or Open-Meteo), run `build_and_save_merged()`. Returns path and optional `weather_source_used`.

**Run-analysis process (`POST /api/run`):**

1. **Body** — City, building, z_threshold, top_n, selected_year, feature_mode (ElasticNet / Correlation Top-K / Fixed 3-feature), top_k, include_cloud_type, electricity_rate, and insight flags (enable_insights, enable_recurrence, enable_cost_estimates, enable_ai_summary).
2. **Load** — Call same “load merged data” logic (with auto-prepare if needed). Apply year filter if `selected_year != "All"`. Reset index.
3. **Feature selection** — Fixed 3-feature: resolve Temperature, Dew Point, Clearsky GHI. Auto: `get_candidate_weather_features()` then `select_weather_features()` (elasticnet or correlation, top_k, include_cloud_type).
4. **Regression** — `fit_regression(df, building, selected_features)` → metrics (R², RMSE, MAE), coefficients, predictions.
5. **Anomaly detection** — Residuals = actual − predicted; z-scores; flag |z| > z_threshold; compute summary (total hours, anomaly hours, rate, avg |z|).
6. **Top anomalies** — Sort by |z| (or residual), take top_n (e.g. per year if applicable).
7. **Insights** — If flags set: anomaly explanations, recurring patterns, executive summary, cost estimate (and optionally occupancy).
8. **Response** — JSON: `anomaly_summary`, `top_anomalies`, `regression` (features, metrics, coef_table, confidence), `insights`, `occupancy`, `cost`, plus any `weather_source_used`, `z_threshold_used`, `top_n_used`, `year_filter_used`.

**Code:** All of this lives in `backend/main.py` and reuses the root-level modules (`openei_loader`, `nsrdb_downloader`, `build_merge`, `regression_engine`, `insights`, `occupancy_insights`). Helpers include `get_canonical_city_key()`, `normalize_city_name_for_matching()`, `get_building_columns()`, `robust_parse_datetime()`, `resolve_city_coordinates()`, `ensure_city_prepared()`, and the `load_merged_data()` used in run.

---

## 3. Frontend — What Exists and How It Works

**Stack:** React, TypeScript, Vite, TanStack Query (React Query), Axios, Tailwind CSS, Framer Motion, Lucide icons.

### 3.1 Entry and Layout

- **`main.tsx`** — Renders `<App />` inside root.
- **`App.tsx`** — Holds all shared state (city, building, z-threshold, top-N, year, feature mode, top-K, cloud type, electricity rate, insight toggles, results, isRunning, isPreparing, runError). Wraps with `QueryClientProvider`. Layout: sidebar + main area; main area has `HeroHeader` and `MainContent`; shows `runError` if present.
- **`api/client.ts`** — Axios instance with `baseURL` from `VITE_API_URL` or `http://localhost:8000`. Exposes: `getCities()`, `prepareCity(city)`, `getBuildings(city)`, `getYears(city, building)`, `runAnalysis(request)`, `health()`.

**Process (user flow):**

1. App loads → `getCities()` populates city dropdown.
2. User selects city → `onPrepareCity(city)` (e.g. `prepareCity(selectedCity)`) runs; when `ready`, `setSelectedCity(city)`.
3. When city is set, React Query fetches `getBuildings(selectedCity)` and `getYears(selectedCity, selectedBuilding)` when building is set.
4. User selects building and options (z-threshold, top-N, year, feature mode, etc.), then clicks Run → `handleRun()` builds the request and calls `api.runAnalysis(request)`; on success `setResults(result)`, on failure `setRunError(msg)`.
5. `MainContent` receives `results` and `isRunning` and renders tabs accordingly.

---

### 3.2 Components

| Component | Purpose |
|-----------|---------|
| **HeroHeader** | Animated hero: Zap icon, “ENERGY ANOMALY EXPLORER” (Framer Motion on E, R, A, O, Y, X, E), subtitle. Matches Streamlit hero idea in React. |
| **Sidebar** | City dropdown (from `getCities`); building dropdown (from `getBuildings(city)`); year (from `getYears`); sliders/inputs for Z-threshold, Top-N, Top-K; feature mode radio; Include Cloud_Type; electricity rate; insight toggles (insights, recurrence, cost, AI summary); status indicators; “Prepare city” / “Run analysis” behavior; fixed width (e.g. `ml-64` for main). |
| **MainContent** | Tab bar (Overview, Insights & Actions, Drilldown, Top Anomalies, Regression). When no results: “Select city and building, then run…”. When running: “Running analysis…”. When results: renders the active tab component with `results`. |

---

### 3.3 Tab Components (under `src/components/tabs/`)

| Tab | Role |
|-----|------|
| **OverviewTab** | Key metrics from `results.anomaly_summary` (total hours, anomaly hours, anomaly rate, avg |z|). Can show top-N summary by year from `results.top_anomalies`. Uses same run params (z_threshold_used, top_n_used, year_filter_used) for context. |
| **InsightsTab** | Uses `results.insights`: anomaly explanations, recurring patterns, executive summary; optionally `results.cost` for cost impact. Renders in cards/sections. |
| **DrilldownTab** | Deeper view of the time series / distribution: e.g. load vs predicted, anomaly points. Data from `results` (e.g. top_anomalies, regression predictions if exposed). |
| **TopAnomaliesTab** | Table of top anomalies: datetime, residual, z-score, actual vs predicted, etc., from `results.top_anomalies`. |
| **RegressionTab** | Shows `results.regression`: selected features, method, R²/confidence, coefficient table, any regression warning or diagnostics. |

All tabs are present in `MainContent`; they only render when `results` exists and `!isRunning`.

---

### 3.4 API Contract (Frontend ↔ Backend)

- **Cities:** `GET /api/cities` → `{ cities: string[] }`.
- **Prepare:** `POST /api/prepare-city` → `{ status, message, ready }`.
- **Buildings:** `GET /api/buildings?city=...` → `{ buildings: string[] }`.
- **Years:** `GET /api/years?city=...&building=...` → `{ years: number[] }`.
- **Run:** `POST /api/run` with body (city, building, z_threshold, top_n, selected_year, feature_mode, top_k, include_cloud_type, electricity_rate, enable_insights, enable_recurrence, enable_cost_estimates, enable_ai_summary) → full result object (anomaly_summary, top_anomalies, regression, insights, occupancy, cost, …).

The frontend does not implement the regression or anomaly math; it only sends parameters and displays the JSON returned by the backend.

---

## 4. End-to-End Process (React + FastAPI)

1. User opens React app (e.g. `http://localhost:5173`). Backend runs at `http://localhost:8000`.
2. **Cities** — Frontend calls `GET /api/cities`; user picks a city.
3. **Prepare** — Frontend calls `POST /api/prepare-city` with that city. Backend ensures merged file exists (OpenEI + weather + merge if needed).
4. **Buildings & years** — Frontend calls `GET /api/buildings` and `GET /api/years`; user selects building and optionally year.
5. **Parameters** — User sets Z-threshold, Top-N, feature mode (and Top-K, Cloud_Type, insight toggles, rate) in the sidebar.
6. **Run** — User clicks Run; frontend sends `POST /api/run` with all parameters.
7. **Backend** — Loads merged data (with year filter), selects features, fits regression, computes residuals and z-scores, finds top anomalies, runs insight modules, returns one JSON payload.
8. **Frontend** — Saves result in state; MainContent shows Overview, Insights, Drilldown, Top Anomalies, and Regression tabs from that payload.

---

## 5. Streamlit vs React+FastAPI (Same Logic, Two UIs)

| Aspect | Streamlit (app.py) | React + FastAPI |
|--------|--------------------|-----------------|
| **UI** | Streamlit widgets and markdown/HTML | React components, Tailwind, Framer Motion |
| **Data/regression/insights** | Same Python modules in same repo | Same Python modules; FastAPI imports them and exposes HTTP API |
| **City/building/data prep** | In-process: OpenEI, NSRDB/build_merge, load_data | Same logic in backend; prepare-city and run endpoints |
| **Run flow** | One process; button triggers `detect_anomalies()` and then tab content | Frontend calls `/api/run`; backend runs same pipeline and returns JSON |
| **Deployment** | Single `streamlit run app.py` | Serve backend (e.g. uvicorn) and frontend (e.g. static build or Vite dev server) |

---

## 6. File Map (Quick Reference)

- **Root:** `app.py` (Streamlit), `openei_loader.py`, `nsrdb_downloader.py`, `build_merge.py`, `regression_engine.py`, `insights.py`, `occupancy_insights.py`, `icons.py`, merged CSVs, load profiles (or `LoadProfiles/`), weather data/cache.
- **Backend:** `backend/main.py`, `backend/requirements.txt`, `backend/start.sh`.
- **Frontend:** `frontend/src/App.tsx`, `main.tsx`, `api/client.ts`, `components/HeroHeader.tsx`, `Sidebar.tsx`, `MainContent.tsx`, `components/tabs/*.tsx`, `index.css`, Tailwind/Vite config.

This document is the single place that describes both **what’s built** (code) and **how it runs** (process) for frontend and backend.
