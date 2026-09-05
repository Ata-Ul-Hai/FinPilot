import type { CloseException, MatchDecision, Transaction } from './types'

const tx = (
  id: string,
  source: 'bank' | 'gl',
  date: string,
  amount: number,
  counterparty: string,
  reference: string,
): Transaction => ({
  id,
  source,
  date,
  amount,
  currency: 'USD',
  counterparty,
  reference,
  raw: source === 'bank'
    ? { posted_on: date, description: counterparty, debit: amount < 0 ? Math.abs(amount).toFixed(2) : '', credit: amount > 0 ? amount.toFixed(2) : '', bank_ref: reference }
    : { journal_date: date, account: '1010 Cash', memo: counterparty, signed_amount: amount.toFixed(2), document_no: reference },
})

export const matches: MatchDecision[] = [
  {
    pair: [tx('BNK-0007', 'bank', '2026-08-31', -1234.56, 'Acme Freight', 'INV-4471'), tx('GL-0031', 'gl', '2026-08-31', -1234.56, 'Acme Freight', 'INV-4471')],
    status: 'matched', method: 'exact', confidence: 1,
    evidence: { field_scores: { amount: 1, date_proximity: 1, counterparty: 1, reference: 1 }, reasons: ['Amount exact', 'Posting date exact', 'Reference INV-4471 appears in both'], counterfactual: 'Would remain unmatched if amount differed or reference was absent.' },
  },
  {
    pair: [tx('BNK-0018', 'bank', '2026-08-28', -8420, 'Northline Logistics', 'PAY-8204'), tx('GL-0048', 'gl', '2026-08-28', -8420, 'Northline Logistics LLC', 'PAY-8204')],
    status: 'matched', method: 'rule', confidence: 0.97,
    evidence: { field_scores: { amount: 1, date_proximity: 1, counterparty: 0.86, reference: 1 }, reasons: ['Amount exact', 'Reference PAY-8204 appears in both', 'Legal suffix ignored by MATCH-01'], counterfactual: 'Would not auto-match below 0.80 counterparty similarity.' },
  },
  {
    pair: [tx('BNK-0026', 'bank', '2026-08-26', 18450, 'Redwood Retail', 'DEP-1802'), tx('GL-0057', 'gl', '2026-08-26', 18450, 'Redwood Retail', 'DEP-1802')],
    status: 'matched', method: 'exact', confidence: 1,
    evidence: { field_scores: { amount: 1, date_proximity: 1, counterparty: 1, reference: 1 }, reasons: ['Amount exact', 'Posting date exact', 'Reference DEP-1802 appears in both'], counterfactual: 'Would remain unmatched if the deposit reference changed.' },
  },
  {
    pair: [tx('BNK-0041', 'bank', '2026-08-22', -2210.45, 'Meridian Cloud', 'INV-9310'), tx('GL-0069', 'gl', '2026-08-22', -2210.45, 'Meridian Cloud Inc', 'INV-9310')],
    status: 'matched', method: 'rule', confidence: 0.96,
    evidence: { field_scores: { amount: 1, date_proximity: 1, counterparty: 0.84, reference: 1 }, reasons: ['Amount exact', 'Reference INV-9310 appears in both', 'Legal suffix ignored by MATCH-01'], counterfactual: 'Would require review without the legal-suffix normalization rule.' },
  },
  {
    pair: [tx('BNK-0059', 'bank', '2026-08-18', -776.25, 'Bright Office Co', 'INV-5519'), tx('GL-0078', 'gl', '2026-08-18', -776.25, 'Bright Office Company', 'INV-5519')],
    status: 'matched', method: 'fuzzy', confidence: 0.91,
    evidence: { field_scores: { amount: 1, date_proximity: 1, counterparty: 0.78, reference: 1 }, reasons: ['Amount exact', 'Reference INV-5519 appears in both', 'Counterparty fuzzy score 0.78'], counterfactual: 'Not matched by policy v1 because counterparty 0.78 is below the 0.80 strict threshold; reviewed candidate shown for evidence.' },
  },
]

