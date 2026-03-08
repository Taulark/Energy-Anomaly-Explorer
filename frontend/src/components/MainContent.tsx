import { useState } from 'react';
import OverviewTab from './tabs/OverviewTab';
import InsightsTab from './tabs/InsightsTab';
import DrilldownTab from './tabs/DrilldownTab';
import TopAnomaliesTab from './tabs/TopAnomaliesTab';
import RegressionTab from './tabs/RegressionTab';
import ForecastTab from './tabs/ForecastTab';

interface MainContentProps {
  results: any;
  isRunning: boolean;
}

export default function MainContent({ results, isRunning }: MainContentProps) {
  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'insights', label: 'Insights & Actions' },
    { id: 'drilldown', label: 'Drilldown' },
    { id: 'top-anomalies', label: 'Top Anomalies' },
    { id: 'regression', label: 'Regression' },
    { id: 'forecast', label: '⚡ Forecast' },
  ];

  return (
    <div className="p-6">
      {/* Tabs */}
      <div className="flex gap-2 border-b border-[#2d2d44] mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-white border-b-2 border-blue-500'
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div>
        {isRunning && (
          <div className="text-center py-12 text-gray-400">
            Running analysis...
          </div>
        )}
        {!isRunning && !results && (
          <div className="text-center py-12 text-gray-400">
            Select a city and building, then run anomaly detection to see results.
          </div>
        )}
        {!isRunning && results && (
          <>
            {activeTab === 'overview' && <OverviewTab results={results} />}
            {activeTab === 'insights' && <InsightsTab results={results} />}
            {activeTab === 'drilldown' && <DrilldownTab results={results} />}
            {activeTab === 'top-anomalies' && <TopAnomaliesTab results={results} />}
            {activeTab === 'regression' && <RegressionTab results={results} />}
            {activeTab === 'forecast' && <ForecastTab results={results} />}
          </>
        )}
      </div>
    </div>
  );
}
