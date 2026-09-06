import { describe, expect, it } from 'vitest'
import { bulkApprovalGate, evidenceAmount } from './trustGate'
import type { CloseException, ReviewRule } from './types'

const rule: ReviewRule = { policy_id: 'SHORT-PAY', applicable_kinds: ['AMOUNT_MISMATCH'], amount_cap: 0.5, min_confidence: 0.95, allow_bulk: true }
const item = (overrides: Partial<CloseException> = {}): CloseException => ({
  id: 'EX-1', kind: 'AMOUNT_MISMATCH', primary_kind: 'AMOUNT_MISMATCH', secondary_tags: [], items: ['BNK-1', 'GL-1'],
  disposition: 'needs_review', suggestion: 'Review short pay.', confidence: 0.98,
  evidence: { field_scores: { amount: 0.9, date_proximity: 1, counterparty: 1, reference: 1 }, reasons: ['Amount differs.'], counterfactual: 'Outside exact tolerance.', source_rows: { bank: { amount: '-0.30' }, gl: { amount: '0.30' } } },
  ...overrides,
})

describe('bulkApprovalGate', () => {
  it('uses the absolute evidence amount for signed values', () => {
    expect(evidenceAmount(item())).toBe(0.3)
    expect(bulkApprovalGate(item(), [rule]).eligible).toBe(true)
    expect(bulkApprovalGate(item({ evidence: { ...item().evidence, source_rows: { bank: { amount: '-0.75' } } } }), [rule]).eligible).toBe(false)
  })

  it('requires an explicit applicable policy and cap', () => {
    expect(bulkApprovalGate(item(), []).eligible).toBe(false)
    expect(bulkApprovalGate(item(), [{ ...rule, allow_bulk: false }]).eligible).toBe(false)
  })

  it('uses the reclassified primary kind rather than the stale kind', () => {
    const reclassified = item({ kind: 'AMOUNT_MISMATCH', primary_kind: 'DUPLICATE' })
    expect(bulkApprovalGate(reclassified, [rule])).toEqual({ eligible: false, reason: 'Duplicates always require individual controller approval.' })
  })

  it('enforces confidence and disposition', () => {
    expect(bulkApprovalGate(item({ confidence: 0.94 }), [rule]).eligible).toBe(false)
    expect(bulkApprovalGate(item({ disposition: 'escalated' }), [rule]).eligible).toBe(false)
  })
})
