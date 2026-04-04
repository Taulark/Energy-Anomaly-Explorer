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
    <div className="px-3 py-4 md:p-6">
      {/* Tabs — horizontal scroll on small screens */}
      <div className="relative -mx-1 mb-4 md:mx-0 md:mb-6">
        <div
          className="tabs-scroll flex gap-1 overflow-x-auto overflow-y-hidden border-b border-[#2d2d44] pb-px [-webkit-overflow-scrolling:touch] [scrollbar-width:thin]"
          style={{ scrollbarColor: '#3f3f5a transparent' }}
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`shrink-0 snap-start px-3 py-3 text-center text-sm font-medium transition-colors md:px-4 md:py-2 ${
                activeTab === tab.id
                  ? 'border-b-2 border-blue-500 text-white'
                  : 'border-b-2 border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div>
        {isRunning && (
          <div className="space-y-6 py-10 text-center">
            <div className="mx-auto max-w-md space-y-3 px-2">
              <p className="text-sm font-medium text-gray-300">Running analysis…</p>
              <p className="text-xs text-gray-500">
                Large datasets can take a few minutes. You can leave this screen open.
              </p>
              <div className="relative h-2.5 overflow-hidden rounded-full bg-[#2d2d44]">
                <div className="absolute inset-y-0 w-2/5 rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/30 animate-loadbar" />
              </div>
            </div>
          </div>
        )}
        {!isRunning && !results && (
          <div className="px-2 py-12 text-center text-sm text-gray-400">
            Open the menu (☰), choose a city and building, then run anomaly detection.
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
