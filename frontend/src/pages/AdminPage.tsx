import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../hooks/useAuth'

interface UserRun {
  id: string; goal: string; status: string
  risk_level: string | null; token_count: number | null
  cost_usd: number | null; duration_ms: number | null
  created_at: string; user_id: string | null
}
interface AuditEvent {
  id: string; event_type: string
  payload: Record<string, unknown>
  event_hash: string; created_at: string
}
interface SystemStats {
  total_runs: number; total_users: number
  total_chunks: number; total_cost: number; avg_latency: number
}

const RISK_EMOJI: Record<string, string> = {
  UNACCEPTABLE: '🚫', HIGH_RISK: '🔴', LIMITED_RISK: '🟡', MINIMAL_RISK: '🟢'
}

export default function AdminPage() {
  const { user } = useAuth()
  const [tab, setTab] = useState<'overview'|'runs'|'audit'|'corpus'>('overview')
  const [runs, setRuns] = useState<UserRun[]>([])
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([])
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [auditValid, setAuditValid] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([fetchAllRuns(), fetchStats(), fetchAuditEvents()]).finally(() => setLoading(false))
  }, [])

  async function fetchAllRuns() {
    const { data } = await supabase
      .from('research_runs')
      .select('id,goal,status,risk_level,token_count,cost_usd,duration_ms,created_at,user_id')
      .order('created_at', { ascending: false }).limit(100)
    setRuns((data ?? []) as UserRun[])
  }

  async function fetchStats() {
    const [runsRes, chunksRes, usersRes] = await Promise.all([
      supabase.from('research_runs').select('cost_usd,duration_ms', { count: 'exact' }),
      supabase.from('document_chunks').select('id', { count: 'exact', head: true }),
      supabase.from('research_runs').select('user_id').not('user_id', 'is', null),
    ])
    const allRuns = runsRes.data ?? []
    const uniqueUsers = new Set((usersRes.data ?? []).map((r: any) => r.user_id)).size
    setStats({
      total_runs: runsRes.count ?? 0,
      total_users: uniqueUsers,
      total_chunks: chunksRes.count ?? 0,
      total_cost: allRuns.reduce((s, r) => s + Number(r.cost_usd ?? 0), 0),
      avg_latency: allRuns.length ? allRuns.reduce((s, r) => s + Number(r.duration_ms ?? 0), 0) / allRuns.length / 1000 : 0,
    })
  }

  async function fetchAuditEvents() {
    const { data } = await supabase
      .from('audit_events')
      .select('id,event_type,payload,event_hash,created_at')
      .order('created_at', { ascending: false }).limit(50)
    setAuditEvents((data ?? []) as AuditEvent[])
  }

  async function verifyAuditChain() {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/api/audit/verify`)
      const data = await res.json()
      setAuditValid(data.valid)
    } catch { setAuditValid(false) }
  }

  const completedRuns = runs.filter(r => r.status === 'completed')
  const failedRuns    = runs.filter(r => r.status === 'failed')
  const TABS = [
    { key: 'overview', label: '📊 Overview' },
    { key: 'runs',     label: `🔬 All Runs (${runs.length})` },
    { key: 'audit',   label: '🔒 Audit Log' },
    { key: 'corpus',  label: '📚 Corpus' },
  ]

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <span className="text-2xl">⚙️</span>
        <h1 className="text-2xl font-bold text-white">Admin Panel</h1>
        <span className="ml-2 text-xs bg-red-900 text-red-300 px-2 py-0.5 rounded-full font-medium">ADMIN ONLY</span>
      </div>
      <p className="text-gray-500 text-sm mb-6">
        Signed in as <span className="text-gray-300 font-mono">{user?.email}</span>
      </p>

      <div className="flex gap-1 bg-gray-800 rounded-lg p-1 mb-6">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key as any)}
            className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
              tab === t.key ? 'bg-red-900 text-white' : 'text-gray-400 hover:text-white'
            }`}>{t.label}</button>
        ))}
      </div>

      {loading ? <div className="text-gray-400 text-center py-20">Loading...</div> : <>

        {tab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-5 gap-4">
              {[
                { label: 'Total Runs',   value: stats?.total_runs ?? 0 },
                { label: 'Unique Users', value: stats?.total_users ?? 0 },
                { label: 'Total Chunks', value: (stats?.total_chunks ?? 0).toLocaleString() },
                { label: 'Total Cost',   value: `$${(stats?.total_cost ?? 0).toFixed(3)}` },
                { label: 'Avg Latency', value: `${(stats?.avg_latency ?? 0).toFixed(1)}s` },
              ].map(m => (
                <div key={m.label} className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
                  <div className="text-xs text-gray-500 mb-1">{m.label}</div>
                  <div className="text-xl font-bold text-white">{m.value}</div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="text-xs text-gray-500 mb-1">Completed</div>
                <div className="text-2xl font-bold text-green-400">{completedRuns.length}</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="text-xs text-gray-500 mb-1">Failed</div>
                <div className="text-2xl font-bold text-red-400">{failedRuns.length}</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="text-xs text-gray-500 mb-1">Success Rate</div>
                <div className="text-2xl font-bold text-white">
                  {runs.length ? Math.round(completedRuns.length / runs.length * 100) : 0}%
                </div>
              </div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-gray-400 mb-3">Risk distribution — all users</h3>
              <div className="flex flex-wrap gap-3">
                {Object.entries(
                  runs.reduce((acc, r) => {
                    const k = r.risk_level ?? 'UNKNOWN'
                    acc[k] = (acc[k] ?? 0) + 1
                    return acc
                  }, {} as Record<string, number>)
                ).map(([k, v]) => (
                  <div key={k} className="bg-gray-800 rounded-lg px-4 py-2 text-center">
                    <div>{RISK_EMOJI[k] ?? '⚪'}</div>
                    <div className="text-xs text-gray-400">{k.replace('_', ' ')}</div>
                    <div className="text-lg font-bold text-white">{v}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {tab === 'runs' && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
            {runs.map(r => {
              const goal = r.goal ?? ''
              if (goal.startsWith('[ERASED')) return null
              return (
                <div key={r.id} className="flex items-center gap-3 px-4 py-3 text-xs hover:bg-gray-800 transition-colors">
                  <span className="text-lg shrink-0">{RISK_EMOJI[r.risk_level ?? ''] ?? '⚪'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-gray-200 truncate">{goal.slice(0, 70)}...</div>
                    <div className="text-gray-500 font-mono mt-0.5">{r.user_id?.slice(0, 8) ?? 'anon'} · {r.id.slice(0, 8)}</div>
                  </div>
                  <span className={`shrink-0 px-2 py-0.5 rounded-full font-medium ${
                    r.status === 'completed' ? 'bg-green-900 text-green-300'
                    : r.status === 'failed'  ? 'bg-red-900 text-red-300'
                    : 'bg-gray-700 text-gray-300'
                  }`}>{r.status}</span>
                  <span className="text-gray-500 shrink-0">${Number(r.cost_usd ?? 0).toFixed(4)}</span>
                  <span className="text-gray-500 shrink-0">{((r.duration_ms ?? 0)/1000).toFixed(1)}s</span>
                  <span className="text-gray-600 shrink-0">{r.created_at?.slice(0, 10)}</span>
                </div>
              )
            })}
          </div>
        )}

        {tab === 'audit' && (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <button onClick={verifyAuditChain}
                className="bg-blue-800 hover:bg-blue-700 text-white text-xs px-4 py-2 rounded-lg transition-colors">
                🔍 Verify SHA-256 Chain
              </button>
              {auditValid !== null && (
                <span className={`text-sm font-medium ${auditValid ? 'text-green-400' : 'text-red-400'}`}>
                  {auditValid ? '✅ Chain intact' : '❌ Chain broken — tampering detected'}
                </span>
              )}
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
              {auditEvents.map(e => (
                <div key={e.id} className="px-4 py-3 text-xs">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-mono text-blue-400">{e.event_type}</span>
                    <span className="text-gray-600">{e.created_at?.slice(0, 19).replace('T', ' ')}</span>
                    <span className="text-gray-700 font-mono truncate ml-auto">{e.event_hash?.slice(0, 16)}…</span>
                  </div>
                  <pre className="text-gray-500 overflow-x-auto">{JSON.stringify(e.payload, null, 2).slice(0, 200)}</pre>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'corpus' && (
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h3 className="text-white font-semibold mb-2">Corpus Management</h3>
              <p className="text-sm text-gray-400 mb-4">Run locally to update the knowledge base.</p>
              {[
                { label: 'Ingest demo corpus', cmd: 'uv run python scripts/ingest_demo_corpus.py' },
                { label: 'Rebuild FTS index',  cmd: 'uv run python scripts/migrate_fts_multilingual.py' },
                { label: 'Run RAGAS eval',     cmd: 'uv run python scripts/run_ragas_baseline.py' },
                { label: 'Run LLM-as-judge',   cmd: 'uv run python evals/judge.py' },
              ].map(({ label, cmd }) => (
                <div key={cmd} className="mb-3">
                  <div className="text-xs text-gray-500 mb-1">{label}</div>
                  <code className="block bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-blue-300 font-mono">{cmd}</code>
                </div>
              ))}
            </div>
            <div className="bg-yellow-950 border border-yellow-800 rounded-xl p-4">
              <p className="text-yellow-300 text-xs">⚠️ Ingestion uses the service role key and must be run locally. Never expose it to the frontend.</p>
            </div>
          </div>
        )}
      </>}
    </div>
  )
}
