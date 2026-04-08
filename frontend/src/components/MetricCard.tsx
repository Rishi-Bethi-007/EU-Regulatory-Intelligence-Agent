interface Props {
  label: string
  value: string | number
  sub?: string
  color?: string
}

export default function MetricCard({ label, value, sub, color }: Props) {
  return (
    <div className="metric-card">
      <div className="text-xs text-gray-600 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color ?? 'text-gray-900'}`}>{value}</div>
      {sub && <div className="text-xs text-gray-600 mt-0.5">{sub}</div>}
    </div>
  )
}
