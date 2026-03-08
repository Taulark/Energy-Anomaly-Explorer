import {
  ComposedChart, Line, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, BarChart, Bar, PieChart, Pie, Cell,
} from 'recharts';

interface DrilldownTabProps {
  results: any;
}

const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

const SEASON_COLORS: Record<string, string> = {
  Winter: '#60a5fa', Spring: '#4ade80', Summer: '#facc15', Fall: '#fb923c',
};

const SEVERITY_COLORS = ['#facc15', '#f97316', '#ef4444', '#dc2626', '#991b1b'];

const CAUSE_COLORS = ['#3b82f6', '#8b5cf6', '#f97316', '#22c55e', '#ef4444', '#ec4899', '#14b8a6'];

function fmt12(hour: number): string {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
}

function getSeason(month: number): string {
  if ([11, 0, 1].includes(month)) return 'Winter'; // JS months 0-indexed
  if ([2, 3, 4].includes(month)) return 'Spring';
  if ([5, 6, 7].includes(month)) return 'Summer';
  return 'Fall';
}

function simplifyCauseTag(tag: string): string | null {
  const t = tag.trim();
  if (t.includes('Weather')) return 'Weather-driven';
  if (t.includes('After-hours')) return 'After-hours';
  if (t.includes('Weekend')) return 'Weekend';
  if (t.includes('Sustained')) return 'Sustained event';
  if (t.includes('Operational') || t.includes('Internal')) return 'Internal/Operational';
  if (t.includes('sensor') || t.includes('meter')) return 'Sensor/Meter issue';
  if (t.includes('Solar')) return 'Solar mismatch';
  if (t.includes('Summer') || t.includes('Winter')) return null; // seasonal label, not cause
  if (t.includes('severity')) return null; // severity label, not cause
  return null;
}

const CUSTOM_TOOLTIP_STYLE = { backgroundColor: '#1e1e2e', border: '1px solid #2d2d44', color: '#fff' };
const TOOLTIP_ITEM_STYLE = { color: '#e2e8f0' };
const TOOLTIP_LABEL_STYLE = { color: '#94a3b8' };

