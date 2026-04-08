import { RiskLevel, RISK_CONFIG } from '../lib/types'

interface Props {
  level: RiskLevel | null | undefined
  size?: 'sm' | 'md' | 'lg'
}

export default function RiskBadge({ level, size = 'md' }: Props) {
  if (!level) return (
    <span className="badge bg-gray-100 text-gray-700 border border-gray-200">⚪ Not classified</span>
  )

  const cfg = RISK_CONFIG[level]
  const sizes = { sm: 'text-xs px-2 py-0.5', md: 'text-sm px-3 py-1', lg: 'text-base px-4 py-2' }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-lg font-semibold ${sizes[size]}`}
      style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}40` }}
    >
      {cfg.emoji} {cfg.label}
    </span>
  )
}
