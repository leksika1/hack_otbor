import React, { useMemo, useState } from 'react';
import { formatCost, formatDuration, formatNumber } from '../../utils/format';
import AgentsMdPanel from './AgentsMdPanel';
import FindingsPanel from './FindingsPanel';
import MetricsGrid from './MetricsGrid';
import StepInspector from './StepInspector';
import StepTrace from './StepTrace';
import Timeline from './Timeline';

function ProviderBadge({ provider, isMock }) {
  return (
    <span
      className={`text-[10px] uppercase font-bold px-2 py-1 rounded border ${
        isMock
          ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
          : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
      }`}
      title={isMock ? 'Объяснения сгенерированы офлайн-заглушкой, а не реальной моделью' : 'Объяснения от LLM'}
    >
      {isMock ? `mock: ${provider}` : provider}
    </span>
  );
}

export default function Dashboard({ report, onReset }) {
  const { summary, findings, explanations, steps } = report;
  const [activeStep, setActiveStep] = useState(null);

  const stepsById = useMemo(() => new Map(steps.map((step) => [step.id, step])), [steps]);
  const selectById = (id) => {
    const step = stepsById.get(id);
    if (step) setActiveStep(step);
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-300 font-sans selection:bg-zinc-800">
      <header className="h-16 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur flex items-center justify-between px-6 sticky top-0 z-10">
        <div className="flex items-center gap-4 min-w-0">
          <button
            type="button"
            onClick={onReset}
            className="text-xs px-3 py-1.5 rounded-md border border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-white transition-colors"
          >
            ← Новый лог
          </button>
          <div className="text-sm font-mono bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-md text-zinc-400 shadow-sm truncate max-w-[280px]">
            {summary.file_name || 'log.jsonl'}
          </div>
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">{summary.log_format}</span>
          <span className="text-sm text-zinc-500">{formatDuration(summary.duration_seconds)}</span>
        </div>

        <div className="flex items-center gap-6 text-sm">
          <ProviderBadge provider={report.provider} isMock={report.provider_is_mock} />
          {summary.cost > 0 && (
            <div className="flex flex-col items-end">
              <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-0.5">Стоимость</span>
              <span className="font-mono text-2xl text-emerald-400 font-semibold">{formatCost(summary.cost)}</span>
            </div>
          )}
          <div className="flex flex-col items-end">
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-0.5">Токенов</span>
            <span className="font-mono text-2xl text-white font-semibold">{formatNumber(summary.tokens)}</span>
          </div>
        </div>
      </header>

      <main className="p-6 max-w-[1600px] mx-auto">
        {report.warnings?.length > 0 && (
          <div className="mb-6 px-4 py-3 rounded-lg border border-amber-900/50 bg-amber-950/20 text-xs text-amber-200/80">
            {report.warnings.slice(0, 3).map((warning, index) => (
              <p key={index}>{warning}</p>
            ))}
            {report.warnings.length > 3 && <p>… и ещё {report.warnings.length - 3}</p>}
          </div>
        )}

        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-7 flex flex-col gap-6">
            <MetricsGrid summary={summary} findings={findings} />
            <Timeline steps={steps} onSelect={setActiveStep} truncated={report.steps_truncated} />
            <StepTrace steps={steps} activeStep={activeStep} onSelect={setActiveStep} />
          </div>

          <div className="col-span-12 lg:col-span-5 flex flex-col gap-6">
            <FindingsPanel findings={findings} explanations={explanations} onSelectStep={selectById} />
            <AgentsMdPanel agentsMd={report.agents_md} />
            <StepInspector step={activeStep} />
          </div>
        </div>
      </main>
    </div>
  );
}
