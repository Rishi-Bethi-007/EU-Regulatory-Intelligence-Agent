# EU Regulatory Intelligence Agent

> **Live demo:** [reguliq.eu](https://www.reguliq.eu) &nbsp;·&nbsp; **API:** [api.reguliq.eu/health](https://api.reguliq.eu/health) &nbsp;·&nbsp; **Stack:** LangGraph · FastAPI · React/Vite · Supabase pgvector · AWS ECS Fargate

## Why this exists

EU AI Act and GDPR compliance is a growing burden for European SMEs — the regulations are complex, multilingual, and change frequently, yet most small businesses have no dedicated legal or compliance resource. This system automates the first and most time-consuming step: understanding what specific obligations apply to a given AI use case, cited to the actual regulatory articles, in plain language. It was built as a production portfolio project by an MSc AI & Automation student at University West, Sweden, targeting AI Engineer roles and research internships at Swedish and European organisations for autumn 2026.

---

A production-grade **multi-agent AI system** that helps European SMEs navigate GDPR and EU AI Act obligations. Six specialised LangGraph agents classify risk, retrieve obligations across English, Swedish, and German regulatory documents, cross-verify with GPT-4o, and produce a structured compliance report in minutes.

---

## Demo

| Step | Description |
|---|---|
| 1 | Enter a business scenario (e.g. *"A Swedish HR startup is building a CV screening AI — what are their EU AI Act obligations?"*) |
| 2 | 6 LangGraph agents run in sequence: classify risk → plan research → retrieve regulatory docs → analyse obligations → critique → synthesise |
| 3 | Receive a structured compliance report with risk classification, cited regulatory articles, XAI decision traces, and PDF export |

**Example query:** *"A German fintech wants to use AI for credit scoring. What GDPR and EU AI Act obligations apply?"*

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph Orchestrator                  │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │Risk Classifier│───▶│   Planner    │───▶│ Researcher│ │
│  │  (EU AI Act) │    │ (sub-queries)│    │ (RAG+MCP) │ │
│  └──────────────┘    └──────────────┘    └─────┬─────┘ │
│                                                 │       │
│  ┌──────────────┐    ┌──────────────┐    ┌─────▼─────┐ │
│  │ Synthesizer  │◀───│    Critic    │◀───│  Analyst  │ │
│  │ (GPT-4o XAI) │    │ (GPT-4o judge│    │(obligations│ │
│  └──────────────┘    └──────────────┘    └───────────┘ │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Supabase pgvector (EU North-1)                         │
│  Hybrid retrieval: dense (multilingual-e5-large) +      │
│  sparse (BM25/FTS) with HNSW indexing                   │
│  10-doc multilingual corpus: EN · SV · DE               │
└─────────────────────────────────────────────────────────┘
```

### Agent Pipeline

| Agent | Model | Role |
|---|---|---|
| **Risk Classifier** | Claude Sonnet | Determines EU AI Act risk tier (Unacceptable / High / Limited / Minimal) |
| **Planner** | Claude Sonnet | Decomposes query into regulatory research sub-questions |
| **Researcher** | Claude Sonnet + MCP | Hybrid RAG retrieval + live web search via Tavily MCP |
| **Analyst** | Claude Sonnet | Maps obligations to specific EU AI Act / GDPR articles |
| **Critic** | GPT-4o | Cross-model verification — challenges weak claims, flags gaps |
| **Synthesizer** | Claude Sonnet | Produces structured report with citations, Mermaid diagrams, XAI traces |

### Custom MCP Servers

- **`scraper_mcp.py`** — Fetches and cleans EUR-Lex regulatory source pages
- **`citation_mcp.py`** — Formats and validates regulatory citations against article index

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Orchestration** | LangGraph 0.2 | Auditable state machine; preferred over CrewAI for EU AI Act compliance |
| **LLMs** | Claude Sonnet 4.5 · GPT-4o | Cross-model critic for credible verification |
| **Embeddings** | `intfloat/multilingual-e5-large` | Open weights, 1024 dims, EN/SV/DE multilingual, runs locally |
| **Vector DB** | Supabase pgvector (EU North-1) | Single managed service; simplifies GDPR data residency |
| **Retrieval** | Hybrid dense + sparse (HNSW + FTS) | Higher recall on OCR-degraded EUR-Lex PDFs |
| **Backend** | FastAPI + Python 3.13 | Async throughout; UV package manager |
| **Frontend** | React 18 + Vite + TypeScript + Tailwind | Auth via Supabase; production sessions |
| **Deployment** | AWS ECS Fargate (eu-north-1) + ECR | Cloud-native; no raw VM management |
| **Frontend CDN** | Vercel | Global edge; auto-deploys from `main` |
| **CI/CD** | GitHub Actions | 3-job pipeline: test → build → deploy (~8 min) |
| **Observability** | LangSmith | Full agent trace visibility |
| **Evaluation** | Custom RAGAS-equivalent + GPT-4o judge | Direct evaluation, avoids RAGAS Windows threading issues |

---

## RAG Evaluation Results

Evaluated on 20 multilingual QA pairs (EN/SV/DE) covering EU AI Act and GDPR.
Judge: `claude-haiku-4-5`. Retrieval: hybrid HNSW + FTS, top-k=15.

| Metric | Score | Notes |
|---|---|---|
| **Faithfulness** | 0.48 | Ceiling limited by OCR-degraded EUR-Lex PDF source text |
| **Context Precision** | 0.59 | Hybrid retrieval improves on dense-only baseline |
| **Answer Relevancy** | 0.78 | Strong — answers are on-topic and actionable |
| **Passed target (0.75)** | ❌ | Faithfulness bottleneck; known trade-off documented |

**LLM-as-Judge (GPT-4o)** across 5 dimensions:

| Dimension | Score |
|---|---|
| Regulatory accuracy | 0.72 |
| Completeness | 0.68 |
| Clarity | 0.74 |
| Citation quality | 0.48 |
| Actionability | 0.63 |
| **Overall** | **0.65** |

> Citation quality (0.48) is the weakest dimension — a known gap from OCR-degraded EUR-Lex source material.

---

## Key Features

- **EU AI Act risk classification** — Four-tier risk assessment (Unacceptable / High / Limited / Minimal) per Annex III
- **Multilingual RAG** — Retrieves and reasons across EN, SV, and DE regulatory documents
- **XAI decision traces** — Every agent logs reasoning steps, confidence, sources, and counterfactual (EU AI Act Art. 13)
- **GDPR compliance module** — Art. 15 (data access) and Art. 17 (right to erasure) endpoints with tamper-evident SHA-256 audit chain
- **PDF export** — Zero-dependency browser-print with pre-rendered Mermaid diagrams, risk badge, cover page
- **Tamper-evident audit log** — SHA-256 hash chain over all processing events; verifiable via `/api/audit/verify`

---

## Project Structure

```
eu-regulatory-intelligence-agent/
├── agents/
│   ├── orchestrator.py        # LangGraph graph definition
│   ├── risk_classifier.py
│   ├── planner.py
│   ├── researcher.py          # Hybrid RAG + MCP tool calls
│   ├── analyst.py
│   ├── critic.py              # GPT-4o cross-model verification
│   └── synthesizer.py
├── api/
│   ├── main.py                # FastAPI app
│   └── routes.py              # GDPR Art. 15/17 + audit endpoints
├── tools/
│   ├── scraper_mcp.py         # Custom MCP server — EUR-Lex scraper
│   └── citation_mcp.py        # Custom MCP server — citation formatter
├── rag/
│   └── retriever.py           # HybridRetriever (pgvector + FTS)
├── db/
│   └── client.py              # Supabase async client + audit chain
├── frontend/
│   └── src/
│       ├── pages/             # 6 pages: Home, Research, Reports, Documents, Evals, GDPR
│       └── components/
├── scripts/
│   ├── ingest_demo_corpus.py  # Ingest 10-doc multilingual corpus
│   └── run_ragas_baseline.py  # RAG evaluation
├── evals/                     # DeepEval integration
├── Dockerfile
└── .github/workflows/deploy.yml  # GitHub Actions CI/CD
```

---

## Local Setup

### Prerequisites

- Python 3.13+
- [UV](https://github.com/astral-sh/uv) package manager
- Node.js 20+
- Supabase project (pgvector enabled)
- API keys: Anthropic, OpenAI, Tavily, LangSmith (optional)

### 1. Clone and install

```bash
git clone https://github.com/Rishi-Bethi-007/EU-Regulatory-Intelligence-Agent.git
cd EU-Regulatory-Intelligence-Agent
uv sync
```

### 2. Environment variables

Create `.env` in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<service_role_key>
LANGCHAIN_API_KEY=ls__...          # optional — LangSmith tracing
LANGCHAIN_TRACING_V2=true
```

Create `frontend/.env.local`:

```env
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon_key>
VITE_API_URL=http://localhost:8000
```

### 3. Database setup

Run in Supabase SQL Editor:

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Apply migrations
-- (See scripts/sql/ for all schema files)
```

### 4. Ingest the demo corpus

```bash
uv run python scripts/ingest_demo_corpus.py
```

This ingests 10 documents (EN/SV/DE) covering EU AI Act, GDPR, and national guidance. Embedding takes ~3 minutes on CPU.

### 5. Run locally

**Backend:**
```bash
uv run uvicorn api.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**CLI (single run without frontend):**
```bash
uv run python main.py "A Swedish HR startup is building a CV screening AI. What are their EU AI Act obligations?"
```

### 6. Run RAG evaluation

```bash
uv run python scripts/run_ragas_baseline.py
```

---

## Deployment

### Infrastructure

| Component | Service | Region |
|---|---|---|
| Backend container | AWS ECS Fargate | eu-north-1 (Stockholm) |
| Container registry | AWS ECR | eu-north-1 |
| Load balancer | AWS ALB | eu-north-1 |
| Frontend | Vercel | Global edge |
| Database | Supabase | EU North-1 |

### CI/CD

GitHub Actions runs on every push to `main`:
1. **Test** — `pytest` on core agent logic
2. **Build** — Docker image → ECR push
3. **Deploy** — ECS Fargate service update with rolling deployment

Total pipeline: ~8 minutes.

### Manual deploy

```bash
# Build and push
docker build -t eu-reg-agent .
aws ecr get-login-password --region eu-north-1 | docker login --username AWS --password-stdin 719982590161.dkr.ecr.eu-north-1.amazonaws.com
docker tag eu-reg-agent:latest 719982590161.dkr.ecr.eu-north-1.amazonaws.com/eu-reg-agent:latest
docker push 719982590161.dkr.ecr.eu-north-1.amazonaws.com/eu-reg-agent:latest

# Deploy
aws ecs update-service --cluster eu-reg-agent --service eu-reg-agent-service --force-new-deployment --region eu-north-1
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/research` | Start a research run |
| `GET` | `/api/research/{id}` | Get run status and result |
| `GET` | `/api/research/{id}/agents` | Get per-agent task details and XAI traces |
| `GET` | `/api/evals` | Get RAGAS evaluation scores |
| `GET` | `/api/audit/verify` | Verify SHA-256 audit chain integrity |
| `DELETE` | `/api/users/{id}/data` | GDPR Art. 17 — right to erasure |
| `GET` | `/api/users/{id}/data` | GDPR Art. 15 — right of access |

---

## Design Decisions

**LangGraph over CrewAI** — LangGraph produces an auditable state machine with explicit node transitions. For an EU AI Act compliance tool this is a feature, not a constraint: every state transition is logged, inspectable, and reproducible.

**GPT-4o as critic** — Claude judging Claude outputs reduces adversarial coverage. Cross-model verification is more credible and catches model-specific blind spots.

**multilingual-e5-large over OpenAI embeddings** — Open weights, runs locally, genuinely multilingual across EN/SV/DE without language-specific fine-tuning. Eliminates embedding API costs and data residency concerns.

**Supabase pgvector over Qdrant** — Single managed service in EU North-1 handles auth, RLS, vector search, and relational data. Eliminates a separate vector DB service and simplifies GDPR data residency.

**ECS Fargate over EC2** — Demonstrates cloud-native container orchestration skills without raw VM management. Scales to zero between demo runs.

**React/Vite over Streamlit** — Production auth with persistent sessions, proper JWT/RLS integration, and Mermaid rendering require a real frontend framework. Streamlit has fundamental architectural limitations around auth state.

---

## Known Limitations

- **Faithfulness score (0.48)** is ceiling-limited by OCR-degraded text in EUR-Lex PDFs. The actual regulatory reasoning quality is higher than this metric suggests.
- **Citation quality (0.48 LLM-judge)** — citations exist but are not always pinned to exact article paragraphs. Addressed in a future ingestion pass with cleaner PDF parsing.
- **ECS cold start** — The multilingual embedding model takes ~60s to load. ECS health check grace period is set to 120s.

---

## Future Development

Features planned for future iterations, roughly in priority order:

**User document upload** — Allow users to optionally upload their own documents (PDF, DOCX) describing how they use AI in their organisation. The researcher agent would incorporate this alongside the regulatory corpus to produce compliance analysis grounded in the user's specific context, not just a generic business scenario. This is the highest-value UX improvement for real SME users.

**Cleaner EUR-Lex ingestion** — Re-ingest the regulatory corpus using a proper PDF parser (pdfplumber or pymupdf) rather than the current OCR-degraded text. This is the single fix that would most improve faithfulness scores and citation quality.

**Expanded corpus** — Add national AI strategies and guidance from Sweden (IMY), Germany (BfDI), and the EU AI Office. Increase corpus from 10 to 50+ documents. Add French and Dutch regulatory guidance.

**Streaming agent output** — Stream each agent's output to the frontend in real time rather than polling every 2 seconds. Significantly improves perceived latency for the 3–6 minute run time.

**Saved compliance profiles** — Allow users to save their organisation profile (industry, size, country, AI use cases) so they don't need to re-describe their context on every query. Pre-fills the research goal with context automatically.

**Obligation tracking** — Let users mark obligations as "acknowledged", "in progress", or "completed" and track their compliance posture over time across multiple queries.

**Citation pinpointing** — Pin citations to exact article paragraphs rather than article-level references. Requires cleaner ingestion and chunk-level metadata improvements.

**Multi-jurisdiction support** — Extend beyond Sweden and Germany to cover French, Dutch, and Polish national implementation of the EU AI Act.

**API access tier** — Expose the research pipeline as a public REST API for developers and compliance tools to integrate directly.

---

## Author

**Rishi Bethi** — MSc AI & Automation, University West (Trollhättan, Sweden)

Built as a production portfolio project targeting AI Engineer roles and research internships at Swedish/European companies and RISE Research Institutes, autumn 2026.

- GitHub: [Rishi-Bethi-007](https://github.com/Rishi-Bethi-007)
- Live: [reguliq.eu](https://www.reguliq.eu)
- LinkedIn: [linkedin.com/in/rishi-kumar-bethi](https://www.linkedin.com/in/rishi-kumar-bethi)
