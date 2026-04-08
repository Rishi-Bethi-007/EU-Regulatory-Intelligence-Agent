import { useNavigate } from 'react-router-dom'

const AGENTS = [
  { icon: '🛡️', name: 'Risk Classifier',  desc: 'EU AI Act tier assessment per Annex III' },
  { icon: '🗺️', name: 'Planner',          desc: 'Decomposes query into research sub-questions' },
  { icon: '🔍', name: 'Researcher',        desc: 'Hybrid RAG + live web search via Tavily' },
  { icon: '⚖️', name: 'Analyst',           desc: 'Maps obligations to specific articles' },
  { icon: '🧠', name: 'Critic',            desc: 'GPT-4o cross-model verification' },
  { icon: '✍️', name: 'Synthesizer',       desc: 'Structured report with XAI traces' },
]

const STATS = [
  { value: '6',    label: 'AI Agents' },
  { value: '3',    label: 'Languages (EN/SV/DE)' },
  { value: '0.78', label: 'Answer Relevancy' },
  { value: 'EU',   label: 'Data Residency' },
]

const SAMPLE = {
  query: 'A Swedish HR startup is building a CV screening AI. What are their EU AI Act obligations?',
  riskLevel: 'HIGH RISK',
  articles: [
    { ref: 'EU AI Act Art. 6(2)', text: 'CV screening AI falls under Annex III — employment use. Classified as High-Risk system.' },
    { ref: 'EU AI Act Art. 9',    text: 'Mandatory risk management system must be established and maintained throughout the lifecycle.' },
    { ref: 'EU AI Act Art. 10',   text: 'Training data must be governed, relevant, representative, and free from discriminatory patterns.' },
    { ref: 'EU AI Act Art. 13',   text: 'System must be transparent and interpretable. Decision logic must be explainable to deployers.' },
    { ref: 'GDPR Art. 22',        text: 'Candidates have the right not to be subject to solely automated decisions with significant effects.' },
    { ref: 'GDPR Art. 13/14',     text: 'Candidates must be informed that an AI system is used in the hiring process.' },
  ],
  summary: 'As a provider of a High-Risk AI system under EU AI Act Annex III, your startup must register in the EU database before deployment, conduct conformity assessment, implement a risk management system, ensure human oversight mechanisms, and maintain technical documentation. Candidates must be able to request human review of any AI-assisted hiring decision.',
  agents: ['Risk Classifier ✓', 'Planner ✓', 'Researcher ✓', 'Analyst ✓', 'Critic ✓', 'Synthesizer ✓'],
  duration: '4m 12s',
  tokens: '18,420',
}

