import { useMemo, useState } from 'react'
import {
  ArrowRight, BookOpenCheck, Check, ChevronDown, ChevronRight, CircleAlert,
  FileCheck2, FileText, Gauge, History, Inbox, Layers3, Menu, PanelRightClose,
  RefreshCw, Search, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import { exceptions as initialExceptions, kindLabels, matches } from './mockData'
import type { CloseException, ExceptionKind, MatchDecision, View } from './types'

const navItems: { id: View; label: string; icon: typeof FileCheck2; badge?: number }[] = [
  { id: 'close', label: 'Close workspace', icon: FileCheck2 },
  { id: 'review', label: 'Review inbox', icon: Inbox, badge: 13 },
  { id: 'policies', label: 'Policies', icon: Layers3 },
  { id: 'evaluation', label: 'Evaluation', icon: Gauge },
]

const fmt = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Math.abs(amount))
const pct = (score: number) => `${Math.round(score * 100)}%`

function MethodBadge({ method }: { method: MatchDecision['method'] }) {
  return <span className={`method method-${method}`}><span />{method}</span>
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="score-row">
      <div><span>{label.replace('_', ' ')}</span><strong>{pct(value)}</strong></div>
      <div className="score-track"><i style={{ width: pct(value) }} /></div>
    </div>
  )
}

function EvidenceDrawer({ decision, onClose }: { decision: MatchDecision; onClose: () => void }) {
  const [bank, gl] = decision.pair
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="drawer" aria-modal="true" role="dialog" aria-labelledby="drawer-title">
        <header className="drawer-header">
          <div>
            <span className="eyebrow">Decision evidence</span>
            <h2 id="drawer-title">{bank.id} ↔ {gl.id}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close evidence drawer"><PanelRightClose size={19} /></button>
        </header>
        <div className="drawer-body">
          <section className="decision-summary">
            <div><ShieldCheck size={20} /><span>Matched by {decision.method}</span></div>
            <strong>{pct(decision.confidence)} confidence</strong>
          </section>
          <section>
            <div className="section-heading"><h3>Source rows</h3><span>Original values, never transformed</span></div>
            <div className="source-grid">
              {[bank, gl].map((item) => (
                <article className="source-card" key={item.id}>
                  <div><span className="source-type">{item.source}</span><code>{item.id}</code></div>
                  {Object.entries(item.raw).map(([key, value]) => <p key={key}><span>{key.replace('_', ' ')}</span><strong>{value || '—'}</strong></p>)}
                </article>
              ))}
            </div>
          </section>
          <section>
            <div className="section-heading"><h3>Field scores</h3><span>Deterministic scoring</span></div>
            <div className="scores">{Object.entries(decision.evidence.field_scores).map(([label, value]) => <ScoreBar key={label} label={label} value={value} />)}</div>
          </section>
          <section>
            <div className="section-heading"><h3>Why this matched</h3></div>
            <ul className="reason-list">{decision.evidence.reasons.map((reason) => <li key={reason}><Check size={14} />{reason}</li>)}</ul>
          </section>
          <section className="counterfactual">
            <span>Why not match?</span>
            <p>{decision.evidence.counterfactual}</p>
          </section>
        </div>
      </aside>
    </div>
  )
}

