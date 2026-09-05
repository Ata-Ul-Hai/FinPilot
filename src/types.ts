export type View = 'close' | 'review' | 'policies' | 'evaluation' | 'commentary'

export type RawRow = Record<string, string | number | null>

export type Transaction = {
  id: string
  source: 'bank' | 'gl'
  date: string
  amount: number
  currency: string
  counterparty: string
  reference: string
  raw: RawRow
}

export type FieldScores = {
  amount: number
  date_proximity: number
  counterparty: number
  reference: number
}

export type CandidateRow = { id: string; source: 'bank' | 'gl'; raw: RawRow }

export type Evidence = {
  field_scores: FieldScores
  reasons: string[]
  counterfactual: string
  source_rows: Record<string, RawRow>
  candidate_rows?: CandidateRow[]
}

export type MatchDecision = {
  pair: [string, string] | null
  items?: string[]
  status: 'matched' | 'exception'
  method: 'exact' | 'rule' | 'fuzzy' | 'llm'
  confidence: number
  evidence: Evidence
}

export type ExceptionKind = 'TIMING_DIFF' | 'DUPLICATE' | 'MISSING_ENTRY' | 'AMOUNT_MISMATCH' | 'COUNTERPARTY_MISMATCH' | 'UNKNOWN'

export type CloseException = {
  id: string
  kind: ExceptionKind
  primary_kind: ExceptionKind
  secondary_tags: string[]
  items: string[]
  disposition: 'auto_resolved' | 'needs_review' | 'escalated'
  suggestion: string
  confidence: number
  evidence: Evidence
}

export type PolicyRule = { fuzzy_threshold: number; amount_tolerance: number; date_grace_days: number }
export type Policy = {
  id: string
  version: number
  rule: PolicyRule
  created_by: string
  diff_vs_previous: Record<string, [number, number]>
  eval_impact: Record<string, [number, number]>
}

export type ReviewRule = {
  policy_id: string
  applicable_kinds: ExceptionKind[]
  amount_cap: number
  min_confidence: number
  allow_bulk: boolean
}

export type CloseRun = {
  run_id: string
  counts: { bank: number; gl: number; matched: number; exceptions: number; auto_resolved: number; in_inbox: number }
  checklist: { task: string; status: 'done' | 'in_review' | 'open' }[]
  je_drafts: { for: string; entry: { dr: string; cr: string; amount: number } }[]
}

export type EvalMetrics = {
  policy_version: number
  precision: number
  recall: number
  f1: number
  false_auto_closes: number
  inbox_size: number
  classification_accuracy: Partial<Record<ExceptionKind, number>>
}
export type EvalComparison = { baseline: EvalMetrics; current: EvalMetrics }

export type CommentaryLine = {
  id: string
  title: string
  body: string
  evidence_refs: string[]
  tone: 'info' | 'review' | 'positive'
}

export type WorkspaceSnapshot = {
  run: CloseRun
  transactions: Transaction[]
  decisions: MatchDecision[]
  exceptions: CloseException[]
  policies: Policy[]
  review_rules: ReviewRule[]
  evaluation: EvalComparison
  commentary: CommentaryLine[]
}

export type ReviewResult = { exception: CloseException; policy: Policy | null; evaluation: EvalComparison }
