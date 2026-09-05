import { describe, expect, it } from 'vitest'
import { createDemoApi } from './api'

describe('review to policy transition', () => {
  it('uses the current reclassification and does not create a stale policy proposal', async () => {
    const api = createDemoApi()
    await api.reclassify('EX-011', 'DUPLICATE')
    await api.approve('EX-011', null)
    const result = await api.runEvaluation()
    expect(result.policies).toHaveLength(1)
    expect(result.evaluation.current.policy_version).toBe(1)
  })

  it('creates only the approved fuzzy diff and records the measured eval impact', async () => {
    const api = createDemoApi()
    await api.approve('EX-011', 'MATCH-01')
    const result = await api.runEvaluation()
    const policy = result.policies.at(-1)!
    expect(policy.diff_vs_previous).toEqual({ fuzzy_threshold: [0.8, 0.6] })
    expect(policy.rule.date_grace_days).toBe(0)
    expect(policy.eval_impact.recall).toEqual([0.721, 0.85])
    expect(result.evaluation.current.recall).toBe(0.85)
  })
})