function CloseWorkspace({ openEvidence }: { openEvidence: (decision: MatchDecision) => void }) {
  const [bankFile, setBankFile] = useState('bank_august.csv')
  const [glFile, setGlFile] = useState('gl_august.csv')
  const [query, setQuery] = useState('')
  const filtered = matches.filter(({ pair }) => pair.some((row) => `${row.id} ${row.counterparty} ${row.reference}`.toLowerCase().includes(query.toLowerCase())))
  return (
    <div className="view close-view">
      <div className="page-title title-with-action">
        <div><span className="eyebrow">August 2026 · close-2026-08</span><h1>Cash reconciliation</h1><p>Trace every decision from ledger row to close status.</p></div>
        <button className="secondary-button"><RefreshCw size={15} /> Re-run close</button>
      </div>

      <section className="close-rail" aria-label="Close progress">
        {[['01', 'Ingested', '162 rows'], ['02', 'Reconciled', '61 matches'], ['03', 'Escalated', '18 exceptions'], ['04', 'Controller review', '13 open']].map(([step, label, detail], index) => (
          <div className={index < 3 ? 'rail-step complete' : 'rail-step current'} key={step}>
            <span>{step}</span><div><strong>{label}</strong><small>{detail}</small></div>{index < 3 ? <Check size={15} /> : <ChevronRight size={15} />}
          </div>
        ))}
      </section>

      <div className="workspace-grid">
        <div className="primary-column">
          <section className="panel upload-panel">
            <div className="panel-title"><div><h2>Source files</h2><p>Canonicalized with raw rows preserved.</p></div><span className="status-pill success"><Check size={12} /> Ingested</span></div>
            <div className="file-pair">
              <label><FileText size={18} /><span><strong>Bank statement</strong><small>{bankFile}</small></span><input type="file" accept=".csv" onChange={(e) => setBankFile(e.target.files?.[0]?.name ?? bankFile)} /><span className="replace">Replace</span></label>
              <label><BookOpenCheck size={18} /><span><strong>General ledger</strong><small>{glFile}</small></span><input type="file" accept=".csv" onChange={(e) => setGlFile(e.target.files?.[0]?.name ?? glFile)} /><span className="replace">Replace</span></label>
            </div>
          </section>

          <section className="panel match-panel">
            <div className="panel-title table-title"><div><h2>Match explorer</h2><p>61 of 79 bank transactions matched.</p></div><label className="search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search rows" aria-label="Search matches" /></label></div>
            <div className="match-table" role="table" aria-label="Reconciliation matches">
              <div className="match-row match-head" role="row"><span>Bank</span><span>GL entry</span><span>Method</span><span>Confidence</span><span /></div>
              {filtered.map((decision) => {
                const [bank, gl] = decision.pair
                return <button className="match-row" key={bank.id} onClick={() => openEvidence(decision)} aria-label={`View evidence for ${bank.id} and ${gl.id}`}>
                  <span><strong>{bank.counterparty}</strong><small>{bank.id} · {fmt(bank.amount)}</small></span>
                  <span><strong>{gl.counterparty}</strong><small>{gl.id} · {gl.reference}</small></span>
                  <span><MethodBadge method={decision.method} /></span>
                  <span><strong className="confidence">{pct(decision.confidence)}</strong></span>
                  <ChevronRight size={16} />
                </button>
              })}
              {filtered.length === 0 ? <div className="empty-row">No source rows match “{query}”.</div> : null}
            </div>
          </section>
        </div>
        <aside className="side-column">
          <section className="panel summary-panel">
            <div className="panel-title"><div><h2>Close pulse</h2><p>As of 4:18 PM</p></div><span className="pulse-dot" /></div>
            <div className="hero-metric"><strong>77.2%</strong><span>matched by value</span></div>
            <div className="summary-list">
              <p><span>Bank rows</span><strong>79</strong></p><p><span>GL rows</span><strong>83</strong></p><p><span>Matched pairs</span><strong>61</strong></p><p className="warning"><span>Needs review</span><strong>13</strong></p>
            </div>
          </section>
          <section className="panel note-panel">
            <div className="note-icon"><Sparkles size={17} /></div>
            <span className="eyebrow">Controller brief</span>
            <h3>Cash is substantially reconciled.</h3>
            <p>Open items are concentrated in timing and counterparty normalization. No false auto-closes were detected.</p>
            <button className="text-button">Read flux commentary <ArrowRight size={14} /></button>
          </section>
        </aside>
      </div>
    </div>
  )
}

function ExceptionCard({ item, selected, onSelect, onReclassify, onApprove }: { item: CloseException; selected: boolean; onSelect: () => void; onReclassify: (kind: ExceptionKind) => void; onApprove: () => void }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <article className={`exception-card ${selected ? 'selected' : ''}`}>
      <div className="exception-select"><input type="checkbox" checked={selected} onChange={onSelect} aria-label={`Select ${item.id}`} /></div>
      <div className="exception-main">
        <div className="exception-top"><div><code>{item.id}</code>{item.secondary_tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div><strong>{fmt(item.amount)}</strong></div>
        <h3>{item.items.join(' ↔ ')}</h3>
        <div className="triad">
          <p><span>Found</span>{item.evidence.reasons[0]}</p>
          <p><span>Flagged</span>{item.evidence.reasons[1]}</p>
          <p><span>Recommend</span>{item.suggestion}</p>
        </div>
        {expanded ? <div className="exception-evidence"><strong>Decision boundary</strong><p>{item.evidence.counterfactual}</p></div> : null}
        <div className="exception-actions">
          <button className="text-button" onClick={() => setExpanded((value) => !value)}>{expanded ? 'Hide' : 'View'} evidence <ChevronDown className={expanded ? 'rotated' : ''} size={14} /></button>
          <div><label>Reclassify <select value={item.primary_kind} onChange={(e) => onReclassify(e.target.value as ExceptionKind)}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button className="approve-button" onClick={onApprove}>Approve</button></div>
        </div>
      </div>
    </article>
  )
}

