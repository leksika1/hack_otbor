import { ISSUE_LABELS, formatNumber, formatTime, stepAction, stepLabel } from '../../utils/format';

export default function StepInspector({ step }) {
  return (
    <div className="border border-zinc-800 bg-zinc-900/30 rounded-xl overflow-hidden min-h-[300px] shadow-sm">
      <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-900/80">
        <h2 className="text-sm font-medium text-white">Инспектор шага</h2>
      </div>

      <div className="p-6">
        {step ? (
          <div className="space-y-5">
            <div>
              <span className="block text-[10px] text-zinc-500 uppercase font-bold tracking-wider mb-1.5">
                Шаг #{step.id} · строка {step.line} · {formatTime(step.timestamp)}
              </span>
              <span className="text-sm text-zinc-200 font-medium break-words">{stepAction(step)}</span>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="inline-flex items-center px-2.5 py-1 rounded bg-zinc-800/80 text-zinc-300 text-xs border border-zinc-700">
                  {stepLabel(step)}
                </span>
                {(step.issue_types || []).map((type) => (
                  <span
                    key={type}
                    className="inline-flex items-center px-2.5 py-1 rounded bg-zinc-800/80 text-amber-300/90 text-xs font-medium border border-zinc-700"
                  >
                    {ISSUE_LABELS[type] || type}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <span className="block text-[10px] text-zinc-500 uppercase font-bold tracking-wider mb-1.5">
                Исходное событие
              </span>
              <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 text-xs font-mono text-zinc-400 leading-relaxed break-words shadow-inner overflow-y-auto max-h-48">
                {step.details || '—'}
              </div>
            </div>

            <div className="pt-5 border-t border-zinc-800/80 flex gap-8">
              <div>
                <span className="block text-[10px] text-zinc-500 uppercase font-bold tracking-wider mb-1.5">Токены</span>
                <p className="text-sm font-mono text-zinc-300">{formatNumber(step.tokens)}</p>
              </div>
              <div>
                <span className="block text-[10px] text-zinc-500 uppercase font-bold tracking-wider mb-1.5">Статус</span>
                <p className="text-sm font-mono text-zinc-300">{step.status}</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center pt-12 opacity-60">
            <svg className="w-12 h-12 text-zinc-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1}
                d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"
              />
            </svg>
            <span className="text-zinc-400 text-sm">
              Выберите шаг на таймлайне или в трассировке,
              <br />
              чтобы увидеть исходное событие.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
