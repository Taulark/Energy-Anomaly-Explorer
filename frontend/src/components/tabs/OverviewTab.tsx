import { Shield, TrendingUp, TrendingDown, Minus, Clock, Calendar, Sun } from 'lucide-react';

interface OverviewTabProps {
  results: any;
}

function formatHour12(hour: number): string {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
}

function getHealthGrade(rate: number, avgZ: number) {
  if (rate < 1 && avgZ < 2.5)
    return { grade: 'Good', color: 'text-green-400', bg: 'bg-green-400/10', border: 'border-green-400/30', desc: 'Building operations are largely within expected ranges.' };
  if (rate < 3 && avgZ < 3.0)
    return { grade: 'Fair', color: 'text-yellow-400', bg: 'bg-yellow-400/10', border: 'border-yellow-400/30', desc: 'Some deviations detected — worth monitoring.' };
  if (rate < 5 && avgZ < 3.5)
    return { grade: 'Needs Attention', color: 'text-orange-400', bg: 'bg-orange-400/10', border: 'border-orange-400/30', desc: 'Recurring anomalies suggest operational issues to investigate.' };
  return { grade: 'Critical', color: 'text-red-400', bg: 'bg-red-400/10', border: 'border-red-400/30', desc: 'High anomaly frequency and severity — immediate review recommended.' };
}

function getSeason(month: number): string {
  if ([6, 7, 8].includes(month)) return 'Summer';
  if ([12, 1, 2].includes(month)) return 'Winter';
  if ([3, 4, 5].includes(month)) return 'Spring';
  return 'Fall';
}

