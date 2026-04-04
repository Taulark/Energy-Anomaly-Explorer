import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import HeroHeader from './components/HeroHeader';
import Sidebar from './components/Sidebar';
import MainContent from './components/MainContent';
import MobileTopBar from './components/MobileTopBar';
import { api } from './api/client';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function App() {
  const [selectedCity, setSelectedCity] = useState<string>('');
  const [selectedBuilding, setSelectedBuilding] = useState<string>('');
  const [zThreshold, setZThreshold] = useState<number>(2.0);
  const [topN, setTopN] = useState<number>(50);
  const [selectedYear, setSelectedYear] = useState<string>('All');
  const [featureMode, setFeatureMode] = useState<string>('Auto-select (ElasticNet)');
  const [topK, setTopK] = useState<number>(3);
  const [includeCloudType, setIncludeCloudType] = useState<boolean>(false);
  const [electricityRate, setElectricityRate] = useState<number>(0.12);
  // Insight flags
  const [enableInsights, setEnableInsights] = useState<boolean>(true);
  const [enableRecurrence, setEnableRecurrence] = useState<boolean>(true);
  const [enableCostEstimates, setEnableCostEstimates] = useState<boolean>(false);
  const [results, setResults] = useState<any>(null);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [isPreparing, setIsPreparing] = useState<boolean>(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const onChange = () => {
      if (mq.matches) setMobileMenuOpen(false);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const handlePrepareCity = async (city: string) => {
    setIsPreparing(true);
    try {
      const status = await api.ensureLoadProfile(city);
      return status;
    } finally {
      setIsPreparing(false);
    }
  };

  const extractErrorMessage = (error: any): string => {
    const d = error?.response?.data?.detail;
    if (typeof d === 'object' && d !== null && 'message' in d) return (d as { message?: string }).message || 'Error';
    if (typeof d === 'string') return d;
    if (d != null) return JSON.stringify(d, null, 2);
    return error?.message || 'Error running analysis';
  };

  const handleRun = async () => {
    if (!selectedCity || !selectedBuilding) return;
    
    setIsRunning(true);
    try {
      const requestPayload = {
        city: selectedCity,
        building: selectedBuilding,
        z_threshold: zThreshold,
        top_n: topN,
        selected_year: selectedYear,
        feature_mode: featureMode,
        top_k: topK,
        include_cloud_type: includeCloudType,
        enable_cost_estimate: false,
        electricity_rate: electricityRate,
        enable_insights: enableInsights,
        enable_recurrence: enableRecurrence,
        enable_cost_estimates: enableCostEstimates,
        enable_ai_summary: false,
      };
      console.log('Run analysis request:', requestPayload);
      const result = await api.runAnalysis(requestPayload);
      result.city = selectedCity;
      result.building = selectedBuilding;
      setResults(result);
      setRunError(null);
    } catch (error: any) {
      console.error('Run analysis error:', error);
      setRunError(extractErrorMessage(error));
    } finally {
      setIsRunning(false);
    }
  };

  const handleUploadRun = async (params: {
    file: File;
    locationName: string;
    latitude: number;
    longitude: number;
    timestampColumn: string;
    energyColumn: string;
    buildingName: string;
  }) => {
    setIsRunning(true);
    setRunError(null);
    try {
      const result = await api.uploadAndAnalyze({
        file: params.file,
        locationName: params.locationName,
        latitude: params.latitude,
        longitude: params.longitude,
        timestampColumn: params.timestampColumn,
        energyColumn: params.energyColumn,
        buildingName: params.buildingName,
        zThreshold,
        topN,
        featureMode,
        topK,
        includeCloudType,
        electricityRate,
        enableInsights,
        enableRecurrence,
        enableCostEstimates,
      });
      setResults(result);
      setRunError(null);
    } catch (error: any) {
      console.error('Upload analysis error:', error);
      setRunError(extractErrorMessage(error));
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex min-h-[100dvh] flex-col bg-gradient-to-br from-[#0f0f23] to-[#1a1a2e] md:flex-row">
        <Sidebar
          selectedCity={selectedCity}
          setSelectedCity={setSelectedCity}
          selectedBuilding={selectedBuilding}
          setSelectedBuilding={setSelectedBuilding}
          zThreshold={zThreshold}
          setZThreshold={setZThreshold}
          topN={topN}
          setTopN={setTopN}
          selectedYear={selectedYear}
          setSelectedYear={setSelectedYear}
          featureMode={featureMode}
          setFeatureMode={setFeatureMode}
          topK={topK}
          setTopK={setTopK}
          includeCloudType={includeCloudType}
          setIncludeCloudType={setIncludeCloudType}
          electricityRate={electricityRate}
          setElectricityRate={setElectricityRate}
          enableInsights={enableInsights}
          setEnableInsights={setEnableInsights}
          enableRecurrence={enableRecurrence}
          setEnableRecurrence={setEnableRecurrence}
          enableCostEstimates={enableCostEstimates}
          setEnableCostEstimates={setEnableCostEstimates}
          onPrepareCity={handlePrepareCity}
          onRun={handleRun}
          onUploadRun={handleUploadRun}
          isRunning={isRunning}
          isPreparing={isPreparing}
          results={results}
          mobileDrawerOpen={mobileMenuOpen}
          onCloseMobileDrawer={() => setMobileMenuOpen(false)}
        />
        <div className="flex min-w-0 flex-1 flex-col pb-[env(safe-area-inset-bottom)]">
          <MobileTopBar
            onOpenMenu={() => setMobileMenuOpen(true)}
            onScrollTop={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          />
          <p className="border-b border-[#2d2d44]/50 px-4 py-2 text-center text-[11px] leading-snug text-slate-500 md:hidden">
            Advanced anomaly detection for building energy load profiles
          </p>
          <HeroHeader />
          {runError && (
            <div className="mx-4 mt-4 rounded-lg border border-amber-600/50 bg-amber-900/30 p-4 text-sm text-amber-200 whitespace-pre-wrap md:mx-6" role="alert">
              {runError}
            </div>
          )}
          <MainContent results={results} isRunning={isRunning} />
        </div>
      </div>
    </QueryClientProvider>
  );
}

export default App;
