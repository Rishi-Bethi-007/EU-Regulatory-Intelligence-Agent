import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { supabase } from '../lib/supabase'
import { startResearch } from '../lib/api'
import { ResearchRun } from '../lib/types'
import RiskBadge from '../components/RiskBadge'

const EXAMPLES = [
  'A Swedish HR startup is building a CV screening AI. What are their EU AI Act obligations?',
  'What GDPR obligations apply to a German fintech processing credit scores?',
  'What is the difference between a provider and deployer under the EU AI Act?',
  'As a Swedish SME using biometric attendance tracking, what are my obligations?',
]

export default function HomePage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [goal, setGoal]       = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [recentRuns, setRecentRuns] = useState<ResearchRun[]>([])

  useEffect(() => {
    fetchRecentRuns()
  }, [user])

  async function fetchRecentRuns() {
    if (!user) return
    const { data } = await supabase
      .from('research_runs')
      .select('id, goal, status, risk_level, transparency_score, token_count, cost_usd, created_at')
      .eq('status', 'completed')
      .eq('user_id', user.id)
      .not('goal', 'like', '[ERASED%]')
      .order('created_at', { ascending: false })
      .limit(8)
    setRecentRuns(data ?? [])
  }

  async function handleRun() {
    if (!goal.trim()) { setError('Please enter a research goal.'); return }
    if (!user) return
    setError(''); setLoading(true)
    try {
      const { run_id } = await startResearch(goal.trim(), user.id)
      navigate(`/progress/${run_id}`)
    } catch (e: any) {
      setError(e.message ?? 'Failed to start research.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">🇪🇺 EU Regulatory Intelligence Agent</h1>
        <p className="text-gray-400">Multi-agent EU AI Act and GDPR compliance research for Swedish and German SMEs</p>
      </div>

      {/* Research input */}
      <div className="card mb-8">
        <h2 className="text-lg font-semibold text-white mb-4">New Research Query</h2>
        <p className="text-sm text-gray-400 mb-4">
          Ask anything about EU AI Act or GDPR compliance. The system classifies risk,
          researches obligations across the regulatory corpus, and generates a full compliance report.
        </p>

        <textarea
          className="input resize-none mb-3"
          rows={4}
          placeholder="e.g. A Swedish SME is deploying an AI hiring tool. What are their EU AI Act and GDPR obligations?"
          value={goal}
          onChange={e => setGoal(e.target.value)}
        />

        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

        <div className="flex items-center gap-4">
          <button onClick={handleRun} disabled={loading} className="btn-primary px-8">
            {loading ? 'Starting...' : '🚀 Run Research'}
          </button>
          <span className="text-xs text-gray-500">Takes 3–6 minutes</span>
        </div>

        {/* Example queries */}
        <div className="mt-4">
          <p className="text-xs text-gray-500 mb-2">💡 Example queries:</p>
          <div className="space-y-1">
            {EXAMPLES.map(ex => (
              <button key={ex} onClick={() => setGoal(ex)}
                className="block w-full text-left text-xs text-gray-400 hover:text-blue-400
                           hover:bg-gray-800 px-2 py-1.5 rounded transition-colors">
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Recent runs */}
      {recentRuns.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Recent Runs</h2>
          <div className="space-y-3">
            {recentRuns.map(run => (
              <div key={run.id}
                className="card hover:border-gray-700 cursor-pointer transition-colors"
                onClick={() => navigate(`/reports/${run.id}`)}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-200 truncate">{run.goal}</p>
                    <div className="flex items-center gap-3 mt-2">
                      <RiskBadge level={run.risk_level} size="sm" />
                      {run.transparency_score != null && (
                        <span className="text-xs text-gray-500">📊 {run.transparency_score}/100</span>
                      )}
                      {run.token_count && (
                        <span className="text-xs text-gray-500">
                          ~{Math.max(1, run.token_count / 800)}m read
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right text-xs text-gray-500 shrink-0">
                    <div>{run.created_at?.slice(0, 10)}</div>
                    {run.cost_usd && <div>${Number(run.cost_usd).toFixed(4)}</div>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
