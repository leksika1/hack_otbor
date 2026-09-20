import { useRef } from 'react';

export default function UploadScreen({ onFileSelected, isLoading, error }) {
  const inputRef = useRef(null);

  const handleChange = (event) => {
    const file = event.target.files?.[0];
    if (file) onFileSelected(file);
    // allow re-selecting the same file after an error
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center p-6 text-zinc-300 font-sans">
      <div className="w-full max-w-md p-8 border border-zinc-800 bg-zinc-900/50 rounded-xl shadow-2xl flex flex-col items-center">
        <div className="w-12 h-12 mb-6 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center">
          {isLoading ? (
            <svg className="animate-spin h-6 w-6 text-emerald-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          ) : (
            <svg className="w-6 h-6 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 17v-6h13M9 17H5a2 2 0 01-2-2V5a2 2 0 012-2h4l2 2h6a2 2 0 012 2v2"
              />
            </svg>
          )}
        </div>

        <h1 className="text-xl font-medium text-white mb-2">Анализ сессии агента</h1>
        <p className="text-sm text-zinc-500 text-center mb-8">
          Загрузите .jsonl лог Claude Code или Codex — детерминированный анализ найдёт проблемы,
          LLM объяснит их и соберёт правила для AGENTS.md.
        </p>

        {error && (
          <div className="w-full mb-5 px-4 py-3 rounded-lg border border-red-900/60 bg-red-950/30 text-sm text-red-300">
            {error}
          </div>
        )}

        <label
          className={`w-full py-3 px-4 flex justify-center items-center text-white font-medium rounded-lg transition-colors cursor-pointer text-center shadow-md ${
            isLoading ? 'bg-emerald-800 cursor-wait' : 'bg-emerald-600 hover:bg-emerald-500'
          }`}
        >
          {isLoading ? 'Анализируем лог…' : 'Выбрать .jsonl файл'}
          <input
            ref={inputRef}
            type="file"
            accept=".jsonl,.json,.log,.txt"
            className="hidden"
            onChange={handleChange}
            disabled={isLoading}
          />
        </label>
      </div>
    </div>
  );
}
