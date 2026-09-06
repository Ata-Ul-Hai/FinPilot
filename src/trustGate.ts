import type { CloseException, ReviewRule } from './types'

const amountKeys = new Set(['amount', 'signed_amount', 'debit', 'credit', 'transaction_amount', 'net_amount'])

const parseAmount = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string' || !value.trim()) return null
  const normalized = value.trim().replace(/[$,\s]/g, '').replace(/^\((.*)\)$/, '-$1')
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

export function evidenceAmount(item: CloseException): number | null {
  const amounts: number[] = []
  Object.values(item.evidence.source_rows).forEach((row) => {
    Object.entries(row).forEach(([key, value]) => {
      if (!amountKeys.has(key.toLowerCase())) return
      const parsed = parseAmount(value)
      if (parsed !== null) amounts.push(Math.abs(parsed))
    })
  })
  return amounts.length ? Math.max(...amounts) : null
}

export type GateResult = { eligible: true; rule: ReviewRule; amount: number } | { eligible: false; reason: string }

export function bulkApprovalGate(item: CloseException, rules: ReviewRule[]): GateResult {
  if (item.disposition !== 'needs_review') return { eligible: false, reason: 'Item is not awaiting review.' }
  if (item.primary_kind === 'DUPLICATE') return { eligible: false, reason: 'Duplicates always require individual controller approval.' }
  const amount = evidenceAmount(item)
  if (amount === null) return { eligible: false, reason: 'Evidence does not contain a traceable amount.' }
  const rule = rules.find((candidate) => candidate.allow_bulk && candidate.applicable_kinds.includes(item.primary_kind))
  if (!rule) return { eligible: false, reason: `No bulk-review policy covers ${item.primary_kind}.` }
  if (item.confidence < rule.min_confidence) return { eligible: false, reason: `Confidence is below ${Math.round(rule.min_confidence * 100)}%.` }
  if (Math.abs(amount) > rule.amount_cap) return { eligible: false, reason: `Amount exceeds ${rule.policy_id}'s ${rule.amount_cap.toFixed(2)} cap.` }
  return { eligible: true, rule, amount: Math.abs(amount) }
}
