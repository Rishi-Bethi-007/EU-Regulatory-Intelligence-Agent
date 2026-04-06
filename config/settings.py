import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# ── Supabase ───────────────────────────────────────────────────
SUPABASE_URL         = os.environ.get("SUPABASE_URL")
SUPABASE_KEY         = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_ANON_KEY    = os.environ.get("SUPABASE_ANON_KEY")

# ── LLM models ────────────────────────────────────────────────
# Model routing strategy:
#   Planner      → Claude Opus   — routing decisions affect the whole run
#   Researcher   → Claude Sonnet — fast, high quality retrieval + synthesis
#   Analyst      → Claude Sonnet — structured extraction
#   Critic       → GPT-4o        — cross-model judge is more credible than
#                                  using Claude to judge Claude's own outputs
#   Synthesizer  → Claude Sonnet — report writing
ANTHROPIC_API_KEY     = os.environ.get("ANTHROPIC_API_KEY")
# PLANNER_MODEL         = "claude-opus-4-5"       # routing + decomposition
PLANNER_MODEL = "claude-sonnet-4-5"   # switch back to opus before final demo
LLM_MODEL             = "claude-sonnet-4-5"     # researcher, analyst, synthesizer
CRITIC_MODEL          = "gpt-4o"                # cross-model judge — back to GPT-4o

# ── Cost per token ────────────────────────────────────────────
# Opus pricing
OPUS_INPUT_COST_PER_TOKEN   = 15.00 / 1_000_000
OPUS_OUTPUT_COST_PER_TOKEN  = 75.00 / 1_000_000
# Sonnet pricing
INPUT_COST_PER_TOKEN        = 3.00  / 1_000_000
OUTPUT_COST_PER_TOKEN       = 15.00 / 1_000_000
# GPT-4o pricing
GPT4O_INPUT_COST_PER_TOKEN  = 5.00  / 1_000_000
GPT4O_OUTPUT_COST_PER_TOKEN = 15.00 / 1_000_000

# ── Search ────────────────────────────────────────────────────
TAVILY_API_KEY       = os.environ.get("TAVILY_API_KEY")

# ── Embeddings ────────────────────────────────────────────────
EMBEDDING_MODEL      = "intfloat/multilingual-e5-large"
EMBEDDING_DIMENSIONS = 1024

# ── Retrieval ─────────────────────────────────────────────────
DEFAULT_MATCH_THRESHOLD = 0.7
DEFAULT_MATCH_COUNT     = 5

# ── Multi-agent retry logic ────────────────────────────────────
MAX_RETRIES           = 2
CONFIDENCE_THRESHOLD  = 0.7

# ── Chunking ──────────────────────────────────────────────────
CHUNKING_STRATEGY             = "semantic"
CHUNK_SIZE_FALLBACK           = 512
CHUNK_OVERLAP_FALLBACK        = 50
SEMANTIC_BREAKPOINT_TYPE      = "percentile"
SEMANTIC_BREAKPOINT_THRESHOLD = 95

# ── Observability ─────────────────────────────────────────────
LANGCHAIN_API_KEY    = os.environ.get("LANGCHAIN_API_KEY")
LANGCHAIN_PROJECT    = os.environ.get("LANGCHAIN_PROJECT", "eu-reg-agent")
LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", "true")

# ── Environment ───────────────────────────────────────────────
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")


def validate():
    required = {
        "SUPABASE_URL":      SUPABASE_URL,
        "SUPABASE_KEY":      SUPABASE_KEY,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "OPENAI_API_KEY":    OPENAI_API_KEY,
        "TAVILY_API_KEY":    TAVILY_API_KEY,
        "LANGCHAIN_API_KEY": LANGCHAIN_API_KEY,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")