export default function OverviewTab({ results }: OverviewTabProps) {
  if (!results) return null;

  const { anomaly_summary } = results;
  const topNUsed = results.top_n_used || 50;
  const zThresholdUsed = results.z_threshold_used || 2.0;
  const yearFilterUsed = results.year_filter_used || 'All';
  const regression = results.regression;

  const getMetricColor = (label: string, value: number) => {
    if (label === 'Anomaly Rate') {
      if (value < 1) return 'text-green-400';
      if (value < 5) return 'text-yellow-400';
      return 'text-red-400';
    }
    if (label === 'Avg |Z-Score|') {
      if (value < 2) return 'text-green-400';
      if (value < 3) return 'text-yellow-400';
      return 'text-red-400';
    }
    return 'text-blue-400';
  };

  const metrics = [
    { label: 'Total Hours', value: anomaly_summary.total_hours.toLocaleString(), color: 'text-blue-400' },
    { label: 'Anomaly Hours', value: anomaly_summary.anomaly_hours.toLocaleString(), color: 'text-orange-400' },
    { label: 'Anomaly Rate', value: `${anomaly_summary.anomaly_rate.toFixed(2)}%`, color: getMetricColor('Anomaly Rate', anomaly_summary.anomaly_rate) },
    { label: 'Avg |Z-Score|', value: anomaly_summary.avg_abs_z.toFixed(2), color: getMetricColor('Avg |Z-Score|', anomaly_summary.avg_abs_z) },
  ];

  const health = getHealthGrade(anomaly_summary.anomaly_rate, anomaly_summary.avg_abs_z);

  // Compute anomaly patterns from top_anomalies
  const topAnomalies = results.top_anomalies || [];
  let peakHour = '-';
  let peakDay = '-';
  let peakSeason = '-';
  const yearStats: Map<number, { count: number; totalZ: number; maxZ: number }> = new Map();

  if (topAnomalies.length > 0) {
    const hourCounts: Map<number, number> = new Map();
    const dayCounts: Map<number, number> = new Map();
    const seasonCounts: Map<string, number> = new Map();
    const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

    topAnomalies.forEach((item: any) => {
      const dt = new Date(item.hour_datetime);
      const h = dt.getHours();
      const d = dt.getDay(); // 0=Sun
      const m = dt.getMonth() + 1;
      const y = dt.getFullYear();
      const s = getSeason(m);

      hourCounts.set(h, (hourCounts.get(h) || 0) + 1);
      dayCounts.set(d, (dayCounts.get(d) || 0) + 1);
      seasonCounts.set(s, (seasonCounts.get(s) || 0) + 1);

      if (!yearStats.has(y)) yearStats.set(y, { count: 0, totalZ: 0, maxZ: 0 });
      const ys = yearStats.get(y)!;
      ys.count++;
      const z = Math.abs(item.z_score || 0);
      ys.totalZ += z;
      if (z > ys.maxZ) ys.maxZ = z;
    });

    const topHourEntry = [...hourCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    if (topHourEntry) peakHour = formatHour12(topHourEntry[0]);

    const topDayEntry = [...dayCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    if (topDayEntry) {
      const jsDay = topDayEntry[0]; // 0=Sun
      peakDay = dayNames[jsDay === 0 ? 6 : jsDay - 1];
    }

    const topSeasonEntry = [...seasonCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    if (topSeasonEntry) peakSeason = topSeasonEntry[0];
  }

  // Year-over-year trend
  const sortedYears = [...yearStats.entries()].sort(([a], [b]) => a - b);
  let trendLabel = 'Stable';
  let TrendIcon = Minus;
  let trendColor = 'text-gray-400';

  if (sortedYears.length >= 4) {
    const mid = Math.floor(sortedYears.length / 2);
    const firstHalfAvgZ = sortedYears.slice(0, mid).reduce((s, [, v]) => s + v.totalZ / v.count, 0) / mid;
    const secondHalfAvgZ = sortedYears.slice(mid).reduce((s, [, v]) => s + v.totalZ / v.count, 0) / (sortedYears.length - mid);
    const diff = secondHalfAvgZ - firstHalfAvgZ;

    if (diff > 0.2) {
      trendLabel = 'Worsening';
      TrendIcon = TrendingUp;
      trendColor = 'text-red-400';
    } else if (diff < -0.2) {
      trendLabel = 'Improving';
      TrendIcon = TrendingDown;
      trendColor = 'text-green-400';
    }
  }

  const confidenceBadge = regression?.confidence;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div>
        <h2 className="text-xl font-semibold text-white mb-4">Key Metrics</h2>
        <div className="grid grid-cols-4 gap-4">
          {metrics.map((metric, idx) => (
            <div
              key={idx}
              className="bg-gradient-to-br from-[#1e1e2e] to-[#252538] border border-[#2d2d44] rounded-xl p-4 shadow-lg"
            >
              <div className="text-sm text-gray-400 mb-1">{metric.label}</div>
              <div className={`text-2xl font-bold ${metric.color}`}>{metric.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Config Strip */}
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-3">
        <div className="text-xs text-gray-400">
          Z-threshold: {zThresholdUsed.toFixed(1)} · Top-N: {topNUsed} · Year: {yearFilterUsed}
          {regression?.method_used && <> · Model: {regression.method_used}</>}
        </div>
      </div>

      {/* Building Health + Model Confidence */}
      <div className="grid grid-cols-2 gap-4">
        {/* Health Grade */}
        <div className={`${health.bg} border ${health.border} rounded-xl p-5`}>
          <div className="flex items-center gap-3 mb-3">
            <Shield size={24} className={health.color} />
            <h3 className="text-lg font-semibold text-white">Building Health</h3>
          </div>
          <div className={`text-3xl font-bold ${health.color} mb-2`}>{health.grade}</div>
          <p className="text-sm text-gray-300">{health.desc}</p>
        </div>

        {/* Model Confidence */}
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-xl p-5">
          <h3 className="text-lg font-semibold text-white mb-3">Model Reliability</h3>
          {regression?.metrics ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">R² Score</span>
                <span className={`text-lg font-bold ${
                  regression.metrics.r2 >= 0.7 ? 'text-green-400' :
                  regression.metrics.r2 >= 0.4 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {regression.metrics.r2?.toFixed(3) ?? 'N/A'}
                </span>
              </div>
              {confidenceBadge && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-400">Confidence</span>
                  <span className={`text-sm font-medium px-2 py-0.5 rounded ${
                    confidenceBadge.level === 'Strong' ? 'bg-green-400/20 text-green-400' :
                    confidenceBadge.level === 'Moderate' ? 'bg-yellow-400/20 text-yellow-400' :
                    'bg-red-400/20 text-red-400'
                  }`}>
                    {confidenceBadge.level}
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">RMSE</span>
                <span className="text-sm text-gray-300">{regression.metrics.rmse?.toFixed(2) ?? 'N/A'}</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {regression.metrics.r2 >= 0.7
                  ? 'Model explains most of the variance — anomaly flags are reliable.'
                  : regression.metrics.r2 >= 0.4
                    ? 'Model captures moderate patterns — use anomaly flags as starting points for investigation.'
                    : 'Limited model fit — interpret anomaly flags with caution.'}
              </p>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Run analysis to see model performance.</p>
          )}
        </div>
      </div>

      {/* Anomaly Patterns at a Glance */}
      {topAnomalies.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold text-white mb-4">Anomaly Patterns at a Glance</h2>
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-xl p-4 flex items-start gap-3">
              <Clock size={20} className="text-blue-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-xs text-gray-400 mb-1">Peak Hour</div>
                <div className="text-sm font-semibold text-white">{peakHour}</div>
              </div>
            </div>
            <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-xl p-4 flex items-start gap-3">
              <Calendar size={20} className="text-purple-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-xs text-gray-400 mb-1">Peak Day</div>
                <div className="text-sm font-semibold text-white">{peakDay}</div>
              </div>
            </div>
            <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-xl p-4 flex items-start gap-3">
              <Sun size={20} className="text-yellow-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-xs text-gray-400 mb-1">Peak Season</div>
                <div className="text-sm font-semibold text-white">{peakSeason}</div>
              </div>
            </div>
            <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-xl p-4 flex items-start gap-3">
              <TrendIcon size={20} className={`${trendColor} mt-0.5 flex-shrink-0`} />
              <div>
                <div className="text-xs text-gray-400 mb-1">Trend</div>
                <div className={`text-sm font-semibold ${trendColor}`}>{trendLabel}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Year-over-Year Summary (compact) */}
      {sortedYears.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold text-white mb-4">Year-over-Year Summary</h2>
          <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#2d2d44]">
                    <th className="text-left py-2 text-gray-400">Year</th>
                    <th className="text-right py-2 text-gray-400">Top-N Count</th>
                    <th className="text-right py-2 text-gray-400">Avg Severity</th>
                    <th className="text-right py-2 text-gray-400">Peak Severity</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedYears.map(([year, stats]) => {
                    const avgZ = stats.totalZ / stats.count;
                    return (
                      <tr key={year} className="border-b border-[#2d2d44] hover:bg-[#252538]">
                        <td className="py-2 text-white">{year}</td>
                        <td className="text-right py-2 text-gray-300">{stats.count}</td>
                        <td className={`text-right py-2 ${avgZ > 3 ? 'text-red-400' : avgZ > 2.5 ? 'text-yellow-400' : 'text-green-400'}`}>
                          {avgZ.toFixed(2)}
                        </td>
                        <td className={`text-right py-2 ${stats.maxZ > 4 ? 'text-red-400' : stats.maxZ > 3 ? 'text-yellow-400' : 'text-green-400'}`}>
                          {stats.maxZ.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
