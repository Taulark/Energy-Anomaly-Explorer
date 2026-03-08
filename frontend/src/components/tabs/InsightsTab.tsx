import { useState } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, Thermometer, Clock, Calendar, TrendingUp, Lightbulb, LucideIcon, ChevronDown, ChevronRight } from 'lucide-react';

interface InsightsTabProps {
  results: any;
}

interface InsightItem {
  text: string;
  type: 'warning' | 'info' | 'success';
  icon: LucideIcon;
}

interface ActionGroup {
  action: string;
  count: number;
  timestamps: string[];
  contexts: string[];
}

function parseInsightCard(card: string): InsightItem {
  let type: 'warning' | 'info' | 'success' = 'info';
  let icon: LucideIcon = Lightbulb;
  
  const lowerCard = card.toLowerCase();
  
  if (lowerCard.includes('low anomaly') || lowerCard.includes('stable') || lowerCard.includes('✅')) {
    type = 'success';
    icon = TrendingUp;
  } else if (
    lowerCard.includes('high') || 
    lowerCard.includes('critical') || 
    lowerCard.includes('concern') || 
    lowerCard.includes('🔴') || 
    lowerCard.includes('🚨') ||
    lowerCard.includes('⚠️')
  ) {
    type = 'warning';
    icon = AlertTriangle;
  } else if (lowerCard.includes('temperature') || lowerCard.includes('weather') || lowerCard.includes('🌡️') || lowerCard.includes('❄️')) {
    type = 'info';
    icon = Thermometer;
  } else if (lowerCard.includes('hour') || lowerCard.includes('time') || lowerCard.includes('🕐')) {
    type = 'info';
    icon = Clock;
  } else if (lowerCard.includes('weekday') || lowerCard.includes('weekend') || lowerCard.includes('📅')) {
    type = 'info';
    icon = Calendar;
  } else if (lowerCard.includes('recommended') || lowerCard.includes('💡')) {
    type = 'info';
    icon = Lightbulb;
  }
  
  const cleanText = card
    .replace(/✅|⚠️|🔴|🚨|🌡️|❄️|⚙️|🕐|📅|📈|💡|📊/g, '')
    .trim();
  
  return { text: cleanText, type, icon };
}

function formatHour(hour: number | string): string {
  let hourNum: number;
  if (typeof hour === 'string') {
    const match = hour.match(/^(\d+)/);
    hourNum = match ? parseInt(match[1], 10) : parseInt(hour, 10);
  } else {
    hourNum = hour;
  }
  if (isNaN(hourNum) || hourNum < 0 || hourNum > 23) return String(hour);
  if (hourNum === 0) return '12 AM';
  if (hourNum < 12) return `${hourNum} AM`;
  if (hourNum === 12) return '12 PM';
  return `${hourNum - 12} PM`;
}

function formatSeasonalValue(value: number | undefined): string {
  if (value === undefined || value === null) return '0.00%';
  const percentage = value <= 1 ? value * 100 : value;
  return `${percentage.toFixed(2)}%`;
}

function groupActions(actions: any[]): ActionGroup[] {
  const groups: Map<string, ActionGroup> = new Map();

  actions.forEach((anomaly: any) => {
    const actionItems = (anomaly.recommended_actions || '')
      .split(';')
      .map((s: string) => s.trim())
      .filter(Boolean);
    const datetime = anomaly.hour_datetime;
    const context = anomaly.explanation_summary || '';

    actionItems.forEach((item: string) => {
      if (!groups.has(item)) {
        groups.set(item, { action: item, count: 0, timestamps: [], contexts: [] });
      }
      const group = groups.get(item)!;
      group.count++;
      group.timestamps.push(datetime);
      if (context && !group.contexts.includes(context)) {
        group.contexts.push(context);
      }
    });
  });

  return [...groups.values()].sort((a, b) => b.count - a.count);
}

