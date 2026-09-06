import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight, BookOpenCheck, Check, ChevronDown, ChevronRight, CircleAlert, FileCheck2,
  FileText, Gauge, History, Inbox, Layers3, Menu, MessageSquareText, PanelRightClose,
  RefreshCw, Search, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import { connectApi } from './api'
import type { CloseApi } from './api'
import { bulkApprovalGate, evidenceAmount } from './trustGate'
import type { CloseException, ExceptionKind, MatchDecision, Policy, View, WorkspaceSnapshot } from './types'

const kindLabels: Record<ExceptionKind, string> = {
  TIMING_DIFF: 'Timing differences', DUPLICATE: 'Possible duplicates', MISSING_ENTRY: 'Missing entries',
  AMOUNT_MISMATCH: 'Amount mismatches', COUNTERPARTY_MISMATCH: 'Counterparty mismatches', UNKNOWN: 'Needs classification',
}
const views: View[] = ['close', 'review', 'policies', 'evaluation', 'commentary']
const navItems: { id: View; label: string; icon: typeof FileCheck2 }[] = [
  { id: 'close', label: 'Close workspace', icon: FileCheck2 }, { id: 'review', label: 'Review inbox', icon: Inbox },
  { id: 'policies', label: 'Policies', icon: Layers3 }, { id: 'evaluation', label: 'Evaluation', icon: Gauge },
  { id: 'commentary', label: 'Flux commentary', icon: MessageSquareText },
]
const fmt = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Math.abs(amount))
const pct = (value: number) => `${Math.round(value * 100)}%`
const viewFromHash = (): View => { const value = window.location.hash.slice(1) as View; return views.includes(value) ? value : 'close' }

function MethodBadge({ method }: { method: MatchDecision['method'] }) {
  return <span className={`method method-${method}`}><span />{method}</span>
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return <div className="score-row"><div><span>{label.replace('_', ' ')}</span><strong>{pct(value)}</strong></div><div className="score-track"><i style={{ width: pct(value) }} /></div></div>
}

function EvidenceDrawer({ decision, onClose }: { decision: MatchDecision; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !dialogRef.current) return
      const controls = [...dialogRef.current.querySelectorAll<HTMLElement>('button,[href],input,select,[tabindex]:not([tabindex="-1"])')]
      if (!controls.length) return
      const first = controls[0], last = controls.at(-1)!
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); previous?.focus() }
  }, [onClose])
  const ids = decision.pair ?? decision.items ?? []
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <aside ref={dialogRef} className="drawer" aria-modal="true" role="dialog" aria-labelledby="drawer-title">
      <header className="drawer-header"><div><span className="eyebrow">Decision evidence</span><h2 id="drawer-title">{ids.join(' ↔ ')}</h2></div><button ref={closeRef} className="icon-button" onClick={onClose} aria-label="Close evidence drawer"><PanelRightClose size={19} /></button></header>
      <div className="drawer-body">
        <section className="decision-summary"><div><ShieldCheck size={20} /><span>{decision.status === 'matched' ? `Matched by ${decision.method}` : 'Held for review'}</span></div><strong>{pct(decision.confidence)} confidence</strong></section>
        <section><div className="section-heading"><h3>Source rows</h3><span>Original values from evidence pack</span></div><div className="source-grid">
          {Object.entries(decision.evidence.source_rows).map(([source, row]) => <article className="source-card" key={source}><div><span className="source-type">{source}</span><code>{ids.find((id) => id.toLowerCase().startsWith(source.slice(0, 2))) ?? source}</code></div>{Object.entries(row).map(([key, value]) => <p key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{String(value ?? '—')}</strong></p>)}</article>)}
        </div></section>
        {decision.evidence.candidate_rows?.length ? <section><div className="section-heading"><h3>Candidate rows</h3><span>Ambiguity preserved for review</span></div><ul className="reason-list">{decision.evidence.candidate_rows.map((row) => <li key={row.id}><CircleAlert size={14} />{row.id} · {row.source}</li>)}</ul></section> : null}
        <section><div className="section-heading"><h3>Field scores</h3><span>Deterministic scoring</span></div><div className="scores">{Object.entries(decision.evidence.field_scores).map(([label, value]) => <ScoreBar key={label} label={label} value={value} />)}</div></section>
        <section><div className="section-heading"><h3>Why this decision</h3></div><ul className="reason-list">{decision.evidence.reasons.map((reason) => <li key={reason}><Check size={14} />{reason}</li>)}</ul></section>
        <section className="counterfactual"><span>Decision boundary</span><p>{decision.evidence.counterfactual}</p></section>
      </div>
    </aside>
  </div>
}

