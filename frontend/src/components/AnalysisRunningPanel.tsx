import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Timer } from 'lucide-react';

const STAGES: { headline: string; detail: string }[] = [
  {
    headline: 'Syncing your dataset',
    detail: 'Aligning hourly load with weather and calendar signals.',
  },
  {
    headline: 'Teaching the baseline model',
    detail: 'Regression is learning what “normal” looks like for this building.',
  },
  {
    headline: 'Hunting for outliers',
    detail: 'Scanning residuals so unusual spikes rise to the top.',
  },
  {
    headline: 'Scoring every hour',
    detail: 'Turning statistics into z-scores you can trust.',
  },
  {
    headline: 'Packaging insights',
    detail: 'Summaries, charts, and anomaly tables are almost ready.',
  },
  {
    headline: 'Polishing the results',
    detail: 'Perfect moment to stretch — algorithms are doing the heavy lifting.',
  },
];

const STAGE_INTERVAL_MS = 8500;
const PROGRESS_CAP = 93;
const PROGRESS_TAU_MS = 100000;

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m > 0 ? `${m}:${r.toString().padStart(2, '0')}` : `${r}s`;
}

function simulatedPercent(elapsedMs: number): number {
  return Math.min(
    PROGRESS_CAP,
    PROGRESS_CAP * (1 - Math.exp(-elapsedMs / PROGRESS_TAU_MS)),
  );
}

interface AnalysisRunningPanelProps {
  active: boolean;
}

export default function AnalysisRunningPanel({ active }: AnalysisRunningPanelProps) {
  const [pct, setPct] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      setPct(0);
      setElapsed(0);
      return;
    }
    const started = Date.now();
    const tick = () => {
      const ms = Date.now() - started;
      setElapsed(ms);
      setPct(simulatedPercent(ms));
    };
    tick();
    const id = window.setInterval(tick, 120);
    return () => clearInterval(id);
  }, [active]);

  const stageIndex = Math.min(
    STAGES.length - 1,
    Math.floor(elapsed / STAGE_INTERVAL_MS),
  );
  const stage = STAGES[stageIndex];
  const displayPct = Math.round(pct);

  if (!active) return null;

  return (
    <div
      className="py-8 md:py-12"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="mx-auto max-w-lg md:max-w-xl rounded-2xl border border-[#2d2d44] bg-[#1a1a2e]/90 p-6 shadow-xl shadow-indigo-950/20 backdrop-blur-sm md:p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center md:flex-row md:items-start md:justify-between md:text-left">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600/25 text-indigo-300">
              <Sparkles className="h-6 w-6" aria-hidden />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-indigo-300/90">
                Analysis in progress
              </p>
              <h2 className="text-lg font-semibold text-white md:text-xl">
                Crunching your anomaly detection run
              </h2>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-[#2d2d44] bg-[#252538]/80 px-3 py-1.5 text-xs text-gray-400">
            <Timer className="h-3.5 w-3.5 shrink-0 text-amber-400/90" aria-hidden />
            <span className="tabular-nums">{formatElapsed(elapsed)}</span>
            <span className="text-gray-600">·</span>
            <span className="text-gray-500">typ. 3–5 min</span>
          </div>
        </div>

        <div className="mb-2 flex items-end justify-between gap-4">
          <div className="min-h-[4.75rem] min-w-0 flex-1">
            <AnimatePresence mode="wait">
              <motion.div
                key={stageIndex}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.28, ease: 'easeOut' }}
              >
                <p className="text-sm font-medium text-gray-200">{stage.headline}</p>
                <p className="mt-1 text-xs leading-relaxed text-gray-500 md:text-sm">
                  {stage.detail}
                </p>
              </motion.div>
            </AnimatePresence>
          </div>
          <span
            className="shrink-0 text-2xl font-bold tabular-nums text-transparent md:text-3xl"
            style={{
              backgroundImage: 'linear-gradient(120deg, #818cf8, #c084fc, #818cf8)',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
            }}
            aria-label={`Estimated progress ${displayPct} percent`}
          >
            {displayPct}%
          </span>
        </div>

        <div className="relative h-3 overflow-hidden rounded-full bg-[#2d2d44]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-purple-500 shadow-lg shadow-indigo-500/25 transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>

        <p className="mt-4 text-center text-[11px] text-gray-600 md:text-xs">
          This percentage is a friendly estimate from time — not live server telemetry.
          Hanging near the end is normal.
        </p>
      </div>
    </div>
  );
}
