// Presentation helpers. The backend sends raw numbers; formatting lives here.

export function formatDuration(seconds) {
  const value = Number(seconds) || 0;
  if (value <= 0) return 'n/a';
  if (value < 60) return `${Math.round(value)} с`;
  if (value < 3600) return `${Math.floor(value / 60)} мин ${String(Math.round(value % 60)).padStart(2, '0')} с`;
  return `${Math.floor(value / 3600)} ч ${String(Math.floor((value % 3600) / 60)).padStart(2, '0')} мин`;
}

export function formatNumber(value) {
  return new Intl.NumberFormat('ru-RU').format(Number(value) || 0);
}

export function formatCost(value) {
  const amount = Number(value) || 0;
  return amount > 0 ? `$${amount.toFixed(2)}` : '—';
}

export function formatTime(timestamp) {
  if (!timestamp) return '--:--:--';
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? '--:--:--' : date.toISOString().slice(11, 19);
}

const ISSUE_TONE = {
  repeated_tool_call: 'loop',
  retry: 'loop',
  tool_failure: 'error',
  session_error: 'error',
  human_intervention: 'human',
  token_hotspot: 'tokens',
  idle_period: 'idle',
  reverted_edit: 'revert',
};

export const ISSUE_LABELS = {
  repeated_tool_call: 'повтор вызова',
  retry: 'повторная попытка',
  tool_failure: 'ошибка инструмента',
  session_error: 'ошибка сессии',
  human_intervention: 'вмешательство человека',
  token_hotspot: 'всплеск токенов',
  idle_period: 'простой',
  reverted_edit: 'откат правки',
};

// A step is coloured by the most important finding attached to it by the
// analyzer; only then by its own status.
export function stepTone(step) {
  for (const type of step.issue_types || []) {
    if (ISSUE_TONE[type]) return ISSUE_TONE[type];
  }
  if (step.status === 'error') return 'error';
  if (step.actor === 'user') return 'human';
  if (step.status === 'success') return 'success';
  return 'default';
}

export const TONE_BADGE = {
  error: 'text-red-500 bg-red-500/10 border-red-500/20',
  loop: 'text-red-400 bg-red-400/10 border-red-400/20',
  human: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  tokens: 'text-violet-400 bg-violet-400/10 border-violet-400/20',
  idle: 'text-sky-400 bg-sky-400/10 border-sky-400/20',
  revert: 'text-orange-400 bg-orange-400/10 border-orange-400/20',
  success: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  default: 'text-zinc-400 bg-zinc-800 border-zinc-700',
};

export const TONE_BAR = {
  error: 'bg-red-500',
  loop: 'bg-red-600',
  human: 'bg-amber-500',
  tokens: 'bg-violet-500',
  idle: 'bg-sky-500',
  revert: 'bg-orange-500',
  success: 'bg-emerald-500/80',
  default: 'bg-zinc-600',
};

export const SEVERITY_BADGE = {
  high: 'text-red-400 bg-red-500/10 border-red-500/30',
  medium: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  low: 'text-zinc-400 bg-zinc-800 border-zinc-700',
};

export function stepLabel(step) {
  if (step.tool_name && step.event_type === 'tool_result') return `${step.tool_name} → результат`;
  if (step.tool_name) return step.tool_name;
  if (step.actor === 'user') return 'сообщение пользователя';
  return step.event_type || 'шаг';
}

export function stepAction(step) {
  if (step.text) return step.text;
  if (step.tool_name) return `${step.tool_name}()`;
  return step.event_type || '';
}