function CloseWorkspace({ data, busy, navigate, onRun }: { data: WorkspaceSnapshot; busy: boolean; navigate: (view: View) => void; onRun: (files: { bank: File; gl: File } | null) => void }) {
  const [bank, setBank] = useState<File | null>(null), [gl, setGl] = useState<File | null>(null)
  const [query, setQuery] = useState(''), [drawer, setDrawer] = useState<MatchDecision | null>(null)
  const txById = useMemo(() => new Map(data.transactions.map((item) => [item.id, item])), [data.transactions])
  const matched = data.decisions.filter((decision) => decision.status === 'matched' && decision.pair)
  const filtered = matched.filter((decision) => decision.pair!.some((id) => { const tx = txById.get(id); return `${id} ${tx?.counterparty ?? ''} ${tx?.reference ?? ''}`.toLowerCase().includes(query.toLowerCase()) }))
  const run = () => { if ((bank && !gl) || (!bank && gl)) return; onRun(bank && gl ? { bank, gl } : null) }
  return <div className="view close-view">
    <div className="page-title title-with-action"><div><span className="eyebrow">{data.run.run_id}</span><h1>Cash reconciliation</h1><p>Trace every decision from ledger row to close status.</p></div><button className="secondary-button" disabled={busy || (!!bank !== !!gl)} onClick={run}><RefreshCw size={15} />{bank && gl ? 'Ingest & run close' : 'Re-run close'}</button></div>
    {(!!bank !== !!gl) ? <div className="inline-error">Choose both a bank CSV and GL CSV before running.</div> : null}
    <section className="close-rail" aria-label="Close progress">{data.run.checklist.slice(0, 4).map((item, index) => <div className={`rail-step ${item.status === 'done' ? 'complete' : 'current'}`} key={item.task}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{item.task}</strong><small>{item.status.replace('_', ' ')}</small></div>{item.status === 'done' ? <Check size={15} /> : <ChevronRight size={15} />}</div>)}</section>
    <div className="workspace-grid"><div className="primary-column">
      <section className="panel upload-panel"><div className="panel-title"><div><h2>Source files</h2><p>{data.run.counts.bank + data.run.counts.gl} canonical rows loaded; raw rows retained.</p></div><span className="status-pill success"><Check size={12} /> Ingested</span></div><div className="file-pair">
        <label><FileText size={18} /><span><strong>Bank statement</strong><small>{bank?.name ?? `${data.run.counts.bank} rows loaded`}</small></span><input type="file" accept=".csv" onChange={(e) => setBank(e.target.files?.[0] ?? null)} /><span className="replace">Choose CSV</span></label>
        <label><BookOpenCheck size={18} /><span><strong>General ledger</strong><small>{gl?.name ?? `${data.run.counts.gl} rows loaded`}</small></span><input type="file" accept=".csv" onChange={(e) => setGl(e.target.files?.[0] ?? null)} /><span className="replace">Choose CSV</span></label>
      </div></section>
      <section className="panel match-panel"><div className="panel-title table-title"><div><h2>Match explorer</h2><p>Showing {matched.length} evidence packs of {data.run.counts.matched} matched pairs.</p></div><label className="search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search rows" aria-label="Search matches" /></label></div><div className="match-table" role="table" aria-label="Reconciliation matches"><div className="match-row match-head" role="row"><span>Bank</span><span>GL entry</span><span>Method</span><span>Confidence</span><span /></div>
        {filtered.map((decision) => { const [bankId, glId] = decision.pair!, bankTx = txById.get(bankId), glTx = txById.get(glId); return <button className="match-row" key={bankId} onClick={() => setDrawer(decision)} aria-label={`View evidence for ${bankId} and ${glId}`}><span><strong>{bankTx?.counterparty ?? bankId}</strong><small>{bankId} · {bankTx ? fmt(bankTx.amount) : 'source row'}</small></span><span><strong>{glTx?.counterparty ?? glId}</strong><small>{glId} · {glTx?.reference ?? 'source row'}</small></span><span><MethodBadge method={decision.method} /></span><span><strong className="confidence">{pct(decision.confidence)}</strong></span><ChevronRight size={16} /></button> })}
        {!filtered.length ? <div className="empty-row">No evidence packs match “{query}”.</div> : null}
      </div></section>
    </div><aside className="side-column">
      <section className="panel summary-panel"><div className="panel-title"><div><h2>Close pulse</h2><p>Derived from {data.run.run_id}</p></div><span className="pulse-dot" /></div><div className="hero-metric"><strong>{data.run.counts.bank ? pct(data.run.counts.matched / data.run.counts.bank) : '—'}</strong><span>bank rows matched</span></div><div className="summary-list"><p><span>Bank rows</span><strong>{data.run.counts.bank}</strong></p><p><span>GL rows</span><strong>{data.run.counts.gl}</strong></p><p><span>Matched pairs</span><strong>{data.run.counts.matched}</strong></p><p className="warning"><span>Needs review</span><strong>{data.run.counts.in_inbox}</strong></p></div></section>
      <section className="panel note-panel"><div className="note-icon"><Sparkles size={17} /></div><span className="eyebrow">Controller brief</span><h3>{data.commentary[0]?.title ?? 'Commentary is ready.'}</h3><p>{data.commentary[0]?.body ?? 'Open Flux commentary for the evidence-linked close narrative.'}</p><button className="text-button" onClick={() => navigate('commentary')}>Read flux commentary <ArrowRight size={14} /></button></section>
    </aside></div>{drawer ? <EvidenceDrawer decision={drawer} onClose={() => setDrawer(null)} /> : null}
  </div>
}

