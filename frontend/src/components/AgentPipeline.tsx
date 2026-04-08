import { AgentTask } from '../lib/types'

const PIPELINE = [
  { key: 'risk_classifier', icon: '🛡️', label: 'Risk Classifier' },
  { key: 'planner',         icon: '🗺️', label: 'Planner'         },
  { key: 'researcher',      icon: '🔍', label: 'Researcher'      },
  { key: 'analyst',         icon: '⚖️', label: 'Analyst'         },
  { key: 'critic',          icon: '🧠', label: 'Critic'          },
  { key: 'synthesizer',     icon: '✍️', label: 'Synthesizer'     },
]

const STATUS_STYLES = {
  pending:   { ring: 'border-gray-300',  bg: 'bg-white',     text: 'text-gray-700'  },
  running:   { ring: 'border-blue-500',  bg: 'bg-blue-950',  text: 'text-blue-400'  },
  completed: { ring: 'border-green-600', bg: 'bg-green-950', text: 'text-green-400' },
  failed:    { ring: 'border-red-700',   bg: 'bg-red-950',   text: 'text-red-400'   },
}

interface Props {
  taskMap:   Record<string, AgentTask>
  rcStatus:  'pending' | 'running' | 'completed' | 'failed'
}

export default function AgentPipeline({ taskMap, rcStatus }: Props) {
  function getStatus(key: string) {
    if (key === 'risk_classifier') return rcStatus
    return taskMap[key]?.status ?? 'pending'
  }

  return (
    <div className="flex items-center gap-1 flex-wrap bg-gray-50 border border-gray-200 rounded-xl p-4">
      {PIPELINE.map(({ key, icon, label }, i) => {
        const status = getStatus(key)
        const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending
        const isRunning = status === 'running'

        return (
          <div key={key} className="flex items-center gap-1">
            <div
              className={`flex flex-col items-center justify-center rounded-lg border
                         px-3 py-2 min-w-[72px] text-center transition-all
                         ${s.bg} ${s.ring} ${s.text}
                         ${isRunning ? 'animate-pulse shadow-lg shadow-blue-500/20' : ''}`}
            >
              <span className="text-lg leading-none">{icon}</span>
              <span className="text-[10px] font-medium mt-1 leading-tight">{label}</span>
            </div>
            {i < PIPELINE.length - 1 && (
              <span className="text-gray-500 text-sm">→</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
