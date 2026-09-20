import React from 'react';
import { ISSUE_LABELS, TONE_BADGE, formatNumber, formatTime, stepAction, stepLabel, stepTone } from '../../utils/format';

export default function StepTrace({ steps, activeStep, onSelect }) {
  return (
    <div className="border border-zinc-800 bg-zinc-900/30 rounded-xl overflow-hidden flex-1 shadow-sm">
      <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-900/80 flex items-center justify-between">
        <h2 className="text-sm font-medium text-white">Трассировка шагов</h2>
        <span className="text-xs text-zinc-500 font-mono">{steps.length}</span>
      </div>

      <div className="p-3 space-y-1.5 max-h-[520px] overflow-y-auto">
        {steps.map((step) => {
          const tone = stepTone(step);
          const isActive = activeStep?.id === step.id;
          return (
            <div
              key={step.id}
              onClick={() => onSelect(step)}
              className={`p-4 rounded-lg text-sm flex items-start gap-4 cursor-pointer transition-all border ${
                isActive
                  ? 'bg-zinc-800 border-zinc-700 shadow-md'
                  : 'bg-transparent border-transparent hover:bg-zinc-800/40'
              }`}
            >
              <span className="text-xs font-mono text-zinc-500 mt-0.5 font-medium whitespace-nowrap">
                #{step.id}
              </span>
              <span className="text-xs font-mono text-zinc-600 mt-0.5">{formatTime(step.timestamp)}</span>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded shadow-sm border ${TONE_BADGE[tone]}`}>
                    {stepLabel(step)}
                  </span>
                  {(step.issue_types || []).map((type) => (
                    <span
                      key={type}
                      className="text-[10px] px-2 py-0.5 rounded border border-zinc-700 bg-zinc-950 text-zinc-400"
                    >
                      {ISSUE_LABELS[type] || type}
                    </span>
                  ))}
                </div>
                <p className={`truncate ${isActive ? 'text-zinc-100 font-medium' : 'text-zinc-400'}`}>
                  {stepAction(step)}
                </p>
              </div>

              <span className="text-xs font-mono font-bold text-zinc-500 whitespace-nowrap">
                {step.tokens ? `${formatNumber(step.tokens)} tok` : ''}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