function ExecutiveSummary({ summaryCards }: { summaryCards: string[] }) {
  const insights: InsightItem[] = summaryCards.map(parseInsightCard);
  
  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.4, staggerChildren: 0.08 },
    },
  };
  
  const itemVariants = {
    hidden: { opacity: 0, x: -20 },
    visible: { opacity: 1, x: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  };
  
  const getTypeStyles = (type: 'warning' | 'info' | 'success') => {
    switch (type) {
      case 'warning':
        return { iconColor: 'text-yellow-400', bgColor: 'bg-yellow-400/10', borderColor: 'border-yellow-400/20' };
      case 'success':
        return { iconColor: 'text-green-400', bgColor: 'bg-green-400/10', borderColor: 'border-green-400/20' };
      default:
        return { iconColor: 'text-blue-400', bgColor: 'bg-blue-400/10', borderColor: 'border-blue-400/20' };
    }
  };
  
  return (
    <div>
      <h2 className="text-xl font-semibold text-white mb-4">Executive Summary</h2>
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-6">
        <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-3">
          {insights.map((insight, idx) => {
            const styles = getTypeStyles(insight.type);
            const IconComponent = insight.icon;
            return (
              <motion.div
                key={idx}
                variants={itemVariants}
                className={`flex items-start gap-3 p-3 rounded-lg ${styles.bgColor} border ${styles.borderColor}`}
              >
                <div className={`flex-shrink-0 mt-0.5 ${styles.iconColor}`}>
                  <IconComponent size={20} />
                </div>
                <p className="text-sm text-gray-300 flex-1 leading-relaxed">{insight.text}</p>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </div>
  );
}

function GroupedActions({ actions }: { actions: any[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const groups = groupActions(actions);

  const toggle = (idx: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const formatTs = (ts: string) =>
    new Date(ts).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true,
    });

  const getDateRange = (timestamps: string[]) => {
    const dates = timestamps.map(t => new Date(t)).sort((a, b) => a.getTime() - b.getTime());
    if (dates.length === 0) return '';
    const fmt = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    return dates.length === 1 ? fmt(dates[0]) : `${fmt(dates[0])} – ${fmt(dates[dates.length - 1])}`;
  };

  return (
    <div>
      <h2 className="text-xl font-semibold text-white mb-4">Recommended Actions</h2>
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4 space-y-0">
        {groups.map((group, idx) => (
          <div key={idx} className="border-b border-[#2d2d44] last:border-0 py-3 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-green-400">{group.action}</div>
                <div className="text-xs text-gray-400 mt-1">
                  {group.contexts.length > 0 && (
                    <span>{group.contexts.slice(0, 2).join(' · ')}</span>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {group.count} occurrence{group.count !== 1 ? 's' : ''} · {getDateRange(group.timestamps)}
                </div>
              </div>
              <button
                onClick={() => toggle(idx)}
                className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 whitespace-nowrap mt-0.5 transition-colors"
              >
                {expanded.has(idx) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                {expanded.has(idx) ? 'Hide' : 'View'} times
              </button>
            </div>
            {expanded.has(idx) && (
              <div className="mt-2 ml-2 pl-3 border-l border-[#2d2d44] max-h-40 overflow-y-auto space-y-0.5">
                {group.timestamps.map((ts, i) => (
                  <div key={i} className="text-xs text-gray-500">{formatTs(ts)}</div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function InsightsTab({ results }: InsightsTabProps) {
  if (!results) {
    return (
      <div className="text-center text-gray-400 py-8">
        No analysis results available. Run analysis first.
      </div>
    );
  }

  const insights = results.insights || { summary_cards: [], actions: [], recurrence: null };
  const occupancy = results.occupancy;
  const cost = results.cost;

  const hasInsights = insights && (
    (insights.summary_cards && insights.summary_cards.length > 0) ||
    (insights.actions && insights.actions.length > 0) ||
    insights.recurrence ||
    insights.error
  );

  if (!hasInsights && !insights.error) {
    return (
      <div className="text-center text-gray-400 py-8">
        Enable Insights & Actions in the sidebar and rerun analysis.
      </div>
    );
  }

  if (insights.error) {
    return (
      <div className="text-center text-red-400 py-8">
        <p>Insights generation failed: {insights.error}</p>
        <p className="text-sm text-gray-400 mt-2">Check backend logs for details.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {insights?.summary_cards && insights.summary_cards.length > 0 && (
        <ExecutiveSummary summaryCards={insights.summary_cards} />
      )}

      {insights?.actions && insights.actions.length > 0 && (
        <GroupedActions actions={insights.actions} />
      )}

      {insights?.recurrence && (
        <div>
          <h2 className="text-xl font-semibold text-white mb-4">Recurrence Analysis</h2>
          <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
            {insights.recurrence.top_hours && insights.recurrence.top_hours.length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-gray-300 mb-2">Top Hours for Anomalies</h3>
                <div className="text-xs text-gray-400">
                  {insights.recurrence.top_hours.map(formatHour).join(', ')}
                </div>
              </div>
            )}
            {insights.recurrence.top_weekdays && insights.recurrence.top_weekdays.length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-gray-300 mb-2">Top Days for Anomalies</h3>
                <div className="text-xs text-gray-400">
                  {insights.recurrence.top_weekdays.join(', ')}
                </div>
              </div>
            )}
            {insights.recurrence.season_split && (
              <div>
                <h3 className="text-sm font-semibold text-gray-300 mb-2">Seasonal Distribution</h3>
                <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
                  <div>Summer: {formatSeasonalValue(insights.recurrence.season_split.summer)}</div>
                  <div>Winter: {formatSeasonalValue(insights.recurrence.season_split.winter)}</div>
                  <div>Spring: {formatSeasonalValue(insights.recurrence.season_split.spring)}</div>
                  <div>Fall: {formatSeasonalValue(insights.recurrence.season_split.fall)}</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {occupancy && (
        <div>
          <h2 className="text-xl font-semibold text-white mb-4">Inferred Operating Behavior</h2>
          <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
            {occupancy.insights && (
              <ul className="list-disc list-inside space-y-2 text-sm text-gray-300">
                {occupancy.insights.map((insight: string, idx: number) => (
                  <li key={idx}>{insight}</li>
                ))}
              </ul>
            )}
            {occupancy.recommendations && (
              <div className="mt-4 pt-4 border-t border-[#2d2d44]">
                <h3 className="text-sm font-semibold text-green-400 mb-2">Recommended Actions</h3>
                <ul className="list-disc list-inside space-y-1 text-sm text-gray-300">
                  {occupancy.recommendations.map((rec: string, idx: number) => (
                    <li key={idx}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {cost && (
        <div>
          <h2 className="text-xl font-semibold text-white mb-4">Cost Impact Estimate</h2>
          <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-gray-400 mb-1">Excess Energy</div>
                <div className="text-lg font-semibold text-red-400">
                  {cost.excess_kwh?.toFixed(2) || 'N/A'} kWh
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">Avoided Energy</div>
                <div className="text-lg font-semibold text-green-400">
                  {cost.avoided_kwh?.toFixed(2) || 'N/A'} kWh
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">Estimated Cost</div>
                <div className="text-lg font-semibold text-yellow-400">
                  ${cost.estimated_cost?.toFixed(2) || 'N/A'}
                </div>
              </div>
            </div>
            {cost.disclaimer && (
              <div className="text-xs text-gray-500 mt-3 italic">{cost.disclaimer}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
