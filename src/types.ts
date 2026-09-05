export type View = 'close' | 'review' | 'policies' | 'evaluation'

export type Transaction = {
  id: string
  source: 'bank' | 'gl'
  date: string
  amount: number
  currency: string
  counterparty: string
  reference: string
  raw: Record<string, string>
}

export type Evidence = {
  field_scores: Record<string, number>
  reasons: string[]
  counterfactual: string
}

export type MatchDecision = {
  pair: [Transaction, Transaction]
  status: 'matched' | 'exception'
  method: 'exact' | 'rule' | 'fuzzy' | 'llm'
  confidence: number
  evidence: Evidence
}

export type ExceptionKind =
  | 'TIMING_DIFF'
  | 'DUPLICATE'
  | 'MISSING_ENTRY'
  | 'AMOUNT_MISMATCH'
  | 'COUNTERPARTY_MISMATCH'
  | 'UNKNOWN'

export type CloseException = {
  id: string
  kind: ExceptionKind
  primary_kind: ExceptionKind
  secondary_tags: string[]
  items: string[]
  disposition: 'auto_resolved' | 'needs_review' | 'escalated'
  suggestion: string
  confidence: number
  amount: number
  policyCovered: boolean
  evidence: Evidence
}
