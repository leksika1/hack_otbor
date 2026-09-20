import React, { useState } from 'react';

export default function AgentsMdPanel({ agentsMd }) {
  const [copied, setCopied] = useState(false);
  const text = agentsMd || '';

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
    link.download = 'AGENTS.md';
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
          Сгенерированный AGENTS.md
        </h2>
      </div>

      <div className="p-6">
        <p className="text-xs text-zinc-400 mb-5 leading-relaxed">
          Правила собраны из рекомендаций по найденным проблемам. Положите файл в корень проекта —
          агент прочитает его в следующей сессии.
        </p>

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
            Скачать .md
          </button>
        </div>
      </div>
    </div>
  );
}
