import type { CloseException, Evidence, MatchDecision, Transaction, WorkspaceSnapshot } from './types'

const transaction = (id: string, source: 'bank' | 'gl', date: string, amount: number, counterparty: string, reference: string): Transaction => ({
  id, source, date, amount, currency: 'USD', counterparty, reference,
  raw: source === 'bank'
    ? { posted_on: date, description: counterparty, amount: amount.toFixed(2), bank_ref: reference }
    : { journal_date: date, account: '1010 Cash', memo: counterparty, signed_amount: amount.toFixed(2), document_no: reference },
})

const transactions = [
  transaction('BNK-0007', 'bank', '2026-08-31', -1234.56, 'Acme Freight', 'INV-4471'),
  transaction('GL-0031', 'gl', '2026-08-31', -1234.56, 'Acme Freight', 'INV-4471'),
  transaction('BNK-0018', 'bank', '2026-08-28', -8420, 'Northline Logistics', 'PAY-8204'),
  transaction('GL-0048', 'gl', '2026-08-28', -8420, 'Northline Logistics LLC', 'PAY-8204'),
  transaction('BNK-0026', 'bank', '2026-08-26', 18450, 'Redwood Retail', 'DEP-1802'),
  transaction('GL-0057', 'gl', '2026-08-26', 18450, 'Redwood Retail', 'DEP-1802'),
  transaction('BNK-0041', 'bank', '2026-08-22', -2210.45, 'Meridian Cloud', 'INV-9310'),
  transaction('GL-0069', 'gl', '2026-08-22', -2210.45, 'Meridian Cloud Inc', 'INV-9310'),
  transaction('BNK-0059', 'bank', '2026-08-18', -776.25, 'Bright Office Co', 'INV-5519'),
  transaction('GL-0078', 'gl', '2026-08-18', -776.25, 'Bright Office Company', 'INV-5519'),
]

const byId = new Map(transactions.map((item) => [item.id, item]))
const evidenceForPair = (bankId: string, glId: string, counterparty: number, method: MatchDecision['method']): Evidence => ({
  field_scores: { amount: 1, date_proximity: 1, counterparty, reference: 1 },
  reasons: ['amount exact', 'date exact', `counterparty similarity ${counterparty.toFixed(2)}`, 'reference similarity 1.00'],
  counterfactual: `would not auto-match if ${method} requirements or policy v1 thresholds were not met`,
  source_rows: { bank: byId.get(bankId)!.raw, gl: byId.get(glId)!.raw },
})
const decision = (bankId: string, glId: string, method: MatchDecision['method'], confidence: number, counterparty = 1): MatchDecision => ({
  pair: [bankId, glId], status: 'matched', method, confidence, evidence: evidenceForPair(bankId, glId, counterparty, method),
})

const exceptionEvidence = (amount: number, found: string, flagged: string, counterfactual: string): Evidence => ({
  field_scores: { amount: 1, date_proximity: 0.6, counterparty: 0.72, reference: 0.5 },
  reasons: [found, flagged], counterfactual,
  source_rows: { bank: { amount: amount.toFixed(2), description: found }, gl: { signed_amount: (-amount).toFixed(2), memo: flagged } },
})
const exception = (value: Omit<CloseException, 'evidence'> & { amount: number; found: string; flagged: string; boundary: string }): CloseException => {
  const { amount, found, flagged, boundary, ...contract } = value
  return { ...contract, evidence: exceptionEvidence(amount, found, flagged, boundary) }
}

