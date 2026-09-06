import { createDemoSnapshot } from './demoData'
import type { CloseException, EvalComparison, ExceptionKind, Policy, WorkspaceSnapshot } from './types'

export type DataSource = 'api' | 'demo'
export type CloseApi = {
  source: DataSource
  load(): Promise<WorkspaceSnapshot>
  ingest(bank: File, gl: File): Promise<WorkspaceSnapshot>
  rerunClose(): Promise<WorkspaceSnapshot>
  reclassify(id: string, primaryKind: ExceptionKind): Promise<WorkspaceSnapshot>
  approve(id: string, policyId: string | null): Promise<WorkspaceSnapshot>
  runEvaluation(): Promise<WorkspaceSnapshot>
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init?.headers } })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

async function loadHttpWorkspace(): Promise<WorkspaceSnapshot> {
  const close = await request<WorkspaceSnapshot | WorkspaceSnapshot['run']>('/close')
  if ('run' in close && 'decisions' in close) return close
  const [transactions, decisions, exceptions, policies, reviewRules, evaluation, commentary] = await Promise.all([
    request<WorkspaceSnapshot['transactions']>('/transactions'),
    request<WorkspaceSnapshot['decisions']>('/matches'),
    request<WorkspaceSnapshot['exceptions']>('/exceptions'),
    request<WorkspaceSnapshot['policies']>('/policies'),
    request<WorkspaceSnapshot['review_rules']>('/policies/review-rules'),
    request<EvalComparison>('/eval'),
    request<WorkspaceSnapshot['commentary']>('/commentary'),
  ])
  return { run: close, transactions, decisions, exceptions, policies, review_rules: reviewRules, evaluation, commentary }
}

export const httpApi: CloseApi = {
  source: 'api',
  load: loadHttpWorkspace,
  async ingest(bank, gl) {
    const form = new FormData()
    form.append('bank', bank)
    form.append('gl', gl)
    await request('/ingest', { method: 'POST', body: form })
    await request('/close', { method: 'POST', body: '{}' })
    return loadHttpWorkspace()
  },
  async rerunClose() { await request('/close', { method: 'POST', body: '{}' }); return loadHttpWorkspace() },
  async reclassify(id, primaryKind) { await request('/review/reclassify', { method: 'POST', body: JSON.stringify({ exception_id: id, primary_kind: primaryKind }) }); return loadHttpWorkspace() },
  async approve(id, policyId) { await request('/review', { method: 'POST', body: JSON.stringify({ exception_id: id, action: 'approve', applicable_policy_id: policyId }) }); return loadHttpWorkspace() },
  async runEvaluation() { await request('/eval', { method: 'POST', body: '{}' }); return loadHttpWorkspace() },
}

const clone = <T,>(value: T): T => structuredClone(value)

export function createDemoApi(): CloseApi {
  let state = createDemoSnapshot()
  const load = async () => clone(state)
  const syncCounts = () => {
    const open = state.exceptions.filter((item) => item.disposition !== 'auto_resolved').length
    state.run.counts.in_inbox = open
    state.run.counts.auto_resolved = state.run.counts.exceptions - open
  }
  const nextPolicy = (item: CloseException): Policy | null => {
    const previous = state.policies.at(-1)!
    if (item.primary_kind === 'COUNTERPARTY_MISMATCH') return { id: 'MATCH-01', version: previous.version + 1, rule: { ...previous.rule, fuzzy_threshold: 0.6 }, created_by: `override ${item.id} approved by controller`, diff_vs_previous: { fuzzy_threshold: [previous.rule.fuzzy_threshold, 0.6] }, eval_impact: {} }
    if (item.primary_kind === 'TIMING_DIFF') return { id: 'MATCH-01', version: previous.version + 1, rule: { ...previous.rule, date_grace_days: 4 }, created_by: `override ${item.id} approved by controller`, diff_vs_previous: { date_grace_days: [previous.rule.date_grace_days, 4] }, eval_impact: {} }
    return null
  }
  return {
    source: 'demo', load,
    async ingest() { state = createDemoSnapshot(); return load() },
    async rerunClose() { return load() },
    async reclassify(id, primaryKind) { state.exceptions = state.exceptions.map((item) => item.id === id ? { ...item, primary_kind: primaryKind } : item); return load() },
    async approve(id) {
      const item = state.exceptions.find((candidate) => candidate.id === id)
      if (!item) throw new Error(`Exception ${id} was not found.`)
      const policy = nextPolicy(item)
      state.exceptions = state.exceptions.map((candidate) => candidate.id === id ? { ...candidate, disposition: 'auto_resolved' } : candidate)
      if (policy) state.policies.push(policy)
      syncCounts()
      return load()
    },
    async runEvaluation() {
      const currentPolicy = state.policies.at(-1)!
      const fuzzyImproved = currentPolicy.rule.fuzzy_threshold < 0.8
      const timingImproved = currentPolicy.rule.date_grace_days > 0
      const current = clone(state.evaluation.baseline)
      current.policy_version = currentPolicy.version
      if (fuzzyImproved) { current.recall = 0.85; current.f1 = 0.916; current.inbox_size = 14; current.classification_accuracy.COUNTERPARTY_MISMATCH = 1 }
      if (timingImproved) { current.recall = fuzzyImproved ? 0.962 : 0.87; current.f1 = fuzzyImproved ? 0.978 : 0.925; current.inbox_size = fuzzyImproved ? 8 : 12; current.classification_accuracy.TIMING_DIFF = 1 }
      state.evaluation.current = current
      const latest = state.policies.at(-1)!
      latest.eval_impact = { recall: [state.evaluation.baseline.recall, current.recall] }
      return load()
    },
  }
}

export async function connectApi(): Promise<{ api: CloseApi; snapshot: WorkspaceSnapshot; error: string | null }> {
  try { return { api: httpApi, snapshot: await httpApi.load(), error: null } }
  catch (error) {
    const demo = createDemoApi()
    return { api: demo, snapshot: await demo.load(), error: error instanceof Error ? error.message : 'API unavailable' }
  }
}