function ExceptionCard({ item, rules, selected, busy, onSelect, onReclassify, onApprove }: { item: CloseException; rules: WorkspaceSnapshot['review_rules']; selected: boolean; busy: boolean; onSelect: () => void; onReclassify: (kind: ExceptionKind) => void; onApprove: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const gate = bulkApprovalGate(item, rules), amount = evidenceAmount(item)
  return <article className={`exception-card ${selected ? 'selected' : ''}`}><div className="exception-select"><input type="checkbox" checked={selected} onChange={onSelect} aria-label={`Select ${item.id}`} /></div><div className="exception-main">
    <div className="exception-top"><div><code>{item.id}</code>{item.secondary_tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div><strong>{amount === null ? 'Unpriced' : fmt(amount)}</strong></div><h3>{item.items.join(' ↔ ')}</h3>
    <div className="triad"><p><span>Found</span>{item.evidence.reasons[0]}</p><p><span>Flagged</span>{item.evidence.reasons[1] ?? item.evidence.counterfactual}</p><p><span>Recommend</span>{item.suggestion}</p></div>
    {expanded ? <div className="exception-evidence"><strong>Decision boundary</strong><p>{item.evidence.counterfactual}</p><small>{gate.eligible ? `Bulk gate: ${gate.rule.policy_id}, ≤${fmt(gate.rule.amount_cap)}, ≥${pct(gate.rule.min_confidence)}` : `Individual review: ${gate.reason}`}</small></div> : null}
    <div className="exception-actions"><button className="text-button" onClick={() => setExpanded((value) => !value)}>{expanded ? 'Hide' : 'View'} evidence <ChevronDown className={expanded ? 'rotated' : ''} size={14} /></button><div><label>Reclassify <select disabled={busy} value={item.primary_kind} onChange={(e) => onReclassify(e.target.value as ExceptionKind)}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button disabled={busy} className="approve-button" onClick={onApprove}>Approve individually</button></div></div>
  </div></article>
}

function ReviewInbox({ data, busy, onReclassify, onApprove }: { data: WorkspaceSnapshot; busy: boolean; onReclassify: (id: string, kind: ExceptionKind) => void; onApprove: (ids: string[]) => void }) {
  const [selected, setSelected] = useState<Set<string>>(new Set()), [filter, setFilter] = useState<ExceptionKind | 'ALL'>('ALL')
  const open = data.exceptions.filter((item) => item.disposition !== 'auto_resolved')
  const activeSelected = new Set([...selected].filter((id) => open.some((item) => item.id === id)))
  const visible = filter === 'ALL' ? open : open.filter((item) => item.primary_kind === filter)
  const grouped = useMemo(() => { const result = new Map<ExceptionKind, CloseException[]>(); visible.forEach((item) => result.set(item.primary_kind, [...(result.get(item.primary_kind) ?? []), item])); return [...result.entries()] }, [visible])
  const selectedItems = open.filter((item) => activeSelected.has(item.id)), gateResults = selectedItems.map((item) => bulkApprovalGate(item, data.review_rules))
  const bulkEligible = selectedItems.length > 0 && gateResults.every((result) => result.eligible)
  const firstFailure = gateResults.find((result) => !result.eligible)
  const failureMessage = firstFailure && !firstFailure.eligible ? firstFailure.reason : ''
  const exposure = open.reduce((total, item) => total + (evidenceAmount(item) ?? 0), 0)
  return <div className="view"><div className="page-title title-with-action"><div><span className="eyebrow">{open.length} items · {fmt(exposure)} evidence-backed exposure</span><h1>Review inbox</h1><p>Grouped by the current primary cause; every approval preserves its evidence.</p></div><div className="bulk-wrap"><button className="primary-button" disabled={busy || !bulkEligible} onClick={() => onApprove([...activeSelected])}><Check size={15} /> Approve selected</button>{selectedItems.length && !bulkEligible ? <small>{failureMessage}</small> : null}</div></div>
    <div className="trust-banner"><ShieldCheck size={18} /><p><strong>Triage cannot post or close.</strong> Bulk approval requires ≥95% confidence, a named applicable policy, and evidence amount within that policy’s cap.</p></div>
    <div className="inbox-layout"><aside className="inbox-filters"><span>Primary cause</span><button className={filter === 'ALL' ? 'active' : ''} onClick={() => setFilter('ALL')}>All open <strong>{open.length}</strong></button>{Object.entries(kindLabels).map(([kind, label]) => { const count = open.filter((item) => item.primary_kind === kind).length; return count ? <button className={filter === kind ? 'active' : ''} key={kind} onClick={() => setFilter(kind as ExceptionKind)}>{label} <strong>{count}</strong></button> : null })}</aside><div className="exception-groups">{grouped.map(([kind, group]) => <section key={kind} className="exception-group"><div className="group-title"><h2>{kindLabels[kind]}</h2><span>{group.length} {group.length === 1 ? 'item' : 'items'}</span></div>{group.map((item) => <ExceptionCard key={item.id} item={item} rules={data.review_rules} selected={activeSelected.has(item.id)} busy={busy} onSelect={() => setSelected((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })} onReclassify={(kind) => onReclassify(item.id, kind)} onApprove={() => onApprove([item.id])} />)}</section>)}</div></div>
  </div>
}

function PolicyCard({ policy, reviewRules }: { policy: Policy; reviewRules: WorkspaceSnapshot['review_rules'] }) {
  const rules = reviewRules.filter((rule) => rule.policy_id === policy.id)
  return <article className={`policy-card ${Object.keys(policy.diff_vs_previous).length ? 'featured' : ''}`}><header><div><span>{policy.id}</span><h2>Matching controls</h2></div><span className="version">v{policy.version}</span></header><div className="policy-rule"><p><span>Fuzzy threshold</span><strong>{policy.rule.fuzzy_threshold.toFixed(2)}</strong></p><p><span>Amount tolerance</span><strong>{fmt(policy.rule.amount_tolerance)}</strong></p><p><span>Date grace</span><strong>{policy.rule.date_grace_days} days</strong></p>{rules.map((rule) => <p key={`${rule.policy_id}-${rule.applicable_kinds.join()}`}><span>Bulk gate · {rule.applicable_kinds.map((kind) => kindLabels[kind]).join(', ')}</span><strong>≤{fmt(rule.amount_cap)} / ≥{pct(rule.min_confidence)}</strong></p>)}</div>{Object.keys(policy.diff_vs_previous).length ? <div className="policy-diff"><span><History size={14} /> Changed from v{policy.version - 1}</span>{Object.entries(policy.diff_vs_previous).map(([key, [before, after]]) => <p key={key}><code>{key}</code><del>{before}</del><ins>{after}</ins></p>)}<small>{policy.created_by}</small>{Object.entries(policy.eval_impact).map(([key, [before, after]]) => <small key={key}>Measured {key}: {pct(before)} → {pct(after)}</small>)}</div> : <div className="policy-empty"><p>{policy.created_by}. No prior-version diff.</p></div>}</article>
}
function Policies({ data }: { data: WorkspaceSnapshot }) {
  return <div className="view"><div className="page-title"><span className="eyebrow">Governed decision rules</span><h1>Matching policies</h1><p>Only controller-approved corrections create a version; each card shows the exact returned diff.</p></div><div className="policy-grid">{[...data.policies].reverse().map((policy) => <PolicyCard key={`${policy.id}-${policy.version}`} policy={policy} reviewRules={data.review_rules} />)}</div></div>
}

const Metric = ({ label, before, after, inverse = false, percent = true }: { label: string; before: number; after: number; inverse?: boolean; percent?: boolean }) => {
  const improved = inverse ? after < before : after > before, format = (value: number) => percent ? pct(value) : String(value)
  return <article className="metric-card"><span>{label}</span><div><del>{format(before)}</del><ArrowRight size={16} /><strong>{format(after)}</strong></div><small className={improved ? 'positive' : ''}>{improved ? 'Improved' : 'No change'}</small></article>
}
function Evaluation({ data, busy, onRun }: { data: WorkspaceSnapshot; busy: boolean; onRun: () => void }) {
  const { baseline, current } = data.evaluation, improved = current.policy_version > baseline.policy_version
  return <div className="view"><div className="page-title title-with-action"><div><span className="eyebrow">Frozen ground truth · {data.run.counts.bank} bank / {data.run.counts.gl} GL</span><h1>Evaluation</h1><p>Metrics returned by the evaluation endpoint, never inferred by the UI.</p></div><button disabled={busy} className="secondary-button" onClick={onRun}><RefreshCw size={15} /> Run evaluation</button></div>
    <section className="eval-hero"><div><span className="eyebrow">Policy v{baseline.policy_version} → v{current.policy_version}</span><h2>{improved ? 'Reviewed policy measured against frozen labels.' : 'Strict baseline protects precision.'}</h2><p>{improved ? 'The latest metrics were returned after the approved policy diff was evaluated.' : 'Approve a policy-producing correction, then rerun evaluation to measure its impact.'}</p></div><div className="zero-card"><ShieldCheck size={22} /><strong>{current.false_auto_closes}</strong><span>false auto-closes</span></div></section>
    <div className="metrics-grid"><Metric label="Precision" before={baseline.precision} after={current.precision} /><Metric label="Recall" before={baseline.recall} after={current.recall} /><Metric label="F1 score" before={baseline.f1} after={current.f1} /><Metric label="Inbox size" before={baseline.inbox_size} after={current.inbox_size} inverse percent={false} /></div>
    <section className="panel taxonomy-panel"><div className="panel-title"><div><h2>Exception classification</h2><p>Accuracy by primary cause from /eval</p></div><span className="status-pill success"><Check size={12} /> {data.run.counts.exceptions} labeled exceptions</span></div>{Object.entries(kindLabels).filter(([kind]) => current.classification_accuracy[kind as ExceptionKind] !== undefined).map(([kind, label]) => { const value = current.classification_accuracy[kind as ExceptionKind]!; return <div className="taxonomy-row" key={kind}><span>{label}</span><div><i style={{ width: pct(value) }} /></div><strong>{pct(value)}</strong></div> })}</section>
  </div>
}

function FluxCommentary({ data }: { data: WorkspaceSnapshot }) {
  return <div className="view"><div className="page-title"><span className="eyebrow">Evidence-linked controller notes</span><h1>Flux commentary</h1><p>Draft narrative from close results; every statement links back to evidence.</p></div><div className="commentary-grid">{data.commentary.map((line) => <article className={`commentary-card ${line.tone}`} key={line.id}><div><MessageSquareText size={18} /><code>{line.id}</code></div><h2>{line.title}</h2><p>{line.body}</p><footer><span>Evidence</span>{line.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</footer></article>)}</div><section className="panel je-panel"><div className="panel-title"><div><h2>Journal drafts</h2><p>Prepared only; posting requires controller approval.</p></div><span className="status-pill success">{data.run.je_drafts.length} balanced</span></div>{data.run.je_drafts.map((draft) => <div className="je-row" key={draft.for}><code>{draft.for}</code><span>Dr {draft.entry.dr}</span><span>Cr {draft.entry.cr}</span><strong>{fmt(draft.entry.amount)}</strong></div>)}</section></div>
}

function Loading() { return <main className="loading"><RefreshCw className="spin" /><p>Connecting to close workspace…</p></main> }

export default function App() {
  const [view, setView] = useState<View>(viewFromHash), [menuOpen, setMenuOpen] = useState(false)
  const [data, setData] = useState<WorkspaceSnapshot | null>(null), [source, setSource] = useState<'api' | 'demo'>('api')
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null), [toast, setToast] = useState<string | null>(null)
  const apiRef = useRef<CloseApi | null>(null)
  useEffect(() => { const listener = () => setView(viewFromHash()); window.addEventListener('hashchange', listener); return () => window.removeEventListener('hashchange', listener) }, [])
  useEffect(() => { connectApi().then(({ api, snapshot, error: connectError }) => { apiRef.current = api; setData(snapshot); setSource(api.source); if (connectError) setError('Offline demo data — backend not reachable. Start it with: uvicorn backend.app.server:app --port 8000') }) }, [])
  const navigate = (next: View) => { window.history.pushState({}, '', `#${next}`); setView(next); setMenuOpen(false) }
  const perform = async (action: (api: CloseApi) => Promise<WorkspaceSnapshot>, success?: string) => {
    if (!apiRef.current) return
    setBusy(true); setError(null)
    try { const snapshot = await action(apiRef.current); setData(snapshot); if (success) { setToast(success); window.setTimeout(() => setToast(null), 4000) } }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The action failed.') }
    finally { setBusy(false) }
  }
  const approve = async (ids: string[]) => {
    if (!apiRef.current || !data) return
    setBusy(true); setError(null)
    try {
      let snapshot = data
      for (const id of ids) { const item = snapshot.exceptions.find((candidate) => candidate.id === id); if (!item) continue; const gate = bulkApprovalGate(item, snapshot.review_rules); snapshot = await apiRef.current.approve(id, gate.eligible ? gate.rule.policy_id : null) }
      snapshot = await apiRef.current.runEvaluation()
      setData(snapshot); setToast(`${ids.length} review ${ids.length === 1 ? 'decision' : 'decisions'} persisted · evaluation rerun`); window.setTimeout(() => setToast(null), 4000)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Approval failed.') }
    finally { setBusy(false) }
  }
  if (!data) return <Loading />
  return <div className="app-shell">
    <header className="mobile-header"><button className="icon-button" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="brand-mark"><span>CC</span><strong>Close Copilot</strong></div></header>
    <aside className={`sidebar ${menuOpen ? 'open' : ''}`}><div className="brand"><div className="brand-mark"><span>CC</span><div><strong>Close Copilot</strong><small>Evidence-first close</small></div></div><button className="icon-button mobile-only" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={18} /></button></div><nav>{navItems.map(({ id, label, icon: Icon }) => <button className={view === id ? 'active' : ''} key={id} onClick={() => navigate(id)}><Icon size={17} /><span>{label}</span>{id === 'review' ? <strong>{data.run.counts.in_inbox}</strong> : null}</button>)}</nav><div className="sidebar-bottom"><div className="close-status"><span className="pulse-dot" /><div><strong>{data.run.run_id}</strong><small>{source === 'api' ? 'Live API' : 'Offline demo data'}</small></div></div></div></aside>
    {menuOpen ? <button className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-label="Close navigation overlay" /> : null}
    {error ? <div className={`connection-banner ${source}`}>{error}<button onClick={() => setError(null)} aria-label="Dismiss message"><X size={14} /></button></div> : null}
    <main>
      {view === 'close' ? <CloseWorkspace data={data} busy={busy} navigate={navigate} onRun={(files) => perform((api) => files ? api.ingest(files.bank, files.gl) : api.rerunClose(), 'Close run refreshed')} /> : null}
      {view === 'review' ? <ReviewInbox data={data} busy={busy} onReclassify={(id, kind) => perform((api) => api.reclassify(id, kind), `${id} reclassified`)} onApprove={approve} /> : null}
      {view === 'policies' ? <Policies data={data} /> : null}{view === 'evaluation' ? <Evaluation data={data} busy={busy} onRun={() => perform((api) => api.runEvaluation(), 'Evaluation rerun')} /> : null}{view === 'commentary' ? <FluxCommentary data={data} /> : null}
    </main>
    {toast ? <div className="toast" role="status"><Check size={16} />{toast}<button onClick={() => setToast(null)} aria-label="Dismiss notification"><X size={14} /></button></div> : null}
  </div>
}