export default function DrilldownTab({ results }: DrilldownTabProps) {
  const drilldownData = results.drilldown_anomalies || results.top_anomalies;
  if (!results || !drilldownData || drilldownData.length === 0) return null;

  const yearFilterUsed = results.year_filter_used || 'All';
  const topAnomalies = results.top_anomalies || [];

  // ── Prepare time-series data (existing logic) ──
  let filteredAnomalies = drilldownData;
  if (yearFilterUsed !== 'All') {
    const year = parseInt(yearFilterUsed);
    filteredAnomalies = drilldownData.filter((item: any) =>
      new Date(item.hour_datetime).getFullYear() === year
    );
  }

  filteredAnomalies = [...filteredAnomalies].sort(
    (a: any, b: any) => new Date(a.hour_datetime).getTime() - new Date(b.hour_datetime).getTime()
  );

  let chartData = filteredAnomalies;
  if (chartData.length > 2000) {
    const step = Math.ceil(chartData.length / 2000);
    chartData = chartData.filter((_: any, idx: number) => idx % step === 0);
    if (chartData.length > 0 && filteredAnomalies.length > 0) {
      chartData[0] = filteredAnomalies[0];
      chartData[chartData.length - 1] = filteredAnomalies[filteredAnomalies.length - 1];
    }
  }

  const chartDataFormatted = chartData
    .map((item: any) => ({
      datetime: new Date(item.hour_datetime).getTime(),
      actual: item.actual,
      predicted: item.predicted,
      residual: item.residual,
      z_score: item.z_score,
      abs_z: Math.abs(item.z_score || 0),
      anomaly: Boolean(item.anomaly),
    }))
    .sort((a: any, b: any) => a.datetime - b.datetime);

  const timestamps = chartDataFormatted.map((d: any) => d.datetime).filter((ts: any) => !isNaN(ts));
  const minTs = timestamps.length > 0 ? Math.min(...timestamps) : Date.now();
  const maxTs = timestamps.length > 0 ? Math.max(...timestamps) : Date.now();
  const timeRange = maxTs - minTs;
  const timeBuffer = Math.max(timeRange * 0.02, 6 * 3600000);
  const xAxisDomain: [number, number] = [minTs - timeBuffer, maxTs + timeBuffer];

  const anomalyPoints = chartDataFormatted.filter((d: any) => d.anomaly);

  const residuals = chartDataFormatted.map((d: any) => d.residual).filter((r: any) => !isNaN(r));
  const maxAbsResidual = residuals.length > 0 ? Math.max(...residuals.map((r: any) => Math.abs(r))) : 1;
  const yPad = maxAbsResidual * 0.15;
  const yAxisDomain: [number, number] = [-maxAbsResidual - yPad, maxAbsResidual + yPad];

  const formatYTick = (v: number) =>
    Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : Math.abs(v) >= 1 ? v.toFixed(1) : v.toFixed(2);

  // ── Compute new chart data from top anomalies ──

  // Hourly distribution
  const hourCounts = new Array(24).fill(0);
  topAnomalies.forEach((a: any) => { hourCounts[new Date(a.hour_datetime).getHours()]++; });
  const hourData = hourCounts.map((count: number, h: number) => ({
    hour: fmt12(h), count, hourNum: h,
  }));

  // Monthly distribution
  const monthCounts = new Array(12).fill(0);
  topAnomalies.forEach((a: any) => { monthCounts[new Date(a.hour_datetime).getMonth()]++; });
  const monthData = MONTH_NAMES.map((name, idx) => ({
    month: name, count: monthCounts[idx], season: getSeason(idx),
  }));

  // Z-Score severity histogram
  const severityBins = [
    { range: '2.0–2.5', min: 2.0, max: 2.5, count: 0 },
    { range: '2.5–3.0', min: 2.5, max: 3.0, count: 0 },
    { range: '3.0–3.5', min: 3.0, max: 3.5, count: 0 },
    { range: '3.5–4.0', min: 3.5, max: 4.0, count: 0 },
    { range: '4.0+', min: 4.0, max: Infinity, count: 0 },
  ];
  topAnomalies.forEach((a: any) => {
    const z = Math.abs(a.z_score || 0);
    for (const bin of severityBins) {
      if (z >= bin.min && (z < bin.max || bin.max === Infinity)) { bin.count++; break; }
    }
  });

  // Anomaly cause breakdown (from insights actions if available)
  const actions = results.insights?.actions || [];
  const causeCounts: Record<string, number> = {};
  actions.forEach((a: any) => {
    const tags = (a.explanation_tags || '').split(',');
    const seen = new Set<string>();
    for (const tag of tags) {
      const cause = simplifyCauseTag(tag);
      if (cause && !seen.has(cause)) {
        seen.add(cause);
        causeCounts[cause] = (causeCounts[cause] || 0) + 1;
      }
    }
  });
  const causeData = Object.entries(causeCounts)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  // Day-of-week distribution (for the pie chart fallback when no insights)
  const dayCounts = new Array(7).fill(0);
  topAnomalies.forEach((a: any) => { dayCounts[new Date(a.hour_datetime).getDay()]++; });
  const dayData = DAY_NAMES.map((name, idx) => ({ name, value: dayCounts[idx] })).filter(d => d.value > 0);

  const hasCauseData = causeData.length > 0;
  const pieData = hasCauseData ? causeData : dayData;
  const pieTitle = hasCauseData ? 'Anomaly Cause Breakdown' : 'Anomalies by Day of Week';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-white">Building Drilldown</h2>
        <span className="text-xs text-gray-400">
          Year: {yearFilterUsed} · {topAnomalies.length} anomalies · {chartDataFormatted.length.toLocaleString()} pts
        </span>
      </div>

      {/* ── Actual vs Predicted ── */}
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Actual vs Predicted Load (Anomalies Highlighted)</h3>
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartDataFormatted} margin={{ top: 20, right: 30, bottom: 35, left: 25 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" />
            <XAxis dataKey="datetime" stroke="#9aa0a6" type="number" scale="time"
              domain={xAxisDomain} padding={{ left: 20, right: 20 }}
              tickFormatter={(v) => new Date(v).toLocaleDateString()} />
            <YAxis stroke="#9aa0a6" width={50} domain={[0, (dataMax: number) => Math.ceil(dataMax * 1.1)]} />
            <Tooltip contentStyle={CUSTOM_TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE}
              labelFormatter={(v) => new Date(v).toLocaleString()} />
            <Legend verticalAlign="bottom" align="center" wrapperStyle={{ paddingTop: 12 }} />
            <Line type="monotone" dataKey="actual" stroke="#3b82f6" strokeWidth={2} dot={false} name="Actual" />
            <Line type="monotone" dataKey="predicted" stroke="#22c55e" strokeWidth={2} dot={false} name="Predicted" />
            <Scatter data={anomalyPoints} dataKey="actual" fill="#ef4444" name="Anomaly"
              shape={(props: any) => <circle cx={props.cx} cy={props.cy} r={4} fill="#ef4444" opacity={0.8} />} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ── Residuals over Time ── */}
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Residuals over Time</h3>
        <ResponsiveContainer width="100%" height={370}>
          <ComposedChart data={chartDataFormatted} margin={{ top: 20, right: 30, bottom: 35, left: 64 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" />
            <XAxis dataKey="datetime" stroke="#9aa0a6" type="number" scale="time"
              domain={xAxisDomain} padding={{ left: 20, right: 20 }}
              tickFormatter={(v) => new Date(v).toLocaleDateString()} />
            <YAxis stroke="#9aa0a6" domain={yAxisDomain} allowDataOverflow={false} tickFormatter={formatYTick} />
            <Tooltip contentStyle={CUSTOM_TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE}
              labelFormatter={(v) => new Date(v).toLocaleString()}
              formatter={(value: any, name: string) => {
                if (name === 'Residual' && typeof value === 'number') return [value.toFixed(2), 'Residual'];
                if (name === 'Anomaly') return null;
                return typeof value === 'number' ? [value.toFixed(2), name] : [value, name];
              }} />
            <Legend verticalAlign="bottom" align="center" wrapperStyle={{ paddingTop: 12 }} />
            <Line type="monotone" dataKey="residual" stroke="#8b5cf6" strokeWidth={1.2} dot={false} name="Residual" />
            <ReferenceLine y={0} stroke="#6b7280" strokeWidth={1} strokeDasharray="5 5" />
            <Scatter data={anomalyPoints} dataKey="residual" fill="#ef4444" name="Anomaly"
              shape={(props: any) => <circle cx={props.cx} cy={props.cy} r={3} fill="#ef4444" opacity={0.8} />} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ── Row: Hourly + Monthly Distribution ── */}
      <div className="grid grid-cols-2 gap-4">
        {/* Anomalies by Hour */}
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Anomalies by Hour of Day</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={hourData} margin={{ top: 15, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" vertical={false} />
              <XAxis dataKey="hour" stroke="#9aa0a6" tick={{ fontSize: 10 }} interval={2} />
              <YAxis stroke="#9aa0a6" allowDecimals={false} domain={[0, (dataMax: number) => Math.ceil(dataMax * 1.15)]} />
              <Tooltip contentStyle={CUSTOM_TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE}
                formatter={(value: any) => [value, 'Anomalies']} />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {hourData.map((entry, idx) => {
                  const isBusinessHours = entry.hourNum >= 7 && entry.hourNum < 19;
                  return <Cell key={idx} fill={isBusinessHours ? '#3b82f6' : '#6366f1'} />;
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex items-center justify-center gap-4 mt-2 text-[10px] text-gray-500">
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block" /> Business hours</span>
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-indigo-500 inline-block" /> Off-hours</span>
          </div>
        </div>

        {/* Anomalies by Month */}
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Monthly Anomaly Distribution</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={monthData} margin={{ top: 15, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" vertical={false} />
              <XAxis dataKey="month" stroke="#9aa0a6" tick={{ fontSize: 11 }} />
              <YAxis stroke="#9aa0a6" allowDecimals={false} domain={[0, (dataMax: number) => Math.ceil(dataMax * 1.15)]} />
              <Tooltip contentStyle={CUSTOM_TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE}
                formatter={(value: any) => [value, 'Anomalies']} />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {monthData.map((entry, idx) => (
                  <Cell key={idx} fill={SEASON_COLORS[entry.season] || '#6b7280'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex items-center justify-center gap-3 mt-2 text-[10px] text-gray-500">
            {Object.entries(SEASON_COLORS).map(([season, color]) => (
              <span key={season} className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ backgroundColor: color }} />
                {season}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row: Severity Histogram + Cause/Day Breakdown ── */}
      <div className="grid grid-cols-2 gap-4">
        {/* Z-Score Severity Distribution */}
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Anomaly Severity Distribution</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={severityBins} margin={{ top: 15, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" vertical={false} />
              <XAxis dataKey="range" stroke="#9aa0a6" tick={{ fontSize: 11 }} />
              <YAxis stroke="#9aa0a6" allowDecimals={false} domain={[0, (dataMax: number) => Math.ceil(dataMax * 1.15)]} />
              <Tooltip contentStyle={CUSTOM_TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE}
                formatter={(value: any) => [value, 'Anomalies']}
                labelFormatter={(label) => `|Z-Score| ${label}`} />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {severityBins.map((_, idx) => (
                  <Cell key={idx} fill={SEVERITY_COLORS[idx]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="text-center mt-2 text-[10px] text-gray-500">
            Mild → Critical severity (left to right)
          </div>
        </div>

        {/* Cause Breakdown / Day-of-Week Pie */}
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">{pieTitle}</h3>
          <div className="flex items-center gap-4">
            <div className="flex-shrink-0" style={{ width: 200, height: 200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={false}
                  >
                    {pieData.map((_, idx) => (
                      <Cell key={idx} fill={CAUSE_COLORS[idx % CAUSE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={CUSTOM_TOOLTIP_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE}
                    formatter={(value: any, name: string) => [value, name]} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-2">
              {pieData.map((entry, idx) => {
                const total = pieData.reduce((s, d) => s + d.value, 0);
                const pct = total > 0 ? ((entry.value / total) * 100).toFixed(0) : '0';
                return (
                  <div key={idx} className="flex items-center gap-2 text-xs">
                    <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: CAUSE_COLORS[idx % CAUSE_COLORS.length] }} />
                    <span className="text-gray-300 flex-1">{entry.name}</span>
                    <span className="text-gray-400 font-medium">{pct}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── Top Anomalies Table ── */}
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">
          Top Anomalies
          <span className="text-xs text-gray-500 font-normal ml-2">(showing top 20 by severity)</span>
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2d2d44]">
                <th className="text-left py-2 text-gray-400">DateTime</th>
                <th className="text-right py-2 text-gray-400">Actual</th>
                <th className="text-right py-2 text-gray-400">Predicted</th>
                <th className="text-right py-2 text-gray-400">Residual</th>
                <th className="text-right py-2 text-gray-400">|Z-Score|</th>
              </tr>
            </thead>
            <tbody>
              {[...topAnomalies]
                .sort((a: any, b: any) => Math.abs(b.z_score || 0) - Math.abs(a.z_score || 0))
                .slice(0, 20)
                .map((item: any, idx: number) => {
                  const absZ = Math.abs(item.z_score || 0);
                  const zColor = absZ >= 4 ? 'text-red-500' : absZ >= 3 ? 'text-red-400' : absZ >= 2.5 ? 'text-orange-400' : 'text-yellow-400';
                  return (
                    <tr key={idx} className="border-b border-[#2d2d44] hover:bg-[#252538]">
                      <td className="py-2 text-gray-300">
                        {new Date(item.hour_datetime).toLocaleString('en-US', {
                          month: 'short', day: 'numeric', year: 'numeric',
                          hour: 'numeric', minute: '2-digit', hour12: true,
                        })}
                      </td>
                      <td className="text-right py-2 text-white">{item.actual?.toFixed(2)}</td>
                      <td className="text-right py-2 text-gray-400">{item.predicted?.toFixed(2)}</td>
                      <td className={`text-right py-2 ${(item.residual || 0) >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                        {item.residual >= 0 ? '+' : ''}{item.residual?.toFixed(2)}
                      </td>
                      <td className={`text-right py-2 font-medium ${zColor}`}>
                        {absZ.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
