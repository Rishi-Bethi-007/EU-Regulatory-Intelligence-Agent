interface Props {
  label: string
  value: string | number
  sub?: string
  color?: string
}

export default function MetricCard({ label, value, sub, color }: Props) {
  return (
    <div className="metric-card">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color ?? 'text-white'}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}
