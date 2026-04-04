import { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, ReferenceLine,
} from 'recharts';
import { ShieldAlert, Zap, Loader2, AlertTriangle, ThermometerSun } from 'lucide-react';
import { api } from '../../api/client';

interface ForecastTabProps {
  results: any;
}

const TOOLTIP_STYLE = { backgroundColor: '#1e1e2e', border: '1px solid #2d2d44', color: '#fff' };
const TOOLTIP_ITEM = { color: '#e2e8f0' };
const TOOLTIP_LABEL = { color: '#94a3b8' };

function formatForecastError(err: any): string {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && 'message' in d) return String((d as { message: string }).message);
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return err?.message || 'Forecast failed';
}

function getRiskLevel(temp: number, ghi: number, avgTemp: number): { level: string; color: string; score: number } {
  const tempDeviation = Math.abs(temp - avgTemp);
  let score = 0;
  if (tempDeviation > 15) score += 3;
  else if (tempDeviation > 10) score += 2;
  else if (tempDeviation > 5) score += 1;
  if (ghi > 700) score += 1;
  if (temp > 35 || temp < 0) score += 2;
  else if (temp > 30 || temp < 5) score += 1;

  if (score >= 4) return { level: 'High', color: '#ef4444', score };
  if (score >= 2) return { level: 'Moderate', color: '#f59e0b', score };
  return { level: 'Low', color: '#22c55e', score };
}

