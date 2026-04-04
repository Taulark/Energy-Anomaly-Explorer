import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { Activity, Building2, Target, Settings, Lightbulb, TrendingUp, CheckCircle2, Clock, AlertCircle, Upload, MapPin, FileSpreadsheet } from 'lucide-react';

type DataMode = 'sample' | 'upload';

interface SidebarProps {
  selectedCity: string;
  setSelectedCity: (city: string) => void;
  selectedBuilding: string;
  setSelectedBuilding: (building: string) => void;
  zThreshold: number;
  setZThreshold: (value: number) => void;
  topN: number;
  setTopN: (value: number) => void;
  selectedYear: string;
  setSelectedYear: (value: string) => void;
  featureMode: string;
  setFeatureMode: (value: string) => void;
  topK: number;
  setTopK: (value: number) => void;
  includeCloudType: boolean;
  setIncludeCloudType: (value: boolean) => void;
  electricityRate: number;
  setElectricityRate: (value: number) => void;
  enableInsights: boolean;
  setEnableInsights: (value: boolean) => void;
  enableRecurrence: boolean;
  setEnableRecurrence: (value: boolean) => void;
  enableCostEstimates: boolean;
  setEnableCostEstimates: (value: boolean) => void;
  onPrepareCity: (city: string) => Promise<any>;
  onRun: () => Promise<void>;
  onUploadRun: (params: {
    file: File;
    locationName: string;
    latitude: number;
    longitude: number;
    timestampColumn: string;
    energyColumn: string;
    buildingName: string;
  }) => Promise<void>;
  isRunning: boolean;
  isPreparing: boolean;
  results: any;
}

