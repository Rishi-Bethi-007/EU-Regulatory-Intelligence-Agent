import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { supabase } from '../lib/supabase'
import { getRunStatus, getAgentTasks } from '../lib/api'
import { ResearchRun, AgentTask, DecisionTrace } from '../lib/types'
import RiskBadge from '../components/RiskBadge'
import MetricCard from '../components/MetricCard'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  theme: 'neutral',
  themeVariables: { fontSize: '13px' },
  flowchart: { useMaxWidth: true, htmlLabels: true },
})

function MermaidBlock({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const id = `mermaid-${Math.random().toString(36).slice(2)}`
    mermaid.render(id, code).then(({ svg }) => {
      if (!ref.current) return
      ref.current.innerHTML = svg
      const svgEl = ref.current.querySelector('svg')
      if (svgEl) { svgEl.removeAttribute('width'); svgEl.removeAttribute('height'); svgEl.style.maxWidth = '100%'; svgEl.style.height = 'auto' }
    }).catch(console.error)
  }, [code])
  return <div ref={ref} className="my-6 overflow-auto bg-gray-50 rounded-xl p-4 border border-gray-200" style={{ maxHeight: '420px' }} />
}

function TableOfContents({ text }: { text: string }) {
  const headings = [...text.matchAll(/^#{1,3} (.+)$/gm)].map(m => m[1]).filter(h => h.length > 3)
  if (headings.length < 3) return null
  return (
    <details className="mb-6 bg-gray-50 rounded-xl border border-gray-200">
      <summary className="px-4 py-3 cursor-pointer text-sm font-medium text-gray-600 hover:text-gray-900">
        📑 Table of Contents ({headings.length} sections)
      </summary>
      <div className="px-4 pb-3 space-y-1">
        {headings.map((h, i) => (
          <div key={i} className="text-sm text-blue-600 hover:text-blue-700">
            {h.startsWith('###') ? '\u00a0\u00a0\u00a0\u00a0' : h.startsWith('##') ? '\u00a0\u00a0' : ''}• {h}
          </div>
        ))}
      </div>
    </details>
  )
}

function TraceCard({ name, trace }: { name: string; trace: DecisionTrace }) {
  const [open, setOpen] = useState(false)
  const pct   = Math.round(trace.confidence * 100)
  const label = pct >= 80 ? 'High' : pct >= 60 ? 'Medium' : 'Low'
  const color = pct >= 80 ? '#16a34a' : pct >= 60 ? '#ca8a04' : '#dc2626'
  const LABELS: Record<string, string> = {
    risk_classifier: '🛡️ Risk Classifier', planner: '🗺️ Planner',
    researcher: '🔍 Researcher', analyst: '⚖️ Analyst',
    critic: '🧠 Critic', synthesizer: '✍️ Synthesizer',
  }
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left">
        <span className="text-sm font-medium text-gray-800">{LABELS[name] ?? name}</span>
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium" style={{ color }}>{label} ({pct}%)</span>
          <span className="text-gray-400 text-xs">{open ? '▲' : '▼'}</span>
        </div>
      </button>
      {open && (
        <div className="bg-white px-4 py-3 border-t border-gray-100 space-y-3">
          <div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden mb-1">
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
            </div>
            <span className="text-xs font-medium" style={{ color }}>{label} confidence — {pct}%</span>
            {trace.duration_ms > 0 && <span className="text-xs text-gray-400 ml-3">⏱ {trace.duration_ms}ms</span>}
          </div>
          {trace.reasoning_steps?.length > 0 && (
            <div>
              <div className="text-xs text-gray-500 font-medium mb-1">Reasoning:</div>
              <ul className="space-y-1">{trace.reasoning_steps.map((s, i) => <li key={i} className="text-xs text-gray-600">• {s}</li>)}</ul>
            </div>
          )}
          {trace.sources_used?.length > 0 && (
            <div>
              <div className="text-xs text-gray-500 font-medium mb-1">Sources used:</div>
              {trace.sources_used.slice(0, 5).map((s, i) => (
                <div key={i} className="text-xs text-blue-600 truncate">
                  {s.startsWith('http') ? <a href={s} target="_blank" rel="noreferrer">{s.slice(0, 80)}</a> : s}
                </div>
              ))}
            </div>
          )}
          {trace.counterfactual && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
              <div className="text-xs text-blue-700 font-medium mb-1">Counterfactual (EU AI Act Art. 13):</div>
              <p className="text-xs text-blue-800">{trace.counterfactual}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

async function preRenderMermaidBlocks(markdown: string): Promise<string> {
  const mermaidRegex = /```mermaid\n([\s\S]*?)```/g
  const replacements: Array<{ original: string; svg: string }> = []
  let match
  while ((match = mermaidRegex.exec(markdown)) !== null) {
    const original = match[0]; const code = match[1].trim()
    const id = `pdf-mermaid-${replacements.length}-${Math.random().toString(36).slice(2)}`
    try {
      const { svg } = await mermaid.render(id, code)
      const scaledSvg = svg.replace(/width="[^"]+"/, 'width="100%"').replace(/height="[^"]+"/, 'height="auto" style="max-width:100%;display:block;margin:16px 0"')
      replacements.push({ original, svg: scaledSvg })
    } catch {
      replacements.push({ original, svg: '<div class="diagram-note">[ Diagram could not be rendered ]</div>' })
    }
  }
  let result = markdown
  for (const { original, svg } of replacements) result = result.replace(original, `\n\n${svg}\n\n`)
  return result
}

function downloadReportAsPdf(reportText: string, runId: string, riskLevel: string | null, goal: string) {
  const date = new Date().toLocaleDateString('en-SE', { year: 'numeric', month: 'long', day: 'numeric' })
  const mdToHtml = (md: string): string => md
    .replace(/```mermaid[\s\S]*?```/g, '<div class="diagram-note">[ Interactive diagram — view in web app ]</div>')
    .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code class="lang-$1">$2</code></pre>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/^## (.+)$/gm, '<h2>$1</h2>').replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>').replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/^---$/gm, '<hr/>').replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>').replace(/^\s*\d+\. (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]+?<\/li>)/g, (block) => block.startsWith('<li>') ? `<ul>${block}</ul>` : block)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
    .split(/\n{2,}/).map(chunk => { const trimmed = chunk.trim(); if (!trimmed) return ''; if (/^<(h[1-6]|ul|ol|pre|blockquote|hr|div)/.test(trimmed)) return trimmed; return `<p>${trimmed.replace(/\n/g, ' ')}</p>` }).join('\n')
  const RISK_COLORS: Record<string, string> = { UNACCEPTABLE: '#ef4444', HIGH_RISK: '#f97316', LIMITED_RISK: '#eab308', MINIMAL_RISK: '#22c55e' }
  const riskColor = RISK_COLORS[riskLevel ?? ''] ?? '#6b7280'
  const htmlContent = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/><title>EU Compliance Report</title>
<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Inter',sans-serif;font-size:11pt;line-height:1.65;color:#1a1a2e;background:#fff;padding:0}
.cover{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);color:#fff;padding:36px 48px 28px}
.cover-flag{font-size:28pt;margin-bottom:8px}.cover-title{font-size:18pt;font-weight:700;margin-bottom:6px;color:#e2e8f0}
.cover-subtitle{font-size:9.5pt;color:#94a3b8;margin-bottom:16px}.cover-meta{display:flex;gap:24px;font-size:8.5pt;color:#94a3b8}
.risk-chip{display:inline-block;padding:3px 10px;border-radius:20px;font-size:8pt;font-weight:600;color:#fff;background:${riskColor}}
.goal-box{margin:0;padding:16px 48px;background:#f0f4ff;border-left:4px solid #3b82f6;font-size:10pt;color:#1e3a5f;font-style:italic}
.body{padding:32px 48px 48px}h1{font-size:15pt;font-weight:700;color:#1a1a2e;margin:28px 0 10px;border-bottom:2px solid #e2e8f0;padding-bottom:6px}
h2{font-size:13pt;font-weight:600;color:#1e3a5f;margin:22px 0 8px;border-bottom:1px solid #e2e8f0;padding-bottom:4px}
h3{font-size:11.5pt;font-weight:600;color:#374151;margin:16px 0 6px}p{margin-bottom:10px;color:#374151}
ul,ol{margin:0 0 10px 20px}li{margin-bottom:4px;color:#374151}
code{font-family:'Menlo',monospace;font-size:9pt;background:#f1f5f9;color:#0f172a;padding:1px 5px;border-radius:3px}
pre{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:14px;overflow-x:auto;margin:12px 0;font-size:8.5pt}
blockquote{border-left:3px solid #3b82f6;padding:8px 14px;margin:12px 0;background:#eff6ff;color:#1e40af;font-style:italic;border-radius:0 4px 4px 0}
a{color:#2563eb;text-decoration:underline}hr{border:none;border-top:1px solid #e2e8f0;margin:18px 0}
.diagram-note{background:#fef9c3;border:1px dashed #ca8a04;border-radius:6px;padding:10px 14px;font-size:9pt;color:#713f12;text-align:center;margin:12px 0}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:9.5pt}
th{background:#f1f5f9;text-align:left;padding:7px 10px;border:1px solid #e2e8f0;font-weight:600;color:#1e3a5f}
td{padding:7px 10px;border:1px solid #e2e8f0;color:#374151}tr:nth-child(even) td{background:#f8fafc}
.footer{border-top:1px solid #e2e8f0;margin-top:32px;padding-top:12px;font-size:8pt;color:#9ca3af;display:flex;justify-content:space-between}
@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.cover{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body>
<div class="cover"><div class="cover-flag">🇪🇺</div><div class="cover-title">EU Regulatory Intelligence Report</div>
<div class="cover-subtitle">Multi-Agent EU AI Act &amp; GDPR Compliance Analysis</div>
<div class="cover-meta"><span>📅 ${date}</span><span>🆔 Run ${runId.slice(0, 8)}</span><span class="risk-chip">${(riskLevel ?? 'UNKNOWN').replace('_', ' ')}</span></div></div>
${goal ? `<div class="goal-box"><strong>Research Query:</strong> ${goal}</div>` : ''}
<div class="body">${mdToHtml(reportText)}<div class="footer"><span>EU Regulatory Intelligence Agent · Rishi Bethi</span><span>Generated ${date} · Run ID: ${runId}</span></div></div>
</body></html>`
  const win = window.open('', '_blank', 'width=900,height=700')
  if (!win) { alert('Pop-ups are blocked. Please allow pop-ups and try again.'); return }
  win.document.write(htmlContent); win.document.close()
  setTimeout(() => { win.focus(); win.print() }, 600)
}

export default function ReportsPage() {
  const { runId: paramRunId } = useParams<{ runId: string }>()
  const { user }   = useAuth()
  const navigate   = useNavigate()
  const [tab,         setTab]         = useState<'report' | 'traces' | 'download'>('report')
  const [activeRunId, setActiveRunId] = useState<string | null>(paramRunId ?? null)
  const [run,         setRun]         = useState<ResearchRun | null>(null)
  const [tasks,       setTasks]       = useState<AgentTask[]>([])
  const [recentRuns,  setRecentRuns]  = useState<ResearchRun[]>([])
  const [pdfLoading,  setPdfLoading]  = useState(false)

  useEffect(() => { fetchRecentRuns() }, [user])
  useEffect(() => { if (activeRunId) fetchRun(activeRunId) }, [activeRunId])

  async function fetchRecentRuns() {
    if (!user) return
    const { data } = await supabase.from('research_runs')
      .select('id, goal, risk_level, transparency_score, created_at')
      .eq('status', 'completed').eq('user_id', user.id)
      .not('goal', 'like', '[ERASED%]')
      .order('created_at', { ascending: false }).limit(10)
    setRecentRuns((data ?? []) as ResearchRun[])
    if (!activeRunId && data?.[0]) setActiveRunId(data[0].id)
  }

  async function fetchRun(id: string) {
    const [status, agentsRes] = await Promise.all([getRunStatus(id), getAgentTasks(id)])
    setRun(status); setTasks(agentsRes.agents ?? [])
  }

  async function handlePdfDownload() {
    if (!run || !activeRunId) return
    setPdfLoading(true)
    try {
      const preRenderedText = await preRenderMermaidBlocks(run.result ?? '')
      downloadReportAsPdf(preRenderedText, activeRunId, run.risk_level, run.goal ?? '')
    } catch { downloadReportAsPdf(run.result ?? '', activeRunId, run.risk_level, run.goal ?? '') }
    finally { setTimeout(() => setPdfLoading(false), 1200) }
  }

  const taskMap    = Object.fromEntries(tasks.map(t => [t.agent_name, t]))
  const reportText = run?.result ?? ''
  const charCount  = reportText.length
  const readMin    = Math.max(1, Math.round(charCount / 1200))

  const TABS = [
    { key: 'report',   label: `📄 Report (${charCount.toLocaleString()} chars · ~${readMin}m read)` },
    { key: 'traces',   label: '🧠 XAI Traces' },
    { key: 'download', label: '📥 Download' },
  ]

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 p-4 shrink-0">
        <h2 className="text-sm font-semibold text-gray-500 mb-3">📂 Recent Runs</h2>
        <div className="space-y-2">
          {recentRuns.map(r => {
            const isActive = r.id === activeRunId
            const EMOJI: Record<string, string> = { UNACCEPTABLE: '🚫', HIGH_RISK: '🔴', LIMITED_RISK: '🟡', MINIMAL_RISK: '🟢' }
            return (
              <button key={r.id}
                onClick={() => { setActiveRunId(r.id); navigate(`/app/reports/${r.id}`) }}
                className={`w-full text-left rounded-lg p-2.5 text-xs transition-colors border ${
                  isActive ? 'bg-blue-50 border-blue-200 text-blue-900' : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50'
                }`}>
                <div className="truncate mb-1 font-medium">{(r.goal ?? '').slice(0, 40)}...</div>
                <div className="flex items-center gap-1.5 text-gray-400">
                  <span>{EMOJI[r.risk_level ?? ''] ?? '⚪'}</span>
                  <span>📊 {r.transparency_score ?? 0}/100</span>
                  <span>{r.created_at?.slice(0, 10)}</span>
                </div>
              </button>
            )
          })}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 p-8 overflow-auto">
        {!activeRunId ? (
          <div className="text-center text-gray-400 mt-20">
            <div className="text-5xl mb-4">📋</div>
            <p>No run selected. <button className="text-blue-600 hover:text-blue-700" onClick={() => navigate('/app')}>Start a research query</button> or select from the sidebar.</p>
          </div>
        ) : !run ? (
          <div className="text-gray-400 text-center mt-20">Loading report...</div>
        ) : (
          <>
            <div className="grid grid-cols-4 gap-4 mb-6">
              <MetricCard label="Tokens"   value={(run.token_count ?? 0).toLocaleString()} />
              <MetricCard label="Cost"     value={`$${Number(run.cost_usd ?? 0).toFixed(4)}`} />
              <MetricCard label="Duration" value={`${((run.duration_ms ?? 0) / 1000).toFixed(1)}s`} />
              <MetricCard label="Risk"     value={run.risk_level?.replace('_', ' ') ?? 'N/A'} />
            </div>

            <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6 overflow-x-auto">
              {TABS.map(t => (
                <button key={t.key} onClick={() => setTab(t.key as any)}
                  className={`whitespace-nowrap px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                    tab === t.key ? 'bg-white text-gray-900 shadow-sm border border-gray-200' : 'text-gray-500 hover:text-gray-700'
                  }`}>
                  {t.label}
                </button>
              ))}
            </div>

            {tab === 'report' && (
              <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-sm">
                <TableOfContents text={reportText} />
                <div className="report-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                    code({ className, children }: any) {
                      const lang = /language-(\w+)/.exec(className ?? '')?.[1]
                      const code = String(children).replace(/\n$/, '')
                      if (lang === 'mermaid') return <MermaidBlock code={code} />
                      return <code className={className}>{children}</code>
                    },
                  }}>{reportText}</ReactMarkdown>
                </div>
              </div>
            )}

            {tab === 'traces' && (
              <div className="space-y-3">
                <h3 className="text-lg font-semibold text-gray-900">EU AI Act Art. 13 — Explainability Traces</h3>
                <p className="text-sm text-gray-500 mb-4">Every agent produced a decision trace recording reasoning steps, sources, confidence level, and counterfactual explanation.</p>
                {['risk_classifier', 'planner', 'researcher', 'analyst', 'critic', 'synthesizer'].map(name => {
                  const task = taskMap[name]
                  if (!task?.decision_trace) return null
                  return <TraceCard key={name} name={name} trace={task.decision_trace} />
                })}
              </div>
            )}

            {tab === 'download' && (
              <div className="max-w-lg space-y-4">
                <h3 className="text-lg font-semibold text-gray-900">Download Report</h3>
                <p className="text-sm text-gray-500">Export the full compliance report in your preferred format.</p>
                <div className="card flex items-start gap-4">
                  <div className="text-3xl">📝</div>
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-gray-900 mb-1">Markdown (.md)</div>
                    <div className="text-xs text-gray-500 mb-3">Raw report with headings, tables, and Mermaid diagrams. Best for Notion / Confluence.</div>
                    <a href={`data:text/markdown;charset=utf-8,${encodeURIComponent(reportText)}`}
                      download={`eu_compliance_report_${activeRunId?.slice(0, 8)}.md`}
                      className="btn-secondary text-xs inline-block">⬇ Download .md</a>
                  </div>
                </div>
                <div className="card flex items-start gap-4 border-blue-200 bg-blue-50">
                  <div className="text-3xl">📄</div>
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-gray-900 mb-1">
                      PDF Report
                      <span className="ml-2 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-normal border border-blue-200">Recommended</span>
                    </div>
                    <div className="text-xs text-gray-500 mb-3">
                      Professionally formatted PDF with cover page and EU AI Act risk badge.
                      Opens in new tab — use <kbd className="bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded text-xs border border-gray-200">Ctrl+P</kbd> → Save as PDF.
                    </div>
                    <button onClick={handlePdfDownload} disabled={pdfLoading} className="btn-primary text-xs">
                      {pdfLoading ? '⏳ Opening...' : '⬇ Export as PDF'}
                    </button>
                  </div>
                </div>
                <p className="text-xs text-gray-400 mt-2 font-mono">Run ID: {activeRunId} · {charCount.toLocaleString()} chars</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
