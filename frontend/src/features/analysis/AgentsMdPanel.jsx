import { useState } from 'react';

export default function AgentsMdPanel({ agentsMd, artifacts }) {
  const [copied, setCopied] = useState(false);
  const [active, setActive] = useState(0);
  // Older API responses carry only agents_md; treat it as a single file.
  const files = artifacts?.length
    ? artifacts
    : [{ path: 'AGENTS.md', description: 'Правила для агента.', content: agentsMd || '' }];
  const file = files[Math.min(active, files.length - 1)];
  const text = file.content || '';

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const download = () => {
    const blob = new Blob([text], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = file.path.split('/').pop();
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="border border-emerald-900/40 bg-emerald-950/20 rounded-xl overflow-hidden shadow-lg">
      <div className="px-6 py-4 border-b border-emerald-900/40 flex items-center justify-between bg-emerald-900/10">
        <h2 className="text-sm font-medium text-emerald-400 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          Готовые файлы для следующей сессии
        </h2>
      </div>

      <div className="p-6">
        <div className="flex flex-wrap gap-1.5 mb-4">
          {files.map((item, index) => (
            <button
              key={item.path}
              type="button"
              onClick={() => setActive(index)}
              className={`text-[11px] font-mono px-2 py-1 rounded border transition-colors ${
                index === active
                  ? 'border-emerald-600 text-emerald-300 bg-emerald-900/30'
                  : 'border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500'
              }`}
            >
              {item.path}
            </button>
          ))}
        </div>

        <p className="text-xs text-zinc-400 mb-4 leading-relaxed">{file.description}</p>

        <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950 p-4 rounded-lg border border-zinc-800/80 whitespace-pre-wrap leading-relaxed shadow-inner mb-5 max-h-64 overflow-y-auto">
          {text || 'Правила не сгенерированы.'}
        </pre>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={copy}
            disabled={!text}
            className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 text-white text-xs font-medium rounded transition-colors border border-zinc-700"
          >
            {copied ? 'Скопировано' : 'Копировать'}
          </button>
          <button
            type="button"
            onClick={download}
            disabled={!text}
            className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-medium rounded transition-colors shadow-md"
          >
            Скачать файл
          </button>
        </div>
      </div>
    </div>
  );
}