export const createDemoSnapshot = (): WorkspaceSnapshot => ({
  run: {
    run_id: 'close-2026-08',
    counts: { bank: 79, gl: 79, matched: 61, exceptions: 18, auto_resolved: 12, in_inbox: 6 },
    checklist: [
      { task: 'Source files ingested', status: 'done' },
      { task: 'Cash reconciliation', status: 'done' },
      { task: 'Exceptions triaged', status: 'done' },
      { task: 'Controller review', status: 'in_review' },
    ],
    je_drafts: [{ for: 'MISSING_ENTRY BNK-0064', entry: { dr: '6120 Bank fees', cr: '1010 Cash', amount: 38 } }],
  },
  transactions,
  decisions: [
    decision('BNK-0007', 'GL-0031', 'exact', 1), decision('BNK-0018', 'GL-0048', 'rule', 0.97, 0.86),
    decision('BNK-0026', 'GL-0057', 'exact', 1), decision('BNK-0041', 'GL-0069', 'rule', 0.96, 0.84),
    decision('BNK-0059', 'GL-0078', 'rule', 0.95, 0.82),
  ],
  exceptions: [
    exception({ id: 'EX-004', kind: 'AMOUNT_MISMATCH', primary_kind: 'AMOUNT_MISMATCH', secondary_tags: ['possible-short-pay'], items: ['BNK-0012', 'GL-0051'], disposition: 'needs_review', suggestion: 'Approve a $0.03 write-off under the short-pay cap.', confidence: 0.91, amount: 0.03, found: 'Likely pair found from reference INV-6210.', flagged: 'Amounts differ by $0.03.', boundary: 'Not auto-resolved because confidence 0.91 is below SHORT-PAY minimum 0.95.' }),
    exception({ id: 'EX-007', kind: 'TIMING_DIFF', primary_kind: 'TIMING_DIFF', secondary_tags: [], items: ['BNK-0033', 'GL-0062'], disposition: 'needs_review', suggestion: 'Accept the pair and propose a four-day date grace.', confidence: 0.97, amount: 4200, found: 'Amount, reference, and counterparty agree.', flagged: 'Posting dates are four days apart.', boundary: 'No active policy covers four-day timing differences.' }),
    exception({ id: 'EX-009', kind: 'DUPLICATE', primary_kind: 'DUPLICATE', secondary_tags: ['same-reference'], items: ['BNK-0046', 'GL-0071', 'GL-0072'], disposition: 'escalated', suggestion: 'Reverse GL-0072 after confirming the duplicate journal.', confidence: 0.99, amount: 1875, found: 'Two GL rows share the same amount and reference.', flagged: 'Only one bank settlement exists.', boundary: 'Duplicates always require individual controller approval.' }),
    exception({ id: 'EX-011', kind: 'COUNTERPARTY_MISMATCH', primary_kind: 'COUNTERPARTY_MISMATCH', secondary_tags: ['known-alias'], items: ['BNK-0054', 'GL-0075'], disposition: 'needs_review', suggestion: 'Approve this match and lower the fuzzy threshold to 0.60.', confidence: 0.96, amount: -3210, found: 'Amount, date, and reference are exact.', flagged: 'Counterparty similarity is 0.62.', boundary: '0.62 is below MATCH-01 v1 threshold 0.80.' }),
    exception({ id: 'EX-014', kind: 'MISSING_ENTRY', primary_kind: 'MISSING_ENTRY', secondary_tags: ['bank-fee'], items: ['BNK-0064'], disposition: 'needs_review', suggestion: 'Approve the balanced bank-fee journal draft.', confidence: 0.98, amount: -38, found: 'Bank memo identifies a monthly service fee.', flagged: 'No GL candidate exists.', boundary: 'BANK-FEE allows review batching only up to $100.' }),
    exception({ id: 'EX-016', kind: 'TIMING_DIFF', primary_kind: 'TIMING_DIFF', secondary_tags: ['month-boundary'], items: ['BNK-0071', 'GL-0080'], disposition: 'needs_review', suggestion: 'Confirm cut-off treatment; retain in August close.', confidence: 0.88, amount: 9980, found: 'Reference and amount agree.', flagged: 'The GL date is in September.', boundary: 'Month-boundary items require individual review.' }),
  ],
  policies: [{ id: 'MATCH-01', version: 1, rule: { fuzzy_threshold: 0.8, amount_tolerance: 0, date_grace_days: 0 }, created_by: 'strict baseline', diff_vs_previous: {}, eval_impact: {} }],
  review_rules: [
    { policy_id: 'SHORT-PAY', applicable_kinds: ['AMOUNT_MISMATCH'], amount_cap: 0.5, min_confidence: 0.95, allow_bulk: true },
    { policy_id: 'MATCH-01', applicable_kinds: ['COUNTERPARTY_MISMATCH'], amount_cap: 5000, min_confidence: 0.95, allow_bulk: true },
    { policy_id: 'BANK-FEE', applicable_kinds: ['MISSING_ENTRY'], amount_cap: 100, min_confidence: 0.98, allow_bulk: true },
  ],
  evaluation: {
    baseline: { policy_version: 1, precision: 0.994, recall: 0.721, f1: 0.835, false_auto_closes: 0, inbox_size: 18, classification_accuracy: { TIMING_DIFF: 0.75, DUPLICATE: 1, MISSING_ENTRY: 1, AMOUNT_MISMATCH: 1, COUNTERPARTY_MISMATCH: 0.5 } },
    current: { policy_version: 1, precision: 0.994, recall: 0.721, f1: 0.835, false_auto_closes: 0, inbox_size: 18, classification_accuracy: { TIMING_DIFF: 0.75, DUPLICATE: 1, MISSING_ENTRY: 1, AMOUNT_MISMATCH: 1, COUNTERPARTY_MISMATCH: 0.5 } },
  },
  commentary: [
    { id: 'FLUX-01', title: 'Cash is substantially reconciled', body: 'Sixty-one pairs cleared deterministic checks. Remaining exposure is concentrated in timing, counterparty normalization, and one duplicate journal.', evidence_refs: ['close-2026-08', 'EX-007', 'EX-009', 'EX-011'], tone: 'info' },
    { id: 'FLUX-02', title: 'No false auto-closes detected', body: 'The frozen-label evaluation found no item that was closed automatically against an incorrect pair.', evidence_refs: ['eval-v1'], tone: 'positive' },
    { id: 'FLUX-03', title: 'One balanced journal is ready', body: 'The bank-fee exception produced a balanced draft: debit 6120 Bank fees and credit 1010 Cash for $38.00.', evidence_refs: ['BNK-0064', 'MISSING_ENTRY BNK-0064'], tone: 'review' },
  ],
})