export default function ForecastTab({ results }: ForecastTabProps) {
  const [forecast, setForecast] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const city = results?.city || results?.upload_info?.location || '';
  const building = results?.building || results?.upload_info?.building_name || '';

  useEffect(() => {
    if (!city || !building) return;
    setLoading(true);
    setError(null);
    api.getForecast(city, building)
      .then((data) => { setForecast(data); setLoading(false); })
      .catch((err) => {
        setError(formatForecastError(err)); setLoading(false);
      });
  }, [city, building]);

  const avgTemp = useMemo(() => {
    if (!forecast?.hourly_forecast?.length) return 20;
    return forecast.hourly_forecast.reduce((s: number, h: any) => s + h.temperature, 0) / forecast.hourly_forecast.length;
  }, [forecast]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-400 gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
        <span className="text-sm">Fetching 7-day weather forecast and generating anomaly risk assessment...</span>
      </div>
    );
  }

  if (error) {
    const isNoModel = error.toLowerCase().includes('run analysis first');
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertTriangle className="w-8 h-8 text-yellow-400" />
        <span className="text-gray-400 text-sm">{error}</span>
        {isNoModel && (
          <span className="text-gray-500 text-xs">Run the analysis first, then come back to this tab.</span>
        )}
      </div>
    );
  }

  if (!forecast) return null;

  const hourlyData = forecast.hourly_forecast || [];
  const dailySummary = forecast.daily_summary || [];
  const modelR2 = forecast.r2;
  const residualStd = forecast.residual_std;
  const wxSource = forecast.forecast_weather_source as string | undefined;
  const wxLabel =
    wxSource === 'MET_NORWAY' ? 'MET Norway (fallback)' : wxSource === 'OPEN_METEO' ? 'Open-Meteo' : 'Open-Meteo / MET Norway';

  const chartData = hourlyData.map((h: any) => {
    const risk = getRiskLevel(h.temperature, h.ghi, avgTemp);
    return {
      ...h,
      dt: new Date(h.datetime).getTime(),
      risk_score: risk.score,
      risk_level: risk.level,
      band_width: h.upper_bound - h.lower_bound,
    };
  });

  const highRiskHours = chartData.filter((h: any) => h.risk_level === 'High');
  const moderateRiskHours = chartData.filter((h: any) => h.risk_level === 'Moderate');
  const totalForecastKwh = dailySummary.reduce((s: number, d: any) => s + d.total_kwh, 0);
  const peakDay = dailySummary.reduce((max: any, d: any) => d.total_kwh > (max?.total_kwh || 0) ? d : max, dailySummary[0]);

  const dailyRiskData = dailySummary.map((d: any) => {
    const dayHours = hourlyData.filter((h: any) => h.date === d.date);
    const dayHighRisk = dayHours.filter((h: any) => getRiskLevel(h.temperature, h.ghi, avgTemp).level === 'High').length;
    const dayModRisk = dayHours.filter((h: any) => getRiskLevel(h.temperature, h.ghi, avgTemp).level === 'Moderate').length;
    return {
      ...d,
      label: `${d.day_of_week.slice(0, 3)} ${d.date.slice(5)}`,
      high_risk_hours: dayHighRisk,
      moderate_risk_hours: dayModRisk,
      low_risk_hours: 24 - dayHighRisk - dayModRisk,
      risk_score: dayHighRisk * 3 + dayModRisk,
    };
  });

  const overallRisk = highRiskHours.length > 20 ? 'High' : highRiskHours.length > 5 ? 'Moderate' : 'Low';
  const overallRiskColor = overallRisk === 'High' ? 'text-red-400' : overallRisk === 'Moderate' ? 'text-yellow-400' : 'text-green-400';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-6 h-6 text-blue-400" />
          <div>
            <h2 className="text-lg font-semibold text-white">7-Day Anomaly Risk Forecast</h2>
            <p className="text-xs text-gray-500">
              Expected baseline consumption &amp; anomaly risk windows &middot; Model R² = {modelR2 != null ? modelR2.toFixed(3) : 'N/A'}
            </p>
          </div>
        </div>
        <div className={`text-sm font-semibold ${overallRiskColor} bg-[#1e1e2e] border border-[#2d2d44] rounded-lg px-3 py-1.5`}>
          Overall Risk: {overallRisk}
        </div>
      </div>

      {modelR2 != null && modelR2 < 0.3 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-yellow-300">
            Low R² ({(modelR2 * 100).toFixed(0)}%) — weather explains limited variance. Risk assessment is approximate.
          </p>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
            <ShieldAlert className="w-3.5 h-3.5 text-red-400" /> High Risk Hours
          </div>
          <p className="text-2xl font-bold text-red-400">{highRiskHours.length}</p>
          <p className="text-xs text-gray-500">of {hourlyData.length} hours</p>
        </div>
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
            <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" /> Moderate Risk
          </div>
          <p className="text-2xl font-bold text-yellow-400">{moderateRiskHours.length}</p>
          <p className="text-xs text-gray-500">hours to monitor</p>
        </div>
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
            <Zap className="w-3.5 h-3.5" /> Expected Total
          </div>
          <p className="text-2xl font-bold text-white">{Math.round(totalForecastKwh).toLocaleString()}</p>
          <p className="text-xs text-gray-500">kWh baseline ({dailySummary.length} days)</p>
        </div>
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
            <ThermometerSun className="w-3.5 h-3.5 text-orange-400" /> Peak Stress Day
          </div>
          <p className="text-2xl font-bold text-white">{peakDay?.day_of_week?.slice(0, 3) || '—'}</p>
          <p className="text-xs text-gray-500">{peakDay ? `${peakDay.max_temp}°C, ${Math.round(peakDay.total_kwh).toLocaleString()} kWh` : ''}</p>
        </div>
      </div>

      {/* Main Chart: Expected Baseline + Anomaly Band */}
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-1">Expected Consumption Baseline</h3>
        <p className="text-[10px] text-gray-500 mb-4">
          Shaded band = normal range. Any actual consumption outside this band would be flagged as an anomaly.
        </p>
        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={chartData} margin={{ top: 5, right: 20, bottom: 28, left: 40 }}>
            <defs>
              <linearGradient id="fGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="bandUpper" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.12} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" />
            <XAxis
              dataKey="dt" type="number" scale="time"
              domain={['dataMin', 'dataMax']} stroke="#9aa0a6"
              tickFormatter={(v) => {
                const d = new Date(v);
                return d.toLocaleDateString([], { weekday: 'short' }) + ' ' + d.toLocaleTimeString([], { hour: 'numeric' });
              }}
              tick={{ fontSize: 10 }} interval={23}
            />
            <YAxis stroke="#9aa0a6" label={{ value: 'kWh', angle: -90, position: 'insideLeft', style: { fill: '#9aa0a6' } }} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM} labelStyle={TOOLTIP_LABEL}
              labelFormatter={(v) => new Date(v).toLocaleString([], { weekday: 'long', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
              formatter={(value: any, name: string) => {
                if (name === 'Normal Range (Upper)' || name === 'Normal Range (Lower)') return null;
                if (name === 'Expected Baseline') return [`${Number(value).toFixed(1)} kWh`, name];
                return [value, name];
              }}
            />
            <Area type="monotone" dataKey="upper_bound" stroke="#22c55e" strokeWidth={0.5} strokeDasharray="4 4" fill="url(#bandUpper)" name="Normal Range (Upper)" />
            <Area type="monotone" dataKey="lower_bound" stroke="#22c55e" strokeWidth={0.5} strokeDasharray="4 4" fill="#13131f" name="Normal Range (Lower)" />
            <Area type="monotone" dataKey="predicted_kwh" stroke="#3b82f6" strokeWidth={2} fill="url(#fGrad)" name="Expected Baseline" />
          </AreaChart>
        </ResponsiveContainer>
        <div className="flex items-center justify-center gap-6 mt-2 text-[10px] text-gray-500">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block" /> Expected Baseline</span>
          <span className="flex items-center gap-1"><span className="w-6 h-0 border-t border-dashed border-green-500 inline-block" /> Normal Range (±{residualStd > 0 ? residualStd.toFixed(0) : '?'} kWh)</span>
          <span className="text-gray-600">Anything outside = potential anomaly</span>
        </div>
      </div>

      {/* Row: Daily Risk + Risk Table */}
      <div className="grid grid-cols-2 gap-4">
        {/* Daily Risk Bar */}
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Daily Anomaly Risk Score</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={dailyRiskData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" vertical={false} />
              <XAxis dataKey="label" stroke="#9aa0a6" tick={{ fontSize: 11 }} />
              <YAxis stroke="#9aa0a6" label={{ value: 'Risk Score', angle: -90, position: 'insideLeft', style: { fill: '#9aa0a6', fontSize: 10 } }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM} labelStyle={TOOLTIP_LABEL}
                formatter={(value: any, name: string) => {
                  if (name === 'Risk Score') return [value, 'Risk Score'];
                  return [value, name];
                }} />
              <ReferenceLine y={10} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'High Risk', fill: '#ef4444', fontSize: 9, position: 'right' }} />
              <Bar dataKey="risk_score" radius={[4, 4, 0, 0]} name="Risk Score">
                {dailyRiskData.map((d: any, idx: number) => (
                  <Cell key={idx} fill={d.risk_score >= 10 ? '#ef4444' : d.risk_score >= 4 ? '#f59e0b' : '#22c55e'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex items-center justify-center gap-4 mt-2 text-[10px] text-gray-500">
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block" /> Low</span>
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-yellow-500 inline-block" /> Moderate</span>
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-500 inline-block" /> High</span>
          </div>
        </div>

        {/* Daily Breakdown Table */}
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Daily Forecast & Risk Breakdown</h3>
          <div className="overflow-auto max-h-[320px]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#1e1e2e]">
                <tr className="text-gray-400 border-b border-[#2d2d44]">
                  <th className="text-left py-2 px-2">Day</th>
                  <th className="text-right py-2 px-2">Baseline kWh</th>
                  <th className="text-right py-2 px-2">Peak Hour</th>
                  <th className="text-right py-2 px-2">Temp</th>
                  <th className="text-center py-2 px-2">Risk</th>
                </tr>
              </thead>
              <tbody>
                {dailyRiskData.map((d: any, idx: number) => {
                  const riskColor = d.risk_score >= 10 ? 'text-red-400' : d.risk_score >= 4 ? 'text-yellow-400' : 'text-green-400';
                  const riskLabel = d.risk_score >= 10 ? 'High' : d.risk_score >= 4 ? 'Mod' : 'Low';
                  return (
                    <tr key={idx} className="border-b border-[#2d2d44]/50 hover:bg-[#252540]">
                      <td className="py-2 px-2 text-gray-300">{d.day_of_week.slice(0, 3)} {d.date.slice(5)}</td>
                      <td className="py-2 px-2 text-right text-white font-medium">{Math.round(d.total_kwh).toLocaleString()}</td>
                      <td className="py-2 px-2 text-right text-gray-400">{d.peak_hour}</td>
                      <td className="py-2 px-2 text-right text-gray-400">{d.min_temp}°–{d.max_temp}°C</td>
                      <td className={`py-2 px-2 text-center font-semibold ${riskColor}`}>{riskLabel}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* How to read this section */}
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">How to Use This Forecast</h3>
        <div className="grid grid-cols-3 gap-4 text-xs text-gray-400">
          <div>
            <p className="text-white font-medium mb-1">The Baseline</p>
            <p>The blue line shows what your building <em>should</em> consume based on the 7-day weather forecast, using the same regression model from your analysis.</p>
          </div>
          <div>
            <p className="text-white font-medium mb-1">The Normal Range</p>
            <p>The green dashed band (±{residualStd > 0 ? residualStd.toFixed(0) : '?'} kWh) represents normal variation. Any actual reading outside this band in the next 7 days would be flagged as an anomaly.</p>
          </div>
          <div>
            <p className="text-white font-medium mb-1">Risk Assessment</p>
            <p>High risk periods have extreme weather (very hot/cold, high solar) where the building is stressed and anomalies are most likely to occur. Monitor these hours closely.</p>
          </div>
        </div>
      </div>

      {/* Model Info Footer */}
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-3 flex items-center justify-between text-xs text-gray-500">
        <span>Model: ElasticNet &middot; Features: {forecast.model_features?.join(', ')}</span>
        <span>Weather: {wxLabel} &middot; {forecast.forecast_days}-day horizon</span>
      </div>
    </div>
  );
}
