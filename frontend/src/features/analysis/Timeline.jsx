import React from 'react';
import { TONE_BAR, stepAction, stepTone } from '../../utils/format';

export default function Timeline({ steps, onSelect, truncated }) {
  const width = `${100 / Math.max(steps.length, 1)}%`;

  return (
    <div className="p-6 border border-zinc-800 bg-zinc-900/30 rounded-xl shadow-sm">
      <h2 className="text-sm font-medium text-white mb-5 flex items-center gap-2">
        <svg className="w-4 h-4 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
          />
        </svg>
        Карта сессии
      </h2>

      <div className="flex h-10 w-full gap-[2px] p-1 bg-zinc-950 rounded-lg border border-zinc-800/80">
        {steps.map((step) => (
          <button
            key={step.id}
            type="button"
            onClick={() => onSelect(step)}
            style={{ width }}
            title={`#${step.id} ${stepAction(step)}`}
            className={`h-full rounded-[3px] transition-all hover:brightness-150 hover:-translate-y-0.5 shadow-sm ${TONE_BAR[stepTone(step)]}`}
          />
        ))}
      </div>

      <div className="flex justify-between mt-3 text-[10px] text-zinc-500 font-mono uppercase font-bold tracking-widest">
        <span>Старт</span>
        <span>{truncated ? 'показаны первые шаги' : 'Конец сессии'}</span>
      </div>
    </div>
  );
}