function ReviewInbox({ items, setItems, approveOverride }: { items: CloseException[]; setItems: React.Dispatch<React.SetStateAction<CloseException[]>>; approveOverride: (id: string) => void }) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const grouped = useMemo(() => {
    const groups = new Map<ExceptionKind, CloseException[]>()
    items.filter((item) => item.disposition !== 'auto_resolved').forEach((item) => groups.set(item.primary_kind, [...(groups.get(item.primary_kind) ?? []), item]))
    return [...groups.entries()]
  }, [items])
  const selectedItems = items.filter((item) => selected.has(item.id))
  const bulkEligible = selectedItems.length > 0 && selectedItems.every((item) => item.confidence >= 0.95 && item.policyCovered && item.amount <= 5000 && item.kind !== 'DUPLICATE')
  const updateKind = (id: string, primary_kind: ExceptionKind) => setItems((current) => current.map((item) => item.id === id ? { ...item, primary_kind } : item))
  return (
    <div className="view">
      <div className="page-title title-with-action"><div><span className="eyebrow">13 items · $24,091.03 exposure</span><h1>Review inbox</h1><p>Grouped by primary cause; each decision keeps its own evidence.</p></div><div className="bulk-wrap"><button className="primary-button" disabled={!bulkEligible} onClick={() => { selectedItems.forEach((item) => approveOverride(item.id)); setSelected(new Set()) }}><Check size={15} /> Approve selected</button>{selectedItems.length > 0 && !bulkEligible ? <small>Selection does not meet the ≥95% policy gate.</small> : null}</div></div>
      <div className="trust-banner"><ShieldCheck size={18} /><p><strong>Triage cannot post or close.</strong> It only groups and recommends; you retain approval control.</p></div>
      <div className="inbox-layout">
        <aside className="inbox-filters"><span>Primary cause</span><button className="active">All open <strong>{items.filter((item) => item.disposition !== 'auto_resolved').length}</strong></button>{grouped.map(([kind, group]) => <button key={kind}>{kindLabels[kind]} <strong>{group.length}</strong></button>)}</aside>
        <div className="exception-groups">{grouped.map(([kind, group]) => <section key={kind} className="exception-group"><div className="group-title"><h2>{kindLabels[kind]}</h2><span>{group.length} {group.length === 1 ? 'item' : 'items'}</span></div>{group.map((item) => <ExceptionCard key={item.id} item={item} selected={selected.has(item.id)} onSelect={() => setSelected((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })} onReclassify={(nextKind) => updateKind(item.id, nextKind)} onApprove={() => approveOverride(item.id)} />)}</section>)}</div>
      </div>
    </div>
  )
}

function Policies({ version }: { version: number }) {
  return (
    <div className="view">
      <div className="page-title"><span className="eyebrow">Governed decision rules</span><h1>Matching policies</h1><p>Every human correction becomes a versioned, measurable proposal.</p></div>
      <div className="policy-grid">
        <article className="policy-card featured"><header><div><span>MATCH-01</span><h2>Core matching</h2></div><span className="version">v{version}</span></header><div className="policy-rule"><p><span>Fuzzy threshold</span><strong>{version === 2 ? '0.60' : '0.80'}</strong></p><p><span>Amount tolerance</span><strong>$0.00</strong></p><p><span>Date grace</span><strong>{version === 2 ? '4 days' : '0 days'}</strong></p></div>{version === 2 ? <div className="policy-diff"><span><History size={14} /> Changed from v1</span><p><code>fuzzy_threshold</code><del>0.80</del><ins>0.60</ins></p><p><code>date_grace_days</code><del>0</del><ins>4</ins></p><small>Created by approved controller overrides · EX-011, EX-007</small></div> : <div className="policy-empty"><p>Strict baseline policy. Approve a recommended override in the inbox to generate v2.</p></div>}</article>
        <article className="policy-card"><header><div><span>SHORT-PAY</span><h2>Immaterial variance</h2></div><span className="version">v1</span></header><div className="policy-rule"><p><span>Amount cap</span><strong>$0.50</strong></p><p><span>Minimum confidence</span><strong>95%</strong></p><p><span>Bulk approval</span><strong>Allowed</strong></p></div></article>
        <article className="policy-card"><header><div><span>CONTROL-02</span><h2>Duplicate journals</h2></div><span className="version">v1</span></header><div className="policy-rule"><p><span>Auto-close</span><strong>Never</strong></p><p><span>Required reviewer</span><strong>Controller</strong></p><p><span>Evidence retention</span><strong>7 years</strong></p></div></article>
      </div>
    </div>
  )
}

const Metric = ({ label, before, after, inverse = false }: { label: string; before: number; after: number; inverse?: boolean }) => {
  const improved = inverse ? after < before : after > before
  return <article className="metric-card"><span>{label}</span><div><del>{before}{label === 'Inbox size' ? '' : '%'}</del><ArrowRight size={16} /><strong>{after}{label === 'Inbox size' ? '' : '%'}</strong></div><small className={improved ? 'positive' : ''}>{improved ? 'Improved' : 'No change'}</small></article>
}