const evidence = (found: string, flagged: string, threshold: string) => ({
  field_scores: { amount: 1, date_proximity: 0.6, counterparty: 0.72, reference: 0.5 },
  reasons: [found, flagged],
  counterfactual: threshold,
})

export const exceptions: CloseException[] = [
  { id: 'EX-004', kind: 'AMOUNT_MISMATCH', primary_kind: 'AMOUNT_MISMATCH', secondary_tags: ['possible-short-pay'], items: ['BNK-0012', 'GL-0051'], disposition: 'needs_review', suggestion: 'Approve a $0.03 write-off under the short-pay cap.', confidence: 0.91, amount: 0.03, policyCovered: true, evidence: evidence('Likely pair found from reference INV-6210.', 'Amounts differ by $0.03.', 'Not auto-resolved because confidence 0.91 is below the 0.95 bulk gate.') },
  { id: 'EX-007', kind: 'TIMING_DIFF', primary_kind: 'TIMING_DIFF', secondary_tags: [], items: ['BNK-0033', 'GL-0062'], disposition: 'needs_review', suggestion: 'Accept the pair and extend date grace to 4 days.', confidence: 0.97, amount: 4200, policyCovered: false, evidence: evidence('Amount, reference, and counterparty agree.', 'Posting dates are four days apart.', 'Not auto-resolved because policy v1 has no timing-grace rule.') },
  { id: 'EX-009', kind: 'DUPLICATE', primary_kind: 'DUPLICATE', secondary_tags: ['same-reference'], items: ['BNK-0046', 'GL-0071', 'GL-0072'], disposition: 'escalated', suggestion: 'Reverse GL-0072 after confirming the duplicate journal.', confidence: 0.99, amount: 1875, policyCovered: true, evidence: evidence('Two GL rows share the same amount and reference.', 'Only one bank settlement exists.', 'Never auto-close duplicates; reversal needs controller approval.') },
  { id: 'EX-011', kind: 'COUNTERPARTY_MISMATCH', primary_kind: 'COUNTERPARTY_MISMATCH', secondary_tags: ['known-alias'], items: ['BNK-0054', 'GL-0075'], disposition: 'needs_review', suggestion: 'Approve this match and add “ACME FRT.” as an Acme Freight alias.', confidence: 0.96, amount: 3210, policyCovered: true, evidence: evidence('Amount, date, and reference are exact.', 'Counterparty similarity is 0.62.', 'Not auto-matched because 0.62 is below policy v1 threshold 0.80.') },
  { id: 'EX-014', kind: 'MISSING_ENTRY', primary_kind: 'MISSING_ENTRY', secondary_tags: ['bank-fee'], items: ['BNK-0064'], disposition: 'needs_review', suggestion: 'Create a draft journal: Dr 6120 Bank fees / Cr 1010 Cash, $38.00.', confidence: 0.98, amount: 38, policyCovered: true, evidence: evidence('Bank memo identifies a monthly service fee.', 'No GL candidate exists.', 'A draft is prepared, but posting always requires approval.') },
  { id: 'EX-016', kind: 'TIMING_DIFF', primary_kind: 'TIMING_DIFF', secondary_tags: ['month-boundary'], items: ['BNK-0071', 'GL-0080'], disposition: 'needs_review', suggestion: 'Confirm cut-off treatment; retain in August close.', confidence: 0.88, amount: 9980, policyCovered: false, evidence: evidence('Reference and amount agree.', 'The GL date is in September.', 'Month-boundary items always require individual review.') },
]

export const kindLabels: Record<CloseException['primary_kind'], string> = {
  TIMING_DIFF: 'Timing differences',
  DUPLICATE: 'Possible duplicates',
  MISSING_ENTRY: 'Missing entries',
  AMOUNT_MISMATCH: 'Amount mismatches',
  COUNTERPARTY_MISMATCH: 'Counterparty mismatches',
  UNKNOWN: 'Needs classification',
}