export default function Sidebar({
  selectedCity,
  setSelectedCity,
  selectedBuilding,
  setSelectedBuilding,
  zThreshold,
  setZThreshold,
  topN,
  setTopN,
  selectedYear,
  setSelectedYear,
  featureMode,
  setFeatureMode,
  topK,
  setTopK,
  includeCloudType,
  setIncludeCloudType,
  electricityRate,
  setElectricityRate,
  enableInsights,
  setEnableInsights,
  enableRecurrence,
  setEnableRecurrence,
  enableCostEstimates,
  setEnableCostEstimates,
  onPrepareCity,
  onRun,
  onUploadRun,
  isRunning,
  isPreparing,
  results,
}: SidebarProps) {
  const [dataMode, setDataMode] = useState<DataMode>('sample');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [locationName, setLocationName] = useState('');
  const [latitude, setLatitude] = useState(0);
  const [longitude, setLongitude] = useState(0);
  const [useLatLon, setUseLatLon] = useState(false);
  const [timestampCol, setTimestampCol] = useState('');
  const [energyCol, setEnergyCol] = useState('');
  const [buildingName, setBuildingName] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) setUploadFile(file);
  }, []);

  const handleUploadRun = async () => {
    if (!uploadFile) return;
    if (!useLatLon && !locationName.trim()) return;
    if (useLatLon && latitude === 0 && longitude === 0) return;
    await onUploadRun({
      file: uploadFile,
      locationName: useLatLon ? '' : locationName,
      latitude: useLatLon ? latitude : 0,
      longitude: useLatLon ? longitude : 0,
      timestampColumn: timestampCol,
      energyColumn: energyCol,
      buildingName: buildingName,
    });
  };
  const { data: cities = [] } = useQuery({
    queryKey: ['cities'],
    queryFn: api.getCities,
    staleTime: 1000 * 60 * 60 * 24,
  });

  const { data: buildings = [], isLoading: buildingsLoading, error: buildingsError } = useQuery<string[]>({
    queryKey: ['buildings', selectedCity],
    queryFn: () => {
      console.log(`[Frontend] Fetching buildings for city: "${selectedCity}"`);
      return api.getBuildings(selectedCity);
    },
    enabled: !!selectedCity,
    staleTime: 1000 * 60 * 30,
    retry: 1,
    retryDelay: 2000,
  });

  const { data: years = [], isLoading: yearsLoading, error: yearsError } = useQuery({
    queryKey: ['years', selectedCity, selectedBuilding],
    queryFn: () => api.getYears(selectedCity, selectedBuilding),
    enabled: !!selectedCity && !!selectedBuilding && !isPreparing,
    retry: 1,
    retryDelay: 2000,
  });

  const nsrdbCredsError =
    (buildingsError as any)?.response?.data?.detail?.error === 'missing_nsrdb_credentials' ||
    (yearsError as any)?.response?.data?.detail?.error === 'missing_nsrdb_credentials';

  const weatherSourceUsed = (results as any)?.weather_source_used as string | undefined;
  const usingFallbackWeather =
    weatherSourceUsed === 'OPEN_METEO' || weatherSourceUsed === 'CACHE';

  const [statusItems, setStatusItems] = useState<Array<{ label: string; status: string; type: 'success' | 'warning' | 'error' }>>([]);

  useEffect(() => {
    const items: Array<{ label: string; status: string; type: 'success' | 'warning' | 'error' }> = [];
    if (selectedCity) {
      items.push({ label: 'Load Profile', status: 'Available', type: 'success' });
      items.push({ label: 'Merged Dataset', status: 'Ready', type: 'success' });
      items.push({ label: 'Coordinates', status: 'Configured', type: 'success' });
      
      // BUG FIX: Only show regression status if:
      // 1. Regression is actually running (isRunning), OR
      // 2. Regression results exist (results?.regression)
      // Do NOT show "Pending" just because city is selected - that's misleading!
      // Regression should only appear in status when it's actively running or has completed.
      if (isRunning) {
        items.push({ label: 'Regression Features', status: 'Running...', type: 'warning' });
      } else if (results?.regression) {
        items.push({ label: 'Regression Features', status: 'Ready', type: 'success' });
      }
      // If neither condition is true, don't show regression status at all
    }
    setStatusItems(items);
  }, [selectedCity, results, isRunning]);

  const handleCityChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const city = e.target.value;
    
    if (!city) {
      // If empty, just reset everything
      setSelectedCity('');
      setSelectedBuilding('');
      setSelectedYear('All');
      return;
    }
    
    // Set city immediately (controlled component)
    setSelectedCity(city);
    // Reset dependent selections
    setSelectedBuilding('');
    setSelectedYear('All');
    
    // Automatically prepare city (download + merge if needed)
    try {
      await onPrepareCity(city);
      // Status will be "already_prepared" or "prepared" if successful
      // Buildings will be fetched automatically via React Query when city is set
    } catch (error) {
      // Error handling - city remains selected, user can retry
      console.error('Error preparing city:', error);
    }
  };

  const handleBuildingChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const building = e.target.value;
    setSelectedBuilding(building);
    // Reset year when building changes
    setSelectedYear('All');
  };

  const handleYearChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const year = e.target.value;
    setSelectedYear(year);
  };

  return (
    <div className="w-64 bg-[#1e1e2e] border-r border-[#2d2d44] h-screen overflow-y-auto fixed left-0 top-0 p-4">
      {/* Status */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
          <Activity className="w-4 h-4" />
          <span>Status</span>
        </div>
        {statusItems.length > 0 && (
          <div className="bg-[rgba(30,30,46,0.5)] rounded-lg p-2.5 border border-[#2d2d44]">
            <div className="space-y-1.5">
              {statusItems.map((item, idx) => {
                const IconComponent =
                  item.type === 'success' ? CheckCircle2 :
                  item.type === 'warning' ? Clock :
                  AlertCircle;
                const statusColor =
                  item.type === 'success' ? 'text-green-400' :
                  item.type === 'warning' ? 'text-yellow-400' :
                  'text-red-400';

                return (
                  <div key={idx} className="flex items-center gap-2">
                    <IconComponent size={14} className={`${statusColor} flex-shrink-0`} />
                    <span className="text-xs text-gray-400 truncate">{item.label}</span>
                    <span className={`text-xs font-medium ${statusColor} ml-auto flex-shrink-0`}>
                      {item.status}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Data Source Toggle */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
          <FileSpreadsheet className="w-4 h-4" />
          <span>Data Source</span>
        </div>
        <div className="flex rounded-lg overflow-hidden border border-[#2d2d44]">
          <button
            onClick={() => setDataMode('sample')}
            className={`flex-1 py-1.5 text-xs font-medium transition-colors ${
              dataMode === 'sample'
                ? 'bg-indigo-600 text-white'
                : 'bg-[#1e1e2e] text-gray-400 hover:text-gray-200'
            }`}
          >
            Sample Data
          </button>
          <button
            onClick={() => setDataMode('upload')}
            className={`flex-1 py-1.5 text-xs font-medium transition-colors ${
              dataMode === 'upload'
                ? 'bg-indigo-600 text-white'
                : 'bg-[#1e1e2e] text-gray-400 hover:text-gray-200'
            }`}
          >
            Upload Data
          </button>
        </div>
      </div>

      {dataMode === 'upload' ? (
        <>
          {/* Upload Panel */}
          <div className="mb-6">
            <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
              <Upload className="w-4 h-4" />
              <span>Upload File</span>
            </div>

            <div className="mb-3 p-2.5 bg-indigo-900/20 border border-indigo-600/30 rounded-lg text-xs text-indigo-200 space-y-1.5">
              <p className="font-medium">Upload a CSV or Excel file with:</p>
              <ul className="list-disc pl-4 space-y-0.5 text-indigo-300">
                <li>A <strong>timestamp</strong> column with hourly readings</li>
                <li>A numeric <strong>energy consumption</strong> column (kWh)</li>
                <li>At least ~1 month of data (720+ rows)</li>
              </ul>
              <p className="text-indigo-400 mt-1.5">Sub-hourly data (15-min, 30-min) is automatically aggregated to hourly. Columns are auto-detected or you can specify them below.</p>
            </div>

            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
                uploadFile
                  ? 'border-green-500/50 bg-green-900/10'
                  : 'border-[#2d2d44] hover:border-indigo-500/50 hover:bg-indigo-900/10'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) setUploadFile(f);
                }}
              />
              {uploadFile ? (
                <div>
                  <FileSpreadsheet size={20} className="mx-auto text-green-400 mb-1" />
                  <p className="text-xs text-green-400 font-medium truncate">{uploadFile.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{(uploadFile.size / 1024).toFixed(0)} KB</p>
                </div>
              ) : (
                <div>
                  <Upload size={20} className="mx-auto text-gray-500 mb-1" />
                  <p className="text-xs text-gray-400">Drop CSV/Excel here</p>
                  <p className="text-xs text-gray-600">or click to browse</p>
                </div>
              )}
            </div>

            {/* Column mapping (optional) */}
            <div className="mt-3 space-y-2">
              <div>
                <label className="block text-xs text-gray-500 mb-0.5">Timestamp column (auto-detect if blank)</label>
                <input
                  type="text"
                  value={timestampCol}
                  onChange={(e) => setTimestampCol(e.target.value)}
                  placeholder="e.g. timestamp, datetime"
                  className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded px-2 py-1.5 text-xs text-white placeholder-gray-600"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-0.5">Energy column (auto-detect if blank)</label>
                <input
                  type="text"
                  value={energyCol}
                  onChange={(e) => setEnergyCol(e.target.value)}
                  placeholder="e.g. energy_kwh, consumption"
                  className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded px-2 py-1.5 text-xs text-white placeholder-gray-600"
                />
              </div>
            </div>
          </div>

          {/* Location */}
          <div className="mb-6">
            <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
              <MapPin className="w-4 h-4" />
              <span>Building Location</span>
            </div>
            <label className="flex items-center gap-2 text-xs text-gray-400 mb-2 cursor-pointer">
              <input
                type="checkbox"
                checked={useLatLon}
                onChange={(e) => setUseLatLon(e.target.checked)}
                className="rounded"
              />
              Use Latitude / Longitude
            </label>
            {useLatLon ? (
              <div className="space-y-2">
                <input
                  type="number" step="0.0001"
                  value={latitude || ''}
                  onChange={(e) => setLatitude(parseFloat(e.target.value) || 0)}
                  placeholder="Latitude (e.g. 29.7604)"
                  className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded px-2 py-1.5 text-xs text-white placeholder-gray-600"
                />
                <input
                  type="number" step="0.0001"
                  value={longitude || ''}
                  onChange={(e) => setLongitude(parseFloat(e.target.value) || 0)}
                  placeholder="Longitude (e.g. -95.3698)"
                  className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded px-2 py-1.5 text-xs text-white placeholder-gray-600"
                />
              </div>
            ) : (
              <input
                type="text"
                value={locationName}
                onChange={(e) => setLocationName(e.target.value)}
                placeholder="e.g. Houston TX, New York NY"
                className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            )}
          </div>

          {/* Building Name / Type (optional) */}
          <div className="mb-6">
            <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
              <Building2 className="w-4 h-4" />
              <span>Building Info <span className="text-gray-500 font-normal">(optional)</span></span>
            </div>
            <input
              type="text"
              value={buildingName}
              onChange={(e) => setBuildingName(e.target.value)}
              placeholder="e.g. Main Office, Warehouse B"
              className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-600 mt-1">Shown in results as a label for your building.</p>
          </div>
        </>
      ) : (
        <>
          {usingFallbackWeather && (
            <div className="mb-6 p-3 bg-sky-900/30 border border-sky-600/50 rounded-lg text-sky-200 text-xs" role="status">
              Using fallback weather source (Open-Meteo). For NSRDB clearsky/GHI, set NSRDB env vars.
            </div>
          )}
          {nsrdbCredsError && !usingFallbackWeather && (
            <div className="mb-6 p-3 bg-amber-900/30 border border-amber-600/50 rounded-lg text-amber-200 text-xs" role="alert">
              Weather download requires NSRDB credentials. Set NSRDB_API_KEY and NSRDB_EMAIL and retry.
            </div>
          )}

          {/* City Selection */}
          <div className="mb-6">
            <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
              <Building2 className="w-4 h-4" />
              <span>City Selection</span>
            </div>
            <select
              value={selectedCity}
              onChange={handleCityChange}
              disabled={isPreparing}
              className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Select City</option>
              {cities.map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
            </select>
            {isPreparing && selectedCity && (
              <div className="mt-2 text-xs text-yellow-500">Preparing city data...</div>
            )}
          </div>

          {/* Building Selection */}
          {selectedCity && (
            <div className="mb-6">
              <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
                <Target className="w-4 h-4" />
                <span>Building Selection</span>
              </div>
              <select
                value={selectedBuilding}
                onChange={handleBuildingChange}
                disabled={isRunning || buildingsLoading || isPreparing}
                className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">
                  {isPreparing ? 'Preparing city data...' : buildingsLoading ? 'Loading buildings...' : 'Select Building'}
                </option>
                {buildings.map((building) => (
                  <option key={building} value={building}>
                    {building}
                  </option>
                ))}
              </select>
              {buildingsError && (
                <div className="mt-2 text-xs text-red-400">
                  Error loading buildings: {(buildingsError as any)?.response?.data?.detail?.message || buildingsError?.message || 'Unknown error'}
                </div>
              )}
              {!buildingsError && !buildingsLoading && !isPreparing && buildings.length === 0 && selectedCity && (
                <div className="mt-2 text-xs text-yellow-500">
                  No buildings found for {selectedCity}. Check backend logs.
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Detection Parameters */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
          <Target className="w-4 h-4" />
          <span>Detection Parameters</span>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Z-Threshold</label>
            <input
              type="range"
              min="1.0"
              max="5.0"
              step="0.1"
              value={zThreshold}
              onChange={(e) => setZThreshold(parseFloat(e.target.value))}
              disabled={isRunning}
              className="w-full"
            />
            <div className="text-xs text-gray-500 mt-1">{zThreshold.toFixed(1)}</div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Top-N per Year</label>
            <input
              type="number"
              min="1"
              max="500"
              value={topN}
              onChange={(e) => setTopN(parseInt(e.target.value))}
              disabled={isRunning}
              className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Filter Year</label>
            <select
              value={selectedYear}
              onChange={handleYearChange}
              disabled={isRunning || !selectedBuilding || yearsLoading || isPreparing}
              className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="All">All</option>
              {years.map((year) => (
                <option key={year} value={year.toString()}>
                  {year}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Regression Model */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
          <Settings className="w-4 h-4" />
          <span>Regression Model</span>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Feature Mode</label>
            <select
              value={featureMode}
              onChange={(e) => setFeatureMode(e.target.value)}
              disabled={isRunning}
              className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="Auto-select (ElasticNet)">Auto-select (ElasticNet)</option>
              <option value="Auto-select (Correlation Top-K)">Auto-select (Correlation Top-K)</option>
              <option value="Fixed 3-feature">Fixed 3-feature</option>
            </select>
          </div>
          {featureMode.includes('Top-K') && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Top-K Features</label>
              <input
                type="number"
                min="1"
                max="10"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                disabled={isRunning}
                className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white"
              />
            </div>
          )}
          <label className="flex items-center gap-2 text-xs text-gray-300">
            <input
              type="checkbox"
              checked={includeCloudType}
              onChange={(e) => setIncludeCloudType(e.target.checked)}
              disabled={isRunning}
              className="rounded"
            />
            Include Cloud Type feature
          </label>
        </div>
      </div>

      {/* Insights & Actions */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
          <Lightbulb className="w-4 h-4" />
          <span>Insights & Actions</span>
        </div>
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-xs text-gray-300">
            <input
              type="checkbox"
              checked={enableInsights}
              onChange={(e) => setEnableInsights(e.target.checked)}
              disabled={isRunning}
              className="rounded"
            />
            Enable Insights & Actions
          </label>
          {enableInsights && (
            <>
              <label className="flex items-center gap-2 text-xs text-gray-300">
                <input
                  type="checkbox"
                  checked={enableRecurrence}
                  onChange={(e) => setEnableRecurrence(e.target.checked)}
                  disabled={isRunning}
                  className="rounded"
                />
                Enable Recurrence Analysis
              </label>
              <label className="flex items-center gap-2 text-xs text-gray-300">
                <input
                  type="checkbox"
                  checked={enableCostEstimates}
                  onChange={(e) => setEnableCostEstimates(e.target.checked)}
                  disabled={isRunning}
                  className="rounded"
                />
                Enable Cost Estimates
              </label>
              {enableCostEstimates && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Electricity Rate ($/kWh)</label>
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={electricityRate}
                    onChange={(e) => setElectricityRate(parseFloat(e.target.value))}
                    disabled={isRunning}
                    className="w-full bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-2 text-sm text-white"
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Run Button */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[#B6C2E2] text-sm font-semibold mb-2 pb-2 border-b border-[#2d2d44]">
          <TrendingUp className="w-4 h-4" />
          <span>Run Detection</span>
        </div>
        {dataMode === 'upload' ? (
          <button
            onClick={handleUploadRun}
            disabled={!uploadFile || (!useLatLon && !locationName.trim()) || (useLatLon && latitude === 0 && longitude === 0) || isRunning}
            className="w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2 px-4 rounded-lg transition-all"
          >
            {isRunning ? 'Analyzing...' : 'Upload & Analyze'}
          </button>
        ) : (
          <button
            onClick={onRun}
            disabled={!selectedCity || !selectedBuilding || isRunning}
            className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2 px-4 rounded-lg transition-all"
          >
            {isRunning ? 'Running...' : 'Run Anomaly Detection'}
          </button>
        )}
        {isRunning && dataMode === 'upload' && (
          <p className="text-xs text-gray-500 mt-2 text-center">Fetching weather data and running analysis...</p>
        )}
      </div>
    </div>
  );
}
