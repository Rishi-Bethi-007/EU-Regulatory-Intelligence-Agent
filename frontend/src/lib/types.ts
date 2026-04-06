export type RiskLevel = 'UNACCEPTABLE' | 'HIGH_RISK' | 'LIMITED_RISK' | 'MINIMAL_RISK'

export interface ResearchRun {
  id:                   string
  goal:                 string
  status:               'pending' | 'running' | 'completed' | 'failed'
  result:               string | null
  risk_level:           RiskLevel | null
  risk_justification:   string | null
  transparency_score:   number | null
  transparency_notice:  string | null
  token_count:          number | null
  cost_usd:             number | null
  duration_ms:          number | null
  error:                string | null
  created_at:           string
  user_id:              string | null
}

export interface AgentTask {
  id:               string
  agent_name:       string
  status:           'pending' | 'running' | 'completed' | 'failed'
  started_at:       string | null
  completed_at:     string | null
  error:            string | null
  decision_trace:   DecisionTrace | null
  output:           Record<string, unknown> | null
  tool_calls:       ToolCallLog[] | null
}

export interface DecisionTrace {
  agent_name:            string
  confidence:            number
  reasoning_steps:       string[]
  sources_used:          string[]
  alternatives_considered: string[]
  counterfactual:        string
  duration_ms:           number
}

export interface ToolCallLog {
  tool:        string
  input:       Record<string, unknown>
  output_len:  number
  latency_ms:  number
  success:     boolean
  error:       string | null
}

export interface Document {
  id:          string
  title:       string
  language:    'en' | 'sv' | 'de'
  doc_type:    string
  chunk_count: number
  source_url:  string | null
  created_at:  string
}

export interface EvalScore {
  id:               string
  research_run_id:  string
  factual_accuracy: number
  completeness:     number
  citation_quality: number
  eu_relevance:     number
  overall_score:    number
  evaluated_at:     string
}

// Risk level display config
export const RISK_CONFIG: Record<RiskLevel, { color: string; bg: string; emoji: string; label: string }> = {
  UNACCEPTABLE: { color: '#ff4444', bg: '#3d1a1a', emoji: '🚫', label: 'UNACCEPTABLE — Prohibited under Art. 5' },
  HIGH_RISK:    { color: '#ff8800', bg: '#3d2a0a', emoji: '🔴', label: 'HIGH RISK — Full obligations (Annex III)' },
  LIMITED_RISK: { color: '#ffcc00', bg: '#3d3a0a', emoji: '🟡', label: 'LIMITED RISK — Transparency obligations' },
  MINIMAL_RISK: { color: '#44cc44', bg: '#0a3d1a', emoji: '🟢', label: 'MINIMAL RISK — No specific obligations' },
}