const STACK = [
  ['Orchestration',  'LangGraph 0.2',              'Auditable state machine — chosen over CrewAI for EU AI Act compliance'],
  ['LLMs',           'Claude Sonnet + GPT-4o',      'Cross-model critic: Claude judging Claude reduces adversarial coverage'],
  ['Embeddings',     'multilingual-e5-large',        'Open weights, EN/SV/DE, runs locally — no embedding API costs'],
  ['Vector DB',      'Supabase pgvector (EU N-1)',   'Single managed service; GDPR data residency built-in'],
  ['Backend',        'FastAPI + Python 3.13',        'Async throughout; GDPR Art.15 + Art.17 endpoints'],
  ['Frontend',       'React 18 + Vite + Tailwind',   'Supabase JWT/RLS auth; persistent sessions'],
  ['Infrastructure', 'AWS ECS Fargate eu-north-1',  'GitHub Actions CI/CD: test → build → deploy in ~8 min'],
  ['Audit',          'SHA-256 hash chain',            'Tamper-evident log over all processing events'],
]

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="lr">

      {/* NAV */}
      <nav className="lr-nav">
        <div className="lr-logo">
          <span className="lr-logo-flag">🇪🇺</span>
          <span className="lr-logo-name">RegulIQ</span>
          <span className="lr-logo-beta">BETA</span>
        </div>
        <div className="lr-nav-links">
          <a href="#demo" className="lr-nav-a">Demo</a>
          <a href="#how" className="lr-nav-a">How it works</a>
          <a href="#stack" className="lr-nav-a">Stack</a>
          <button className="lr-btn-nav" onClick={() => navigate('/auth')}>Sign in →</button>
        </div>
      </nav>

      {/* HERO */}
      <section className="lr-hero">
        <div className="lr-live-pill">
          <span className="lr-live-dot" />
          Live · AWS ECS Fargate · eu-north-1 (Stockholm)
        </div>
        <h1 className="lr-h1">
          EU AI Act &amp; GDPR<br />
          <span className="lr-h1-accent">compliance, automated.</span>
        </h1>
        <p className="lr-hero-sub">
          6 specialised LangGraph agents classify risk, retrieve obligations across English, Swedish,
          and German regulatory documents, cross-verify with GPT-4o, and produce a structured
          compliance report — in minutes.
        </p>
        <div className="lr-hero-btns">
          <button className="lr-btn-primary" onClick={() => navigate('/auth')}>Get started free →</button>
          <a
            href="https://github.com/Rishi-Bethi-007/EU-Regulatory-Intelligence-Agent"
            target="_blank" rel="noreferrer"
            className="lr-btn-outline"
          >View source ↗</a>
        </div>
        <div className="lr-stats">
          {STATS.map(s => (
            <div key={s.label} className="lr-stat">
              <div className="lr-stat-val">{s.value}</div>
              <div className="lr-stat-lbl">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* SAMPLE OUTPUT */}
      <section className="lr-section lr-section-gray" id="demo">
        <div className="lr-inner">
          <div className="lr-eyebrow">Sample output</div>
          <h2 className="lr-h2">See a real compliance report</h2>
          <p className="lr-sub">Actual output from the live system. Sign up to run your own query.</p>

          <div className="lr-report">
            {/* Query bar */}
            <div className="lr-report-query">
              <span className="lr-report-query-lbl">Query</span>
              <p className="lr-report-query-text">"{SAMPLE.query}"</p>
            </div>

            {/* Meta row */}
            <div className="lr-report-meta">
              <span className="lr-risk-badge">⚠️ {SAMPLE.riskLevel}</span>
              <div className="lr-agent-pills">
                {SAMPLE.agents.map(a => (
                  <span key={a} className="lr-agent-pill">{a}</span>
                ))}
              </div>
              <div className="lr-timings">
                <span>⏱ {SAMPLE.duration}</span>
                <span>·</span>
                <span>{SAMPLE.tokens} tokens</span>
              </div>
            </div>

            {/* Obligations */}
            <div className="lr-obligations">
              <div className="lr-obligations-lbl">Regulatory obligations identified</div>
              {SAMPLE.articles.map(a => (
                <div key={a.ref} className="lr-obligation">
                  <span className="lr-obligation-ref">{a.ref}</span>
                  <span className="lr-obligation-text">{a.text}</span>
                </div>
              ))}
            </div>

            {/* Summary */}
            <div className="lr-summary">
              <div className="lr-summary-lbl">✍️ Synthesiser output</div>
              <p className="lr-summary-text">{SAMPLE.summary}</p>
            </div>

            {/* Fade CTA */}
            <div className="lr-report-fade">
              <p className="lr-report-fade-text">Run a compliance analysis for your own scenario</p>
              <button className="lr-btn-primary" onClick={() => navigate('/auth')}>Sign up free →</button>
            </div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="lr-section" id="how">
        <div className="lr-inner">
          <div className="lr-eyebrow">Architecture</div>
          <h2 className="lr-h2">Six agents. One auditable pipeline.</h2>
          <p className="lr-sub">Every agent logs reasoning steps, confidence scores, and sources — satisfying EU AI Act Art. 13 transparency requirements.</p>
          <div className="lr-agents-grid">
            {AGENTS.map((a, i) => (
              <div key={a.name} className="lr-agent-card">
                <div className="lr-agent-num">0{i + 1}</div>
                <div className="lr-agent-icon">{a.icon}</div>
                <div className="lr-agent-name">{a.name}</div>
                <div className="lr-agent-desc">{a.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* STACK */}
      <section className="lr-section lr-section-gray" id="stack">
        <div className="lr-inner">
          <div className="lr-eyebrow">Production stack</div>
          <h2 className="lr-h2">Built for EU data residency and explainability.</h2>
          <p className="lr-sub">Every architectural decision is documented with rationale.</p>
          <div className="lr-stack">
            {STACK.map(([layer, tech, note]) => (
              <div key={layer} className="lr-stack-row">
                <span className="lr-stack-layer">{layer}</span>
                <span className="lr-stack-tech">{tech}</span>
                <span className="lr-stack-note">{note}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="lr-cta-section">
        <div className="lr-inner lr-cta-inner">
          <h2 className="lr-cta-h2">Ready to analyse your compliance obligations?</h2>
          <p className="lr-cta-sub">Free to use. Your data stays in the EU.</p>
          <button className="lr-btn-primary lr-btn-lg" onClick={() => navigate('/auth')}>Get started →</button>
          <div className="lr-cta-links">
            <a href="https://github.com/Rishi-Bethi-007/EU-Regulatory-Intelligence-Agent" target="_blank" rel="noreferrer" className="lr-cta-link">GitHub ↗</a>
            <a href="https://api.reguliq.eu/health" target="_blank" rel="noreferrer" className="lr-cta-link">API health ↗</a>
            <a href="https://api.reguliq.eu/docs" target="_blank" rel="noreferrer" className="lr-cta-link">API docs ↗</a>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="lr-footer">
        <span>Built by <a href="https://www.linkedin.com/in/rishi-kumar-bethi" target="_blank" rel="noreferrer" className="lr-footer-link">Rishi Kumar Bethi</a></span>
        <span>MSc AI &amp; Automation · University West · Trollhättan, Sweden</span>
        <span>Data stored in EU · AWS eu-north-1 · Supabase EU-N1</span>
      </footer>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

        * { box-sizing: border-box; margin: 0; padding: 0; }

        .lr {
          min-height: 100vh;
          background: transparent;
          color: #111827;
          font-family: 'Inter', sans-serif;
          -webkit-font-smoothing: antialiased;
        }

        /* NAV */
        .lr-nav {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 2.5rem;
          height: 64px;
          border-bottom: 1px solid rgba(193, 174, 143, 0.45);
          position: sticky;
          top: 0;
          background: rgba(248, 243, 234, 0.88);
          backdrop-filter: blur(8px);
          z-index: 100;
        }
        .lr-logo { display: flex; align-items: center; gap: 0.5rem; }
        .lr-logo-flag { font-size: 1.3rem; }
        .lr-logo-name {
          font-weight: 800;
          font-size: 1.1rem;
          letter-spacing: -0.03em;
          color: #111827;
        }
        .lr-logo-beta {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.58rem;
          background: #eff6ff;
          color: #2563eb;
          border: 1px solid #bfdbfe;
          padding: 0.15rem 0.4rem;
          border-radius: 4px;
          letter-spacing: 0.06em;
          font-weight: 500;
        }
        .lr-nav-links { display: flex; align-items: center; gap: 2rem; }
        .lr-nav-a {
          color: #6b7280;
          text-decoration: none;
          font-size: 0.875rem;
          font-weight: 500;
          transition: color 0.15s;
        }
        .lr-nav-a:hover { color: #111827; }
        .lr-btn-nav {
          background: #111827;
          color: #fff;
          border: none;
          padding: 0.5rem 1.1rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.15s;
          font-family: 'Inter', sans-serif;
        }
        .lr-btn-nav:hover { background: #1f2937; }

        /* HERO */
        .lr-hero {
          max-width: 800px;
          margin: 0 auto;
          padding: 5rem 2rem 4.5rem;
          text-align: center;
        }
        .lr-live-pill {
          display: inline-flex;
          align-items: center;
          gap: 0.45rem;
          background: #f0fdf4;
          border: 1px solid #bbf7d0;
          color: #15803d;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          padding: 0.3rem 0.85rem;
          border-radius: 100px;
          margin-bottom: 2rem;
          font-weight: 500;
        }
        .lr-live-dot {
          width: 6px; height: 6px;
          background: #22c55e;
          border-radius: 50%;
          animation: lr-pulse 2s infinite;
        }
        @keyframes lr-pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }
        .lr-h1 {
          font-size: clamp(2.2rem, 5.5vw, 3.75rem);
          font-weight: 800;
          line-height: 1.1;
          letter-spacing: -0.04em;
          color: #111827;
          margin-bottom: 1.25rem;
        }
        .lr-h1-accent { color: #2563eb; }
        .lr-hero-sub {
          color: #6b7280;
          font-size: 1.05rem;
          line-height: 1.7;
          max-width: 580px;
          margin: 0 auto 2.25rem;
          font-weight: 400;
        }
        .lr-hero-btns {
          display: flex;
          justify-content: center;
          gap: 0.75rem;
          margin-bottom: 3.5rem;
          flex-wrap: wrap;
        }
        .lr-btn-primary {
          background: #2563eb;
          color: #fff;
          border: none;
          padding: 0.75rem 1.75rem;
          border-radius: 8px;
          font-size: 0.95rem;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.15s;
          font-family: 'Inter', sans-serif;
          text-decoration: none;
          display: inline-block;
        }
        .lr-btn-primary:hover { background: #1d4ed8; }
        .lr-btn-lg { padding: 0.875rem 2.25rem; font-size: 1rem; }
        .lr-btn-outline {
          background: transparent;
          color: #374151;
          border: 1.5px solid #d1d5db;
          padding: 0.75rem 1.75rem;
          border-radius: 8px;
          font-size: 0.95rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s;
          text-decoration: none;
          display: inline-block;
        }
        .lr-btn-outline:hover { border-color: #9ca3af; color: #111827; }

        /* STATS */
        .lr-stats {
          display: flex;
          justify-content: center;
          gap: 3.5rem;
          flex-wrap: wrap;
          padding-top: 1rem;
          border-top: 1px solid #f3f4f6;
        }
        .lr-stat { text-align: center; }
        .lr-stat-val {
          font-size: 1.875rem;
          font-weight: 800;
          letter-spacing: -0.03em;
          color: #111827;
        }
        .lr-stat-lbl { color: #9ca3af; font-size: 0.78rem; margin-top: 0.2rem; font-weight: 500; }

        /* SECTIONS */
        .lr-section { padding: 5rem 2rem; }
        .lr-section-gray { background: rgba(255, 251, 243, 0.42); }
        .lr-inner { max-width: 900px; margin: 0 auto; }
        .lr-eyebrow {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.68rem;
          color: #2563eb;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          font-weight: 500;
          margin-bottom: 0.6rem;
        }
        .lr-h2 {
          font-size: 1.875rem;
          font-weight: 800;
          letter-spacing: -0.03em;
          color: #111827;
          margin-bottom: 0.6rem;
          line-height: 1.2;
        }
        .lr-sub { color: #6b7280; font-size: 0.95rem; margin-bottom: 2.25rem; line-height: 1.6; }

        /* REPORT CARD */
        .lr-report {
          background: rgba(255, 252, 247, 0.9);
          border: 1.5px solid rgba(196, 180, 150, 0.52);
          border-radius: 12px;
          overflow: hidden;
          position: relative;
          box-shadow: 0 1px 2px rgba(88, 68, 32, 0.05), 0 14px 40px rgba(131, 109, 72, 0.1);
          backdrop-filter: blur(8px);
        }
        .lr-report-query {
          padding: 1.25rem 1.5rem;
          border-bottom: 1px solid rgba(214, 198, 166, 0.5);
          background: rgba(250, 245, 236, 0.92);
        }
        .lr-report-query-lbl {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.62rem;
          color: #9ca3af;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          display: block;
          margin-bottom: 0.4rem;
          font-weight: 500;
        }
        .lr-report-query-text {
          color: #374151;
          font-size: 0.92rem;
          line-height: 1.5;
          font-style: italic;
        }
        .lr-report-meta {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.875rem 1.5rem;
          border-bottom: 1px solid #f3f4f6;
          flex-wrap: wrap;
        }
        .lr-risk-badge {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          font-weight: 600;
          padding: 0.3rem 0.65rem;
          border-radius: 5px;
          background: #fef2f2;
          color: #dc2626;
          border: 1px solid #fecaca;
          white-space: nowrap;
        }
        .lr-agent-pills { display: flex; gap: 0.3rem; flex-wrap: wrap; flex: 1; }
        .lr-agent-pill {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.63rem;
          color: #15803d;
          background: #f0fdf4;
          border: 1px solid #bbf7d0;
          padding: 0.2rem 0.45rem;
          border-radius: 4px;
          font-weight: 500;
        }
        .lr-timings {
          display: flex;
          gap: 0.35rem;
          color: #9ca3af;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.68rem;
          white-space: nowrap;
        }
        .lr-obligations {
          padding: 1.25rem 1.5rem;
          border-bottom: 1px solid #f3f4f6;
        }
        .lr-obligations-lbl {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.62rem;
          color: #9ca3af;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 0.875rem;
          font-weight: 500;
        }
        .lr-obligation {
          display: grid;
          grid-template-columns: 170px 1fr;
          gap: 1rem;
          padding: 0.6rem 0.75rem;
          border: 1px solid rgba(214, 198, 166, 0.5);
          border-radius: 6px;
          margin-bottom: 0.4rem;
          background: rgba(250, 245, 236, 0.9);
          font-size: 0.83rem;
          align-items: start;
        }
        .lr-obligation:last-child { margin-bottom: 0; }
        .lr-obligation-ref {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          color: #2563eb;
          font-weight: 500;
          padding-top: 0.05rem;
        }
        .lr-obligation-text { color: #4b5563; line-height: 1.45; }
        .lr-summary {
          padding: 1.25rem 1.5rem;
          padding-bottom: 9rem;
        }
        .lr-summary-lbl {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.62rem;
          color: #9ca3af;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 0.6rem;
          font-weight: 500;
        }
        .lr-summary-text { color: #4b5563; font-size: 0.88rem; line-height: 1.65; }
        .lr-report-fade {
          position: absolute;
          bottom: 0; left: 0; right: 0;
          background: linear-gradient(to bottom, transparent, rgba(248, 243, 234, 0.97) 35%);
          padding: 3.5rem 1.5rem 2rem;
          text-align: center;
        }
        .lr-report-fade-text { color: #6b7280; font-size: 0.875rem; margin-bottom: 0.875rem; }

        /* AGENTS GRID */
        .lr-agents-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 1rem;
        }
        .lr-agent-card {
          background: rgba(255, 252, 247, 0.88);
          border: 1.5px solid rgba(196, 180, 150, 0.52);
          border-radius: 10px;
          padding: 1.25rem;
          transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
          backdrop-filter: blur(8px);
        }
        .lr-agent-card:hover {
          border-color: #c9b48d;
          box-shadow: 0 12px 28px rgba(131, 109, 72, 0.12);
          transform: translateY(-1px);
        }
        .lr-agent-num {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.62rem;
          color: #d1d5db;
          margin-bottom: 0.75rem;
          font-weight: 500;
        }
        .lr-agent-icon { font-size: 1.4rem; margin-bottom: 0.5rem; }
        .lr-agent-name { font-weight: 700; font-size: 0.9rem; color: #111827; margin-bottom: 0.3rem; }
        .lr-agent-desc { color: #6b7280; font-size: 0.8rem; line-height: 1.45; }

        /* STACK */
        .lr-stack { background: rgba(255, 252, 247, 0.88); border: 1.5px solid rgba(196, 180, 150, 0.52); border-radius: 10px; overflow: hidden; backdrop-filter: blur(8px); }
        .lr-stack-row {
          display: grid;
          grid-template-columns: 140px 200px 1fr;
          gap: 1rem;
          padding: 0.875rem 1.25rem;
          border-bottom: 1px solid #f3f4f6;
          font-size: 0.85rem;
          align-items: start;
          transition: background 0.12s;
        }
        .lr-stack-row:last-child { border-bottom: none; }
        .lr-stack-row:hover { background: rgba(250, 245, 236, 0.9); }
        .lr-stack-layer {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          color: #9ca3af;
          font-weight: 500;
          padding-top: 0.1rem;
        }
        .lr-stack-tech { color: #111827; font-weight: 600; }
        .lr-stack-note { color: #6b7280; font-size: 0.8rem; line-height: 1.4; }

        /* CTA SECTION */
        .lr-cta-section {
          background: rgba(244, 237, 225, 0.72);
          border-top: 1px solid rgba(196, 180, 150, 0.42);
          padding: 5rem 2rem;
        }
        .lr-cta-inner { text-align: center; }
        .lr-cta-h2 {
          font-size: 2rem;
          font-weight: 800;
          letter-spacing: -0.03em;
          color: #111827;
          margin-bottom: 0.6rem;
        }
        .lr-cta-sub { color: #6b7280; margin-bottom: 1.75rem; font-size: 0.95rem; }
        .lr-cta-links {
          display: flex;
          justify-content: center;
          gap: 2rem;
          margin-top: 1.5rem;
        }
        .lr-cta-link {
          color: #6b7280;
          font-size: 0.85rem;
          text-decoration: none;
          transition: color 0.15s;
          font-weight: 500;
        }
        .lr-cta-link:hover { color: #2563eb; }

        /* FOOTER */
        .lr-footer {
          border-top: 1px solid rgba(196, 180, 150, 0.42);
          padding: 1.75rem 2rem;
          display: flex;
          justify-content: center;
          gap: 2.5rem;
          flex-wrap: wrap;
          color: #9ca3af;
          font-size: 0.78rem;
          background: rgba(255, 252, 247, 0.74);
          backdrop-filter: blur(8px);
        }
        .lr-footer-link { color: #6b7280; text-decoration: none; }
        .lr-footer-link:hover { color: #2563eb; }

        @media (max-width: 768px) {
          .lr-nav { padding: 0 1.25rem; }
          .lr-nav-links .lr-nav-a { display: none; }
          .lr-hero { padding: 3.5rem 1.25rem 3rem; }
          .lr-stats { gap: 2rem; }
          .lr-obligation { grid-template-columns: 1fr; gap: 0.2rem; }
          .lr-stack-row { grid-template-columns: 1fr; gap: 0.15rem; }
          .lr-stack-note { display: none; }
          .lr-footer { flex-direction: column; align-items: center; gap: 0.4rem; text-align: center; }
          .lr-report-meta { gap: 0.5rem; }
        }
      `}</style>
    </div>
  )
}
