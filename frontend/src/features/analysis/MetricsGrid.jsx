import { formatNumber } from '../../utils/format';

export default function MetricsGrid({ summary, findings }) {
  const high = findings.filter((finding) => finding.severity === 'high').length;
  const repeats = findings.filter(
    (finding) => finding.type === 'repeated_tool_call' || finding.type === 'retry',
  ).length;
  const interventions = findings.filter((finding) => finding.type === 'human_intervention').length;

  const metrics = [
    { label: 'Шаги', value: formatNumber(summary.steps), status: 'ok' },
    {
      label: 'Проблемы',
      value: formatNumber(summary.issues_total),
      status: high ? 'critical' : summary.issues_total ? 'warning' : 'ok',
    },
    { label: 'Повторы', value: formatNumber(repeats), status: repeats ? 'warning' : 'ok' },
    {
      label: 'Вмешательства',
      value: formatNumber(interventions),
      status: interventions ? 'warning' : 'ok',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="p-5 border border-zinc-800 bg-zinc-900/40 rounded-xl flex flex-col justify-center items-start shadow-sm"
        >
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">{metric.label}</span>
          <span
            className={`text-4xl font-bold tracking-tight ${
              metric.status === 'critical'
                ? 'text-red-400'
                : metric.status === 'warning'
                  ? 'text-amber-400'
                  : 'text-white'
            }`}
          >
            {metric.value}
          </span>
        </div>
      ))}
    </div>
  );
}
