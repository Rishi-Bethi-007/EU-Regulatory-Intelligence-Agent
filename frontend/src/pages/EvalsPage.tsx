import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { supabase } from '../lib/supabase'
import { ResearchRun } from '../lib/types'
import MetricCard from '../components/MetricCard'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'

interface RagasEvalScore {
  id: string; experiment: string; chunker: string; retriever: string
  pairs_evaluated: number; faithfulness: number | null; answer_relevancy: number | null
  context_precision: number | null; passed_target: boolean; metadata: Record<string, unknown> | null
  evaluated_at: string; created_at: string
}

export default function EvalsPage() {
  const { user } = useAuth()
  const [runs,    setRuns]    = useState<ResearchRun[]>([])
  const [evals,   setEvals]   = useState<RagasEvalScore[]>([])
  const [tab,     setTab]     = useState<'ragas'|'cost'|'transparency'|'history'>('ragas')
  const [loading, setLoading] = useState(true)

  useEffect(() => { Promise.all([fetchRuns(), fetchEvals()]).finally(() => setLoading(false)) }, [user])

  async function fetchRuns() {
    if (!user) return
    const { data } = await supabase.from('research_runs')
      .select('id,goal,status,risk_level,transparency_score,token_count,cost_usd,duration_ms,created_at')
      .eq('status', 'completed').eq('user_id', user.id)
      .order('created_at', { ascending: false }).limit(30)
    setRuns((data ?? []) as ResearchRun[])
  }

  async function fetchEvals() {
    const { data, error } = await supabase.from('ragas_eval_scores').select('*').order('created_at', { ascending: true })
    if (error) { console.warn('[EvalsPage] ragas_eval_scores error:', error.message); setEvals([]); return }
    setEvals(data ?? [])
  }

  const n        = runs.length
  const avgCost  = n ? runs.reduce((s, r) => s + Number(r.cost_usd ?? 0), 0) / n : 0
  const avgLat   = n ? runs.reduce((s, r) => s + Number(r.duration_ms ?? 0), 0) / n / 1000 : 0
  const avgTok   = n ? runs.reduce((s, r) => s + Number(r.token_count ?? 0), 0) / n : 0
  const scored   = runs.filter(r => (r.transparency_score ?? 0) > 0)
  const avgScore = scored.length ? scored.reduce((s, r) => s + (r.transparency_score ?? 0), 0) / scored.length : 0

  const riskCounts = runs.reduce((acc, r) => {
    const k = r.risk_level ?? 'UNKNOWN'; acc[k] = (acc[k] ?? 0) + 1; return acc
  }, {} as Record<string, number>)

  const RISK_EMOJI: Record<string, string> = { UNACCEPTABLE: '🚫', HIGH_RISK: '🔴', LIMITED_RISK: '🟡', MINIMAL_RISK: '🟢', UNKNOWN: '⚪' }
  const TABS = [
    { key: 'ragas',        label: '🧪 RAGAS Scores' },
    { key: 'cost',         label: '💰 Cost & Latency' },
    { key: 'transparency', label: '🔍 Transparency' },
    { key: 'history',      label: '📋 Run History' },
  ]

  const recentRuns = [...runs].reverse().slice(-15)
  const costData   = recentRuns.map(r => ({ name: (r.goal ?? '').slice(0, 15) + '…', cost: Number(r.cost_usd ?? 0) }))
  const latData    = recentRuns.map(r => ({ name: (r.goal ?? '').slice(0, 15) + '…', latency: Number(r.duration_ms ?? 0) / 1000 }))
  const scoreData  = [...scored].reverse().slice(-15).map(r => ({ name: (r.goal ?? '').slice(0, 15) + '…', score: r.transparency_score ?? 0 }))
  const ragasChartData = evals.map(e => ({
    date: (e.evaluated_at ?? e.created_at)?.slice(0, 10) ?? '?',
    faithfulness:      e.faithfulness      != null ? Number(e.faithfulness.toFixed(3))      : null,
    answer_relevancy:  e.answer_relevancy  != null ? Number(e.answer_relevancy.toFixed(3))  : null,
    context_precision: e.context_precision != null ? Number(e.context_precision.toFixed(3)) : null,
  }))
  const latestEval = evals.length > 0 ? evals[evals.length - 1] : null

  const chartTooltipStyle = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, color: '#111827' }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">📊 Evaluation Dashboard</h1>
      <p className="text-gray-500 text-sm mb-6">RAGAS scores · Cost & latency · Transparency scoring · Run history</p>

      {!loading && (
        <div className="grid grid-cols-5 gap-4 mb-8">
          <MetricCard label="Total Runs"       value={n} />
          <MetricCard label="Avg Cost"         value={`$${avgCost.toFixed(4)}`} />
          <MetricCard label="Avg Latency"      value={`${avgLat.toFixed(1)}s`} />
          <MetricCard label="Avg Tokens"       value={Math.round(avgTok).toLocaleString()} />
          <MetricCard label="Avg Transparency" value={`${avgScore.toFixed(0)}/100`} />
        </div>
      )}

      {Object.keys(riskCounts).length > 0 && (
        <div className="card mb-6">
          <div className="text-sm text-gray-500 mb-3 font-medium">Risk level distribution</div>
          <div className="flex flex-wrap gap-3">
            {Object.entries(riskCounts).map(([k, v]) => (
              <div key={k} className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-center min-w-[80px]">
                <div className="text-lg">{RISK_EMOJI[k] ?? '⚪'}</div>
                <div className="text-xs text-gray-500 mt-0.5">{k.replace('_', ' ')}</div>
                <div className="text-lg font-bold text-gray-900">{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key as any)}
            className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
              tab === t.key ? 'bg-white text-gray-900 shadow-sm border border-gray-200' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'ragas' && (
        evals.length === 0 ? (
          <div className="card">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <h3 className="text-gray-900 font-semibold mb-3">What is RAGAS?</h3>
                <p className="text-sm text-gray-500 mb-4">RAGAS (Retrieval Augmented Generation Assessment) measures RAG quality across 3 dimensions:</p>
                <table className="text-sm w-full">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-200">
                      <th className="text-left pb-2">Metric</th>
                      <th className="text-left pb-2">What it measures</th>
                      <th className="text-left pb-2">Target</th>
                    </tr>
                  </thead>
                  <tbody className="text-gray-600">
                    {[
                      ['Faithfulness',      'Are answer statements supported by retrieved chunks?', '> 0.75'],
                      ['Answer Relevancy',  'Does the answer actually address the question?',       '> 0.70'],
                      ['Context Precision', 'Are retrieved chunks relevant to the question?',       '> 0.70'],
                    ].map(([k, v, t]) => (
                      <tr key={k} className="border-b border-gray-100">
                        <td className="py-2 font-medium text-gray-900">{k}</td>
                        <td className="py-2">{v}</td>
                        <td className="py-2 text-green-600 font-mono text-xs">{t}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h3 className="text-gray-900 font-semibold mb-3">How to run the baseline</h3>
                <code className="block bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm text-blue-700 font-mono mb-3">
                  uv run python scripts/run_ragas_baseline.py
                </code>
                <p className="text-sm text-gray-500">
                  Evaluates 20 Q&A pairs across EN/SV/DE languages. Uses Claude Haiku as judge.
                  Writes scores to <code className="text-blue-600">ragas_eval_scores</code> table. Takes ~5 minutes.
                </p>
                <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">
                  <div className="font-medium mb-1">⚡ Run this first:</div>
                  <div>1. <code className="text-blue-700">uv run python scripts/ingest_demo_corpus.py</code></div>
                  <div>2. <code className="text-blue-700">uv run python scripts/migrate_fts_multilingual.py</code></div>
                  <div>3. <code className="text-blue-700">uv run python scripts/run_ragas_baseline.py</code></div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {latestEval && (
              <div className="grid grid-cols-3 gap-4">
                {[
                  { label: 'Faithfulness',      val: latestEval.faithfulness,      target: 0.75 },
                  { label: 'Answer Relevancy',  val: latestEval.answer_relevancy,  target: 0.70 },
                  { label: 'Context Precision', val: latestEval.context_precision, target: 0.70 },
                ].map(({ label, val, target }) => (
                  <div key={label} className="card text-center">
                    <div className="text-xs text-gray-500 mb-1">{label}</div>
                    <div className={`text-3xl font-bold ${(val ?? 0) >= target ? 'text-green-600' : 'text-amber-600'}`}>
                      {val != null ? val.toFixed(2) : 'N/A'}
                    </div>
                    <div className="text-xs text-gray-400 mt-1">target ≥ {target}</div>
                    <div className="text-xs mt-1">{(val ?? 0) >= target ? '✅ Pass' : '⚠️ Below target'}</div>
                  </div>
                ))}
              </div>
            )}
            {ragasChartData.length > 1 && (
              <div className="card">
                <h3 className="text-sm font-medium text-gray-500 mb-1">Score trend across evaluation runs</h3>
                <p className="text-xs text-gray-400 mb-3">Run baseline after each corpus or pipeline change to track improvements</p>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={ragasChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                    <XAxis dataKey="date" stroke="#9ca3af" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 1]} stroke="#9ca3af" tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={chartTooltipStyle} />
                    <ReferenceLine y={0.75} stroke="#16a34a" strokeDasharray="4 4" label={{ value: 'target', fill: '#16a34a', fontSize: 10 }} />
                    <Line type="monotone" dataKey="faithfulness"      stroke="#3b82f6" strokeWidth={2} dot name="Faithfulness" />
                    <Line type="monotone" dataKey="answer_relevancy"  stroke="#8b5cf6" strokeWidth={2} dot name="Answer Relevancy" />
                    <Line type="monotone" dataKey="context_precision" stroke="#10b981" strokeWidth={2} dot name="Context Precision" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="card">
              <h3 className="text-sm font-medium text-gray-500 mb-3">Evaluation run history</h3>
              <div className="space-y-2">
                {[...evals].reverse().map(e => (
                  <div key={e.id} className="flex items-center gap-4 py-2 border-b border-gray-100 last:border-0 text-xs">
                    <span className="text-lg">{e.passed_target ? '✅' : '⚠️'}</span>
                    <span className="flex-1 text-gray-600 truncate font-mono">{e.experiment}</span>
                    <span className="text-blue-600">F: {e.faithfulness?.toFixed(3) ?? 'N/A'}</span>
                    <span className="text-purple-600">AR: {e.answer_relevancy?.toFixed(3) ?? 'N/A'}</span>
                    <span className="text-green-600">CP: {e.context_precision?.toFixed(3) ?? 'N/A'}</span>
                    <span className="text-gray-400">{e.pairs_evaluated} pairs</span>
                    <span className="text-gray-300">{(e.evaluated_at ?? e.created_at)?.slice(0, 10)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )
      )}

      {tab === 'cost' && (
        <div className="grid grid-cols-2 gap-4">
          <div className="card">
            <h3 className="text-sm font-medium text-gray-500 mb-3">Cost per run (USD)</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={costData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <YAxis stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={chartTooltipStyle} />
                <Bar dataKey="cost" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <h3 className="text-sm font-medium text-gray-500 mb-3">Latency per run (seconds)</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={latData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <YAxis stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={chartTooltipStyle} />
                <Bar dataKey="latency" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {tab === 'transparency' && (
        scored.length === 0 ? (
          <div className="card text-center text-gray-400">No scored runs yet. Run a research query to see transparency scores.</div>
        ) : (
          <div className="card">
            <h3 className="text-sm font-medium text-gray-500 mb-3">Transparency score over time (target: ≥80/100)</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={scoreData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={chartTooltipStyle} />
                <ReferenceLine y={80} stroke="#16a34a" strokeDasharray="4 4" label={{ value: 'target 80', fill: '#16a34a', fontSize: 10 }} />
                <Bar dataKey="score" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )
      )}

      {tab === 'history' && (
        <div className="card">
          <div className="space-y-2">
            {runs.map(r => {
              const goal = (r.goal ?? '')
              if (goal.startsWith('[ERASED')) return null
              return (
                <div key={r.id} className="flex items-center gap-4 py-2 border-b border-gray-100 last:border-0 text-xs">
                  <span className="text-lg shrink-0">{RISK_EMOJI[r.risk_level ?? ''] ?? '⚪'}</span>
                  <span className="flex-1 text-gray-600 truncate">{goal.slice(0, 60)}...</span>
                  <span className="text-gray-400 shrink-0">📊 {r.transparency_score ?? 0}/100</span>
                  <span className="text-gray-400 shrink-0">💰 ${Number(r.cost_usd ?? 0).toFixed(4)}</span>
                  <span className="text-gray-400 shrink-0">⏱ {(Number(r.duration_ms ?? 0) / 1000).toFixed(1)}s</span>
                  <span className="text-gray-300 shrink-0">{r.created_at?.slice(0, 10)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
