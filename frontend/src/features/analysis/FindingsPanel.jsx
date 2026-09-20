import { ISSUE_LABELS, SEVERITY_BADGE } from '../../utils/format';

const FIX_KIND_LABELS = {
  instruction: 'правило в CLAUDE.md',
  skill: 'скилл',
  tool: 'инструмент / MCP',
  hook: 'хук',
  settings: 'настройки',
};

function StepLinks({ steps, onSelectStep }) {
  if (!steps?.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {steps.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => onSelectStep(id)}
          className="text-[11px] font-mono px-2 py-0.5 rounded border border-zinc-700 bg-zinc-950 text-zinc-400 hover:text-white hover:border-zinc-500 transition-colors"
        >
          шаг {id}
        </button>
      ))}
    </div>
  );
}

export default function FindingsPanel({ findings, explanations, onSelectStep }) {
  const explained = new Map(explanations.map((item) => [`${item.issue_type}:${item.steps.join(',')}`, item]));
  const rest = findings.filter((finding) => !explained.has(`${finding.type}:${finding.steps.join(',')}`));

  return (
    <div className="border border-zinc-800 bg-zinc-900/30 rounded-xl overflow-hidden shadow-sm">
      <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-900/80 flex items-center justify-between">
        <h2 className="text-sm font-medium text-white">Найденные проблемы</h2>
        <span className="text-xs text-zinc-500 font-mono">{findings.length}</span>
      </div>

      <div className="p-4 space-y-4">
        {explanations.map((item) => (
          <article
            key={`${item.issue_type}-${item.steps.join('-')}`}
            className="p-5 rounded-lg border border-zinc-800 bg-zinc-950/60"
          >
            <header className="flex items-center gap-3 flex-wrap mb-3">
              <span
                className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${
                  SEVERITY_BADGE[item.severity] || SEVERITY_BADGE.low
                }`}
              >
                {item.severity}
              </span>
              <h3 className="text-sm font-medium text-white">{item.title}</h3>
              <span className="text-[11px] text-zinc-500 font-mono">
                {ISSUE_LABELS[item.issue_type] || item.issue_type}
              </span>
            </header>

            <p className="text-sm text-zinc-300 leading-relaxed mb-3">{item.explanation}</p>

            <div className="text-xs text-zinc-400 leading-relaxed space-y-2">
              {item.cause && (
                <p>
                  <span className="text-amber-500/80 uppercase font-bold tracking-wider mr-2">Почему так вышло</span>
                  {item.cause}
                </p>
              )}
              <p>
                <span className="text-zinc-500 uppercase font-bold tracking-wider mr-2">Чего это стоило</span>
                {item.impact}
              </p>
              <p>
                <span className="text-emerald-500/80 uppercase font-bold tracking-wider mr-2">Что сделать</span>
                {item.fix_kind && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 mr-2 rounded border border-emerald-800/60 text-emerald-400 bg-emerald-950/40">
                    {FIX_KIND_LABELS[item.fix_kind] || item.fix_kind}
                  </span>
                )}
                {item.recommendation}
              </p>
              <p className="font-mono text-[11px] text-zinc-400 bg-zinc-900 border border-zinc-800 rounded p-3">
                {item.agent_rule}
              </p>
            </div>

            <StepLinks steps={item.steps} onSelectStep={onSelectStep} />
          </article>
        ))}

        {rest.length > 0 && (
          <div className="pt-2">
            <h3 className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 mb-3 px-1">
              Остальные находки (без объяснения LLM)
            </h3>
            <ul className="space-y-2">
              {rest.map((finding, index) => (
                <li
                  key={`${finding.type}-${finding.steps.join('-')}-${index}`}
                  className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-950/40"
                >
                  <div className="flex items-center gap-3 flex-wrap">
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${
                        SEVERITY_BADGE[finding.severity] || SEVERITY_BADGE.low
                      }`}
                    >
                      {finding.severity}
                    </span>
                    <span className="text-xs text-zinc-300">
                      {ISSUE_LABELS[finding.type] || finding.type}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1.5">{finding.message}</p>
                  <StepLinks steps={finding.steps} onSelectStep={onSelectStep} />
                </li>
              ))}
            </ul>
          </div>
        )}

        {findings.length === 0 && (
          <p className="text-sm text-zinc-500 px-1 py-6 text-center">
            Детерминированные анализаторы не нашли проблем в этой сессии.
          </p>
        )}
      </div>
    </div>
  );
}