function Evaluation({ version }: { version: number }) {
  const improved = version === 2
  return (
    <div className="view">
      <div className="page-title title-with-action"><div><span className="eyebrow">Frozen ground truth · 79 bank / 83 GL</span><h1>Evaluation</h1><p>Measured against labels generated before matcher development.</p></div><button className="secondary-button"><RefreshCw size={15} /> Run evaluation</button></div>
      <section className="eval-hero"><div><span className="eyebrow">Policy comparison</span><h2>{improved ? 'Review made the close materially better.' : 'Strict baseline protects precision.'}</h2><p>{improved ? 'Two approved corrections increased recall and reduced review load without creating a false auto-close.' : 'Approve an override in the inbox to compare policy v2 against this frozen baseline.'}</p></div><div className="zero-card"><ShieldCheck size={22} /><strong>0</strong><span>false auto-closes</span></div></section>
      <div className="metrics-grid"><Metric label="Precision" before={99.4} after={improved ? 99.4 : 99.4} /><Metric label="Recall" before={72.1} after={improved ? 96.2 : 72.1} /><Metric label="F1 score" before={83.5} after={improved ? 97.8 : 83.5} /><Metric label="Inbox size" before={18} after={improved ? 8 : 18} inverse /></div>
      <section className="panel taxonomy-panel"><div className="panel-title"><div><h2>Exception classification</h2><p>Accuracy by primary cause</p></div><span className="status-pill success"><Check size={12} /> 18 labeled exceptions</span></div>{[['Timing difference', improved ? 100 : 75], ['Duplicate', 100], ['Missing entry', 100], ['Amount mismatch', 100], ['Counterparty mismatch', improved ? 100 : 50]].map(([label, value]) => <div className="taxonomy-row" key={label}><span>{label}</span><div><i style={{ width: `${value}%` }} /></div><strong>{value}%</strong></div>)}</section>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState<View>('close')
  const [menuOpen, setMenuOpen] = useState(false)
  const [drawerDecision, setDrawerDecision] = useState<MatchDecision | null>(null)
  const [items, setItems] = useState(initialExceptions)
  const [policyVersion, setPolicyVersion] = useState(1)
  const [toast, setToast] = useState<string | null>(null)
  const approveOverride = (id: string) => {
    const item = items.find((candidate) => candidate.id === id)
    if (!item) return
    setItems((current) => current.map((candidate) => candidate.id === id ? { ...candidate, disposition: 'auto_resolved' } : candidate))
    if (item.kind === 'COUNTERPARTY_MISMATCH' || item.kind === 'TIMING_DIFF') setPolicyVersion(2)
    setToast(item.kind === 'COUNTERPARTY_MISMATCH' || item.kind === 'TIMING_DIFF' ? `${id} approved · MATCH-01 v2 created` : `${id} approved with evidence`)
    window.setTimeout(() => setToast(null), 4000)
  }
  return (
    <div className="app-shell">
      <header className="mobile-header"><button className="icon-button" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="brand-mark"><span>CC</span><strong>Close Copilot</strong></div></header>
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="brand"><div className="brand-mark"><span>CC</span><div><strong>Close Copilot</strong><small>Evidence-first close</small></div></div><button className="icon-button mobile-only" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={18} /></button></div>
        <nav>{navItems.map(({ id, label, icon: Icon, badge }) => <button className={view === id ? 'active' : ''} key={id} onClick={() => { setView(id); setMenuOpen(false) }}><Icon size={17} /><span>{label}</span>{badge ? <strong>{items.filter((item) => item.disposition !== 'auto_resolved').length}</strong> : null}</button>)}</nav>
        <div className="sidebar-bottom"><div className="close-status"><span className="pulse-dot" /><div><strong>August close</strong><small>In controller review</small></div></div><button><CircleAlert size={16} /> Audit log</button></div>
      </aside>
      {menuOpen ? <button className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-label="Close navigation overlay" /> : null}
      <main>{view === 'close' ? <CloseWorkspace openEvidence={setDrawerDecision} /> : null}{view === 'review' ? <ReviewInbox items={items} setItems={setItems} approveOverride={approveOverride} /> : null}{view === 'policies' ? <Policies version={policyVersion} /> : null}{view === 'evaluation' ? <Evaluation version={policyVersion} /> : null}</main>
      {drawerDecision ? <EvidenceDrawer decision={drawerDecision} onClose={() => setDrawerDecision(null)} /> : null}
      {toast ? <div className="toast" role="status"><Check size={16} />{toast}<button onClick={() => setToast(null)} aria-label="Dismiss notification"><X size={14} /></button></div> : null}
    </div>
  )
}
