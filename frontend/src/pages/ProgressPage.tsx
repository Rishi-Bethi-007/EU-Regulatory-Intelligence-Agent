import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getRunStatus, getAgentTasks } from '../lib/api'
import { ResearchRun, AgentTask } from '../lib/types'
import RiskBadge from '../components/RiskBadge'
import AgentPipeline from '../components/AgentPipeline'

const AGENT_PIPELINE = ['risk_classifier','planner','researcher','analyst','critic','synthesizer']

const AGENT_INFO: Record<string, { icon: string; label: string; desc: string }> = {
  risk_classifier: { icon: '🛡️', label: 'Risk Classifier',  desc: 'EU AI Act risk classification — fires before any agents' },
  planner:         { icon: '🗺️', label: 'Planner',          desc: 'Decomposes goal into subtasks and determines pipeline path' },
  researcher:      { icon: '🔍', label: 'Researcher',        desc: 'Searches Tavily + regulatory corpus in parallel' },
  analyst:         { icon: '⚖️', label: 'Analyst',           desc: 'Extracts EU AI Act and GDPR obligations from research' },
  critic:          { icon: '🧠', label: 'Critic',            desc: 'Verifies each obligation with confidence scoring' },
  synthesizer:     { icon: '✍️', label: 'Synthesizer',       desc: 'Writes the final compliance report' },
}

const STATUS_STYLES = {
  pending:   'text-gray-500 bg-gray-800',
  running:   'text-blue-400 bg-blue-950 border-blue-700',
  completed: 'text-green-400 bg-green-950 border-green-800',
  failed:    'text-red-400 bg-red-950 border-red-800',
}

const STATUS_LABEL = {
  pending:   '🟡 Pending',
  running:   '🔵 Running...',
  completed: '✅ Done',
  failed:    '❌ Failed',
}

function elapsedStr(task: AgentTask | undefined, status: string): string {
  if (!task || status === 'pending' || !task.started_at) return ''
  try {
    const start = new Date(task.started_at).getTime()
    if (status === 'completed' && task.completed_at) {
      const end = new Date(task.completed_at).getTime()
      return `⏱ ${Math.round((end - start) / 1000)}s`
    }
    if (status === 'running') {
      const secs = Math.round((Date.now() - start) / 1000)
      return `⏱ ${secs}s`
    }
  } catch {}
  return ''
}

