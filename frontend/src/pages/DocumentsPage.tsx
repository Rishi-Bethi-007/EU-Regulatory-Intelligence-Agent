import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import { Document } from '../lib/types'

interface Stats { total_docs: number; total_chunks: number; en: number; sv: number; de: number }

export default function DocumentsPage() {
  const [stats,   setStats]   = useState<Stats | null>(null)
  const [docs,    setDocs]    = useState<Document[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { Promise.all([fetchStats(), fetchDocs()]).finally(() => setLoading(false)) }, [])

  async function fetchStats() {
    const [docs, chunks, en, sv, de] = await Promise.all([
      supabase.from('documents').select('id', { count: 'exact', head: true }),
      supabase.from('document_chunks').select('id', { count: 'exact', head: true }),
      supabase.from('document_chunks').select('id', { count: 'exact', head: true }).eq('language', 'en'),
      supabase.from('document_chunks').select('id', { count: 'exact', head: true }).eq('language', 'sv'),
      supabase.from('document_chunks').select('id', { count: 'exact', head: true }).eq('language', 'de'),
    ])
    setStats({ total_docs: docs.count ?? 0, total_chunks: chunks.count ?? 0, en: en.count ?? 0, sv: sv.count ?? 0, de: de.count ?? 0 })
  }

  async function fetchDocs() {
    const { data } = await supabase.from('documents')
      .select('id,title,language,doc_type,chunk_count,source_url,created_at')
      .order('created_at', { ascending: false }).limit(50)
    setDocs(data ?? [])
  }

  const LANG_FLAG: Record<string, string> = { en: '🇬🇧', sv: '🇸🇪', de: '🇩🇪' }
  const TYPE_LABEL: Record<string, string> = {
    regulatory: '⚖️ Regulatory', swedish_market: '🇸🇪 Swedish Market', german_market: '🇩🇪 German Market',
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">📄 Regulatory Knowledge Base</h1>
      <p className="text-gray-500 text-sm mb-8">
        Curated EU AI Act, GDPR, and national regulatory guidance documents in English, Swedish, and German.
        Embedded with <span className="text-blue-600 font-mono">multilingual-e5-large</span> (1024 dims) · Hybrid dense+sparse retrieval.
      </p>

      {loading ? (
        <div className="text-gray-400">Loading corpus stats...</div>
      ) : (
        <>
          {stats && (
            <div className="grid grid-cols-5 gap-4 mb-8">
              {[
                { label: 'Documents',    value: stats.total_docs,                                           sub: '' },
                { label: 'Total Chunks', value: stats.total_chunks.toLocaleString(),                        sub: '' },
                { label: '🇬🇧 English',  value: stats.en.toLocaleString(), sub: `${(stats.en / stats.total_chunks * 100).toFixed(1)}%` },
                { label: '🇸🇪 Swedish',  value: stats.sv.toLocaleString(), sub: `${(stats.sv / stats.total_chunks * 100).toFixed(1)}%` },
                { label: '🇩🇪 German',   value: stats.de.toLocaleString(), sub: `${(stats.de / stats.total_chunks * 100).toFixed(1)}%` },
              ].map(m => (
                <div key={m.label} className="metric-card">
                  <div className="text-xs text-gray-500 mb-1">{m.label}</div>
                  <div className="text-xl font-bold text-gray-900">{m.value}</div>
                  {m.sub && <div className="text-xs text-gray-400">{m.sub}</div>}
                </div>
              ))}
            </div>
          )}

          {stats && stats.total_chunks > 0 && (
            <div className="card mb-8">
              <h2 className="text-sm font-semibold text-gray-500 mb-3">Language distribution</h2>
              {[
                { label: '🇬🇧 English', count: stats.en, color: 'bg-blue-500'   },
                { label: '🇸🇪 Swedish', count: stats.sv, color: 'bg-yellow-400' },
                { label: '🇩🇪 German',  count: stats.de, color: 'bg-red-500'    },
              ].map(({ label, count, color }) => (
                <div key={label} className="flex items-center gap-3 mb-2">
                  <span className="text-xs text-gray-500 w-24 shrink-0">{label}</span>
                  <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${color}`} style={{ width: `${(count / stats.total_chunks * 100).toFixed(1)}%` }} />
                  </div>
                  <span className="text-xs text-gray-400 w-12 text-right">{(count / stats.total_chunks * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}

          <div className="card">
            <h2 className="text-sm font-semibold text-gray-500 mb-4">Corpus Documents ({docs.length})</h2>
            <div className="space-y-3">
              {docs.map(doc => (
                <div key={doc.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                  <div className="flex-1 min-w-0">
                    {doc.source_url ? (
                      <a href={doc.source_url} target="_blank" rel="noreferrer"
                        className="text-sm text-blue-600 hover:text-blue-700 font-medium truncate block">
                        {doc.title}
                      </a>
                    ) : (
                      <span className="text-sm text-gray-800 font-medium">{doc.title}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 ml-4 shrink-0 text-xs text-gray-400">
                    <span>{LANG_FLAG[doc.language] ?? '🌐'} {doc.language?.toUpperCase()}</span>
                    <span>{doc.chunk_count} chunks</span>
                    <span className="hidden md:inline">{TYPE_LABEL[doc.doc_type] ?? doc.doc_type}</span>
                    <span>{doc.created_at?.slice(0, 10)}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-300 mt-4">Documents are ingested by the system administrator via the ingestion pipeline.</p>
          </div>
        </>
      )}
    </div>
  )
}
