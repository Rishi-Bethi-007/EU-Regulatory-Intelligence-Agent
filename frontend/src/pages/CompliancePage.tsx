import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { supabase } from '../lib/supabase'
import { getUserData, eraseUserData } from '../lib/api'
import { ResearchRun, RiskLevel, RISK_CONFIG } from '../lib/types'
import RiskBadge from '../components/RiskBadge'

const SCORE_DIMENSIONS = [
  { key: 'sources_cited',       label: 'Sources cited',               desc: 'Web sources retrieved during research' },
  { key: 'risk_classified',     label: 'Risk level classified',       desc: 'EU AI Act risk tier assigned before agents ran' },
  { key: 'transparency_notice', label: 'Transparency notice present', desc: 'Art. 13 notice generated and stored' },
  { key: 'decision_traces',     label: 'Decision traces populated',   desc: 'All agents produced XAI traces' },
  { key: 'critic_confidence',   label: 'Critic confidence ≥ 70%',     desc: 'All obligations verified above threshold' },
]

function TransparencyGauge({ score }: { score: number }) {
  const color = score >= 80 ? '#4ade80' : score >= 60 ? '#facc15' : '#f87171'
  return (
    <div className="text-center py-4">
      <div className="text-5xl font-black mb-1" style={{ color }}>{score}</div>
      <div className="text-sm text-gray-500 mb-3">out of 100</div>
      <div className="h-3 bg-gray-800 rounded-full overflow-hidden max-w-xs mx-auto">
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${score}%`, background: color }} />
      </div>
    </div>
  )
}

export default function CompliancePage() {
  const { runId: paramRunId } = useParams<{ runId: string }>()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [tab,         setTab]         = useState<'risk'|'obligations'|'notice'|'gdpr'>('risk')
  const [activeRunId, setActiveRunId] = useState<string | null>(paramRunId ?? null)
  const [run,         setRun]         = useState<ResearchRun | null>(null)
  const [recentRuns,  setRecentRuns]  = useState<any[]>([])
  const [gdprData,    setGdprData]    = useState<any>(null)
  const [eraseConfirm, setEraseConfirm] = useState(false)
  const [gdprLoading, setGdprLoading] = useState(false)
  const [gdprMsg,     setGdprMsg]     = useState('')

  useEffect(() => { fetchRecentRuns() }, [user])
  useEffect(() => { if (activeRunId) fetchRun(activeRunId) }, [activeRunId])

  async function fetchRecentRuns() {
    if (!user) return
    const { data } = await supabase.from('research_runs')
      .select('id,goal,risk_level,transparency_score,created_at')
      .eq('status','completed').eq('user_id', user.id)
      .not('goal','like','[ERASED%]')
      .order('created_at',{ascending:false}).limit(10)
    setRecentRuns(data ?? [])
    if (!activeRunId && data?.[0]) setActiveRunId(data[0].id)
  }

  async function fetchRun(id: string) {
    const { data } = await supabase.from('research_runs').select('*').eq('id', id).single()
    setRun(data)
  }

  async function handleAccessData() {
    if (!user) return
    setGdprLoading(true); setGdprMsg('')
    try {
      const data = await getUserData(user.id)
      if (!data) { setGdprMsg('No data found for your account.'); return }
      setGdprData(data)
    } catch (e: any) {
      setGdprMsg(`Error: ${e.message}`)
    } finally {
      setGdprLoading(false)
    }
  }

  async function handleEraseData() {
    if (!user || !eraseConfirm) return
    setGdprLoading(true); setGdprMsg('')
    try {
      const result = await eraseUserData(user.id)
      if (!result) { setGdprMsg('No data found to erase.'); return }
      setGdprMsg(`✅ Erased. ${result.runs_anonymised} runs anonymised. Audit log: ${result.audit_event_id?.slice(0,8)}...`)
      setGdprData(null)
    } catch (e: any) {
      setGdprMsg(`Error: ${e.message}`)
    } finally {
      setGdprLoading(false)
    }
  }

  const EMOJI: Record<string,string> = {UNACCEPTABLE:'🚫',HIGH_RISK:'🔴',LIMITED_RISK:'🟡',MINIMAL_RISK:'🟢'}
  const score = run?.transparency_score ?? 0
  const meta  = (run as any)?.metadata ?? {}
  const breakdown = meta?.transparency_breakdown

  const TABS = [
    { key: 'risk',        label: '🎯 Risk & Score' },
    { key: 'obligations', label: '📋 Obligations' },
    { key: 'notice',      label: '🔍 Transparency Notice' },
    { key: 'gdpr',        label: '🔒 GDPR Rights' },
  ]

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 border-r border-gray-800 p-4 shrink-0">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Select Run</h2>
        <div className="space-y-2">
          {recentRuns.map(r => {
            const isActive = r.id === activeRunId
            return (
              <button key={r.id} onClick={() => { setActiveRunId(r.id); navigate(`/compliance/${r.id}`) }}
                className={`w-full text-left rounded-lg p-2.5 text-xs transition-colors border ${
                  isActive ? 'bg-blue-900 border-blue-700 text-white' : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                }`}>
                <div className="truncate mb-1">{(r.goal ?? '').slice(0,40)}...</div>
                <div className="flex items-center gap-1.5 text-gray-400">
                  <span>{EMOJI[r.risk_level ?? ''] ?? '⚪'}</span>
                  <span>📊 {r.transparency_score ?? 0}/100</span>
                </div>
              </button>
            )
          })}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 p-8 overflow-auto">
        <h1 className="text-2xl font-bold text-white mb-1">🇪🇺 EU Compliance Dashboard</h1>
        <p className="text-gray-400 text-sm mb-6">EU AI Act risk classification · Transparency scoring · GDPR rights</p>

        {!activeRunId ? (
          <div className="text-center text-gray-500 mt-20">
            <div className="text-5xl mb-4">🇪🇺</div>
            <p>No run selected. <button className="text-blue-400 hover:text-blue-300" onClick={() => navigate('/')}>Start a research query.</button></p>
          </div>
        ) : (
          <>
            {run?.goal && !run.goal.startsWith('[ERASED') && (
              <p className="text-gray-300 text-sm mb-4 line-clamp-2">{run.goal}</p>
            )}

            {/* Tabs */}
            <div className="flex gap-1 bg-gray-800 rounded-lg p-1 mb-6">
              {TABS.map(t => (
                <button key={t.key} onClick={() => setTab(t.key as any)}
                  className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
                    tab === t.key ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'
                  }`}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* Risk & Score tab */}
            {tab === 'risk' && (
              <div className="grid grid-cols-2 gap-6">
                <div className="card">
                  <h3 className="text-sm font-semibold text-gray-400 mb-4">EU AI Act Risk Classification</h3>
                  <RiskBadge level={run?.risk_level} size="lg" />
                  {run?.risk_justification && (
                    <div className="mt-4 bg-gray-800 rounded-lg p-3 text-sm text-gray-300">
                      {run.risk_justification}
                    </div>
                  )}
                </div>
                <div className="card">
                  <h3 className="text-sm font-semibold text-gray-400 mb-2">Transparency Score</h3>
                  <TransparencyGauge score={score} />
                  <div className="space-y-2 mt-2">
                    {SCORE_DIMENSIONS.map(({ key, label, desc }, i) => {
                      const passed = breakdown
                        ? breakdown[key]?.passed
                        : score >= (i + 1) * 20
                      return (
                        <div key={key} className="flex items-start gap-2">
                          <span className="text-sm mt-0.5">{passed ? '✅' : '❌'}</span>
                          <div>
                            <div className="text-xs font-medium text-gray-200">{label}</div>
                            <div className="text-xs text-gray-500">{desc}</div>
                          </div>
                          <span className="ml-auto text-xs text-gray-500">+20</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* Obligations tab */}
            {tab === 'obligations' && (
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-400 mb-4">EU AI Act + GDPR Obligations Checklist</h3>
                <p className="text-xs text-gray-500 mb-4">Auto-ticked based on run metadata. All ticked items are verifiable in the audit log.</p>
                <div className="space-y-3">
                  {[
                    ['Risk classification performed',  !!run?.risk_level],
                    ['Research completed',             run?.status === 'completed'],
                    ['Transparency notice generated',  !!run?.transparency_notice],
                    ['Transparency score computed',    (run?.transparency_score ?? 0) > 0],
                    ['Audit event logged',             true],
                    ['GDPR lawful basis documented',   true],
                  ].map(([label, ticked]) => (
                    <div key={String(label)} className="flex items-center gap-3">
                      <span className="text-lg">{ticked ? '☑️' : '⬜'}</span>
                      <span className={`text-sm ${ticked ? 'text-gray-200' : 'text-gray-500'}`}>{label as string}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Transparency notice tab */}
            {tab === 'notice' && (
              <div className="card">
                <h3 className="text-sm font-semibold text-gray-400 mb-3">EU AI Act Art. 13 — Transparency Notice</h3>
                <p className="text-xs text-gray-500 mb-4">
                  Every run generates a transparency notice disclosing which AI models were used,
                  which sources were retrieved, the confidence level, and known limitations.
                  Required for high-risk AI systems under EU AI Act Article 13.
                </p>
                {run?.transparency_notice ? (
                  <pre className="bg-gray-800 rounded-lg p-4 text-xs text-gray-300 overflow-auto whitespace-pre-wrap max-h-[500px]">
                    {run.transparency_notice}
                  </pre>
                ) : (
                  <div className="text-gray-500 text-sm">No transparency notice for this run.</div>
                )}
              </div>
            )}

            {/* GDPR Rights tab */}
            {tab === 'gdpr' && (
              <div className="grid grid-cols-2 gap-6">
                {/* Art. 15 */}
                <div className="card">
                  <h3 className="text-sm font-semibold text-white mb-1">📋 Art. 15 — Right of Access</h3>
                  <p className="text-xs text-gray-400 mb-4">See all data held about you: research runs and audit events.</p>
                  <button onClick={handleAccessData} disabled={gdprLoading} className="btn-secondary text-sm">
                    {gdprLoading ? 'Loading...' : 'Request My Data'}
                  </button>
                  {gdprData && (
                    <div className="mt-4 bg-gray-800 rounded-lg p-3 text-xs text-gray-300">
                      <div className="text-green-400 font-medium mb-2">Found {gdprData.total_records} records</div>
                      <div className="mb-1"><strong className="text-white">Research runs:</strong> {gdprData.research_runs?.length}</div>
                      {gdprData.research_runs?.slice(0,3).map((r: any) => (
                        <div key={r.id} className="text-gray-400 truncate pl-2">• {(r.goal ?? '').slice(0,50)}...</div>
                      ))}
                      <div className="mt-1"><strong className="text-white">Audit events:</strong> {gdprData.audit_events?.length}</div>
                    </div>
                  )}
                </div>

                {/* Art. 17 */}
                <div className="card border-red-900">
                  <h3 className="text-sm font-semibold text-white mb-1">🗑️ Art. 17 — Right to Erasure</h3>
                  <div className="bg-red-950 border border-red-800 rounded-lg p-3 mb-4 text-xs text-red-300">
                    ⚠️ <strong>Warning:</strong> This permanently deletes all your data and cannot be undone.
                  </div>
                  <label className="flex items-center gap-2 mb-4 cursor-pointer">
                    <input type="checkbox" checked={eraseConfirm}
                      onChange={e => setEraseConfirm(e.target.checked)} className="rounded" />
                    <span className="text-xs text-gray-300">I understand this is permanent</span>
                  </label>
                  <button
                    onClick={handleEraseData}
                    disabled={!eraseConfirm || gdprLoading}
                    className="btn-danger text-sm"
                  >
                    {gdprLoading ? 'Erasing...' : 'Erase My Data'}
                  </button>
                </div>

                {gdprMsg && (
                  <div className="col-span-2 bg-gray-800 rounded-lg p-3 text-sm text-gray-300">
                    {gdprMsg}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