export default function ProgressPage() {
  const { runId }  = useParams<{ runId: string }>()
  const navigate   = useNavigate()
  const [run,      setRun]      = useState<ResearchRun | null>(null)
  const [tasks,    setTasks]    = useState<AgentTask[]>([])
  const [complete, setComplete] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [tick, setTick] = useState(0)  // forces elapsed time re-render

  // Build deduplicated task map (handles retries)
  const taskMap: Record<string, AgentTask> = {}
  for (const t of tasks) {
    const existing = taskMap[t.agent_name]
    if (!existing || t.status === 'running' ||
        (t.started_at ?? '') > (existing.started_at ?? '')) {
      taskMap[t.agent_name] = t
    }
  }

  function inferRCStatus(): 'pending' | 'running' | 'completed' | 'failed' {
    if (run?.risk_level || taskMap['planner'] || run?.status === 'completed' || run?.status === 'failed')
      return 'completed'
    return 'running'
  }

  function isTrulyComplete() {
    return run?.status === 'completed' && taskMap['synthesizer']?.status === 'completed'
  }

  async function poll() {
    if (!runId) return
    try {
      const [status, agentsRes] = await Promise.all([getRunStatus(runId), getAgentTasks(runId)])
      setRun(status)
      setTasks(agentsRes.agents ?? [])
      if (status.status === 'completed' && agentsRes.agents?.find((t: AgentTask) => t.agent_name === 'synthesizer' && t.status === 'completed')) {
        setComplete(true)
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    } catch {}
  }

  useEffect(() => {
    poll()
    intervalRef.current = setInterval(poll, 2000)
    const tickInterval = setInterval(() => setTick(t => t + 1), 1000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      clearInterval(tickInterval)
    }
  }, [runId])

  const rcStatus = inferRCStatus()
  const completedCount = (rcStatus === 'completed' ? 1 : 0) +
    AGENT_PIPELINE.slice(1).filter(n => taskMap[n]?.status === 'completed').length
  const progress = Math.min(completedCount / AGENT_PIPELINE.length, 1)

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <h1 className="text-2xl font-bold text-white">⚡ Live Agent Progress</h1>
        {complete && (
          <span className="badge bg-green-900 text-green-300 border border-green-700">Complete</span>
        )}
      </div>

      {run && (
        <div className="text-xs text-gray-500 mb-1">Run ID: <span className="font-mono">{runId}</span></div>
      )}
      {run?.goal && (
        <p className="text-gray-300 mb-4 text-sm line-clamp-2">{run.goal}</p>
      )}

      {/* Risk badge */}
      {run?.risk_level && (
        <div className="mb-4">
          <RiskBadge level={run.risk_level} size="md" />
        </div>
      )}

      {/* Pipeline flow */}
      <div className="mb-4">
        <AgentPipeline taskMap={taskMap} rcStatus={rcStatus} />
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>{completedCount}/{AGENT_PIPELINE.length} stages complete</span>
          <span>{Math.round(progress * 100)}%</span>
        </div>
        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-600 rounded-full transition-all duration-500"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </div>

      {/* Agent cards */}
      <div className="space-y-3 mb-6">
        {AGENT_PIPELINE.map(name => {
          const task   = taskMap[name]
          const status = name === 'risk_classifier' ? rcStatus : (task?.status ?? 'pending')
          const info   = AGENT_INFO[name]
          const styles = STATUS_STYLES[status] ?? STATUS_STYLES.pending
          const elapsed = elapsedStr(task, status)

          return (
            <div key={name} className={`border rounded-xl p-4 transition-all ${styles}`}>
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <span className="text-xl mt-0.5">{info.icon}</span>
                  <div>
                    <div className="font-semibold text-sm">{info.label}</div>
                    <div className="text-xs opacity-60 mt-0.5">{info.desc}</div>
                  </div>
                </div>
                <div className="text-right shrink-0 ml-4">
                  <div className="text-xs font-medium">{STATUS_LABEL[status]}</div>
                  {elapsed && <div className="text-xs opacity-60 mt-0.5">{elapsed}</div>}
                </div>
              </div>
              {task?.status === 'failed' && task.error && (
                <div className="mt-2 text-xs text-red-300 bg-red-900/50 rounded p-2">{task.error}</div>
              )}
            </div>
          )
        })}
      </div>

      {/* Completion */}
      {complete && (
        <div className="card border-green-800 bg-green-950">
          <div className="text-green-400 font-semibold mb-3">✅ Research complete! Your compliance report is ready.</div>
          <div className="flex gap-3">
            <button className="btn-primary" onClick={() => navigate(`/reports/${runId}`)}>
              📋 View Report
            </button>
            <button className="btn-secondary" onClick={() => navigate(`/compliance/${runId}`)}>
              🇪🇺 Compliance View
            </button>
            <button className="btn-secondary" onClick={() => navigate('/')}>
              🆕 New Research
            </button>
          </div>
        </div>
      )}

      {run?.status === 'failed' && !complete && (
        <div className="card border-red-800 bg-red-950">
          <div className="text-red-400 font-semibold mb-2">❌ Research failed</div>
          {run.error && <p className="text-red-300 text-sm mb-3">{run.error}</p>}
          <button className="btn-secondary" onClick={() => navigate('/')}>← Try Again</button>
        </div>
      )}

      {!complete && run?.status !== 'failed' && (
        <p className="text-xs text-gray-500 text-center animate-pulse">🔄 Auto-refreshing every 2s...</p>
      )}
    </div>
  )
}
