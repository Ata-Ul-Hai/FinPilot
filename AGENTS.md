# Close Copilot — Build Blueprint & AO Context

**Hackathon:** Syndicate by Maximor · Track 2: Autonomous Office of the CFO · Solo build
**Window:** Sep 5, 12:00 PM EDT → Sep 6, 6:00 PM EDT (deadline 10:00 PM UTC, Sep 6)
**Status:** Final spec — single source of truth for all AO worker sessions.

---

## 0. How to use this document

1. Copy this file to the repo root as `AGENTS.md`. Codex and most AO harnesses auto-read it at session start.
2. Each AO session receives the Task Briefs in §7. Workers MUST read §4 (schema contract) and §5 (eval) before writing code.
3. If code and this document disagree, fix the code or update this file in the same PR. No silent drift.

---

## 1. Hackathon hard facts (non-negotiable)

- **AO usage is mandatory.** "Projects without meaningful AO usage will be disqualified."
- Judging weights: **AO Usage & Build Process 25% · Technical Execution 25% · Track Fit 25% · Demo & Usability 15% · Innovation 10%.**
- Demo video: **3–5 minutes, posted publicly on X or LinkedIn**, must show: the product working end-to-end, **the AO sessions used, and the AO dashboard with the total session count**.
- Devpost submission must include: team name, member names, track, public GitHub repo, live link (if deployed), demo video link, description, explanation of AO usage.
- README must explain: what the project does, which track, the agent workflow, what improved across iterations, demo/live links.
- Join Discord (mandatory), submit on Devpost only.

---

## 2. Product definition

**One-liner:** Close Copilot takes raw month-end files (bank statement CSV + GL/ERP export CSV) and runs the full autonomous close loop — **Ingest → Reconcile → Escalate → Review → Improve** — with every decision carrying a verifiable evidence pack, exceptions triaged into a human review inbox, and a live eval panel proving accuracy improves across policy versions.

**Positioning:** An open, inspectable, zero-onboarding implementation of the patterns Maximor evangelizes (Audit-Ready Agents™, evidence packs, human-in-the-loop, Learn→Run→Escalate→Improve) for teams that live in the CSV/spreadsheet world and are too small for an enterprise rollout. Complement, not competitor.

**Why judges from Maximor will care:** we speak their vocabulary and push one step further on the trust gap they publish themselves (96% want AI, 14% trust it). Our stance: *we don't demand trust — we make it verifiable.* Every decision ships with evidence, confidence, and measured accuracy.

**The demo loop (memorize):**
Drop 2 CSVs → close checklist fills live → open a match's evidence drawer (source rows side-by-side, scores, "why NOT match" counterfactual) → review inbox: inspect a triaged exception → approve an override → policy card bumps v1 → v2 with a visible diff → eval panel re-runs: accuracy delta on screen → CI check on the PR shows the same numbers.

---

## 3. Architecture

```
close-copilot/
├── AGENTS.md                  ← this file
├── schema/
│   └── close.schema.json      ← THE contract (§4). Committed first.
├── backend/                   # FastAPI + SQLite (Python 3.11+)
│   ├── app/
│   │   ├── main.py            # API: /ingest /close /exceptions /review /policies /eval
│   │   ├── ingest.py          # CSV → canonical transactions (Unified-Context-lite)
│   │   ├── matcher.py         # exact → rules → fuzzy (rapidfuzz); deterministic core
│   │   ├── triage.py          # exception classification + inbox grouping (no auto-close)
│   │   ├── policies.py        # versioned policies; override → vNext; diff records
│   │   ├── llm.py             # OPTIONAL pluggable adapter (openai|tensormux|none)
│   │   ├── eval.py            # decisions vs labels.jsonl → metrics
│   │   └── narrate.py         # flux commentary drafting (LLM optional, template fallback)
│   └── tests/                 # pytest; matcher + triage + policies MUST have tests
├── web/                       # Vite + React + TS + Tailwind
│   └── src/views: CloseChecklist · MatchExplorer(evidence drawer) · ReviewInbox ·
│                   PolicyCards(diff view) · EvalPanel · FluxCommentary
├── data/
│   ├── seed/generate_data.py  # builds bank.csv, gl.csv, labels.jsonl (§5)
│   └── sample/                # generated outputs, committed for reproducibility
├── eval/
│   └── labels.jsonl           # ground truth (generated, then FROZEN)
└── .github/workflows/
    └── eval.yml               # pytest + eval on every PR; metrics as check names
```

**Stack rationale:** Python for the engine (pandas + rapidfuzz are the workhorses; deterministic and testable). Vite+React for a fast, pretty dashboard one AI worker can own end-to-end. SQLite = zero-setup demo. Static web build served by FastAPI → the live demo is **one command**.

**LLM policy (decided):**
- Core matching is 100% deterministic. The LLM is optional everywhere.
- LLM jobs ONLY: (1) choose among top-3 fuzzy candidates + explain, (2) suggest exception dispositions, (3) draft flux commentary lines.
- Every LLM call has a deterministic fallback (lower fuzzy threshold + rule, templated commentary). **An API failure can never break the demo.**
- Provider via env: `LLM_PROVIDER=openai|tensormux|none`, `LLM_API_KEY`, `LLM_MODEL`. Recommended: **GPT-5 Nano via AI Grants India participant form** (free for participants).

---

## 4. The contract — `schema/close.schema.json` (commit FIRST, before any feature work)

All workers code against these shapes. Changing the schema requires a PR that updates every consumer — treat it as a public API.

```jsonc
// Transaction (canonical, post-ingest)
{
  "id": "BNK-0007 | GL-0031",
  "source": "bank | gl",
  "date": "2026-08-31",
  "amount": -1234.56,              // signed; bank and GL use same sign convention
  "currency": "USD",
  "counterparty": "Acme Freight",
  "reference": "INV-4471",         // free-text ref from source
  "raw": { "...original row as-is..." }   // never lost — evidence requirement
}

// MatchDecision — output of matcher
{
  "pair": ["BNK-0007", "GL-0031"] | null,
  "status": "matched | exception",
  "method": "exact | rule | fuzzy | llm",
  "confidence": 0.0,               // 0–1, from scoring fn, NOT vibes
  "evidence": {
    "field_scores": { "amount": 1.0, "date_proximity": 0.9, "counterparty": 0.62, "reference": 1.0 },
    "reasons": ["amount exact", "reference INV-4471 appears in both", "counterparty fuzzy 0.62 'Acme Freightt'~'Acme Freight'"],
    "counterfactual": "not auto-matched because counterparty 0.62 < policy v1 threshold 0.80"
  }
}

// Exception — inbox item
{
  "id": "EX-004",
  "kind": "TIMING_DIFF | DUPLICATE | MISSING_ENTRY | AMOUNT_MISMATCH | COUNTERPARTY_MISMATCH | UNKNOWN",
  "primary_kind": "AMOUNT_MISMATCH",       // single primary for grouping
  "secondary_tags": ["possible-timing"],
  "items": ["BNK-0012", "GL-0051"],
  "disposition": "auto_resolved | needs_review | escalated",
  "suggestion": "write-off $0.03 under SHORT-PAY cap" ,   // what we found / why flagged / recommend
  "confidence": 0.91
}

// Policy — versioned, diff-able
{
  "id": "MATCH-01",
  "version": 2,
  "rule": { "fuzzy_threshold": 0.80, "amount_tolerance": 0.0, "date_grace_days": 0 },
  "created_by": "override EX-004 approved by controller",
  "diff_vs_previous": { "fuzzy_threshold": [0.80, 0.60] },
  "eval_impact": { "recall": [0.72, 0.96] }   // filled by eval harness after vNext run
}

// CloseRun — dashboard summary
{
  "run_id": "close-2026-08",
  "counts": { "bank": 79, "gl": 83, "matched": 61, "exceptions": 18, "auto_resolved": 5, "in_inbox": 13 },
  "checklist": [ {"task": "cash reconciliation", "status": "done|in_review|open"} , "..."],
  "je_drafts": [ {"for": "MISSING_ENTRY BNK-0064", "entry": {"dr": "6120 Bank fees", "cr": "1010 Cash", "amount": 38.00}} ]
}
```

**Iron rule (Audit-Ready):** no MatchDecision or disposition may exist without an evidence object. The UI never shows a number it cannot trace to source rows.

---

## 5. Data & eval methodology — "accuracy against what?"

**Ground truth by construction.** `generate_data.py` emits every record from a known seed, so the truth is fixed at generation time, then **frozen** in `eval/labels.jsonl`:

- **61 clean pairs** — same seed → bank row + GL row (guaranteed match)
- **4 timing pairs** — same seed, bank date vs GL date 3–6 days apart
- **3 duplicates** — one bank tx, GL entry booked twice
- **3 missing entries** — bank tx with no GL counterpart
- **4 amount mismatches** — pair exists, amounts differ by $0.01–5.00
- **4 counterparty typos** — same amount/date, name corrupted ("Acme Freight" vs "ACME FRT.")
- Totals: **79 bank tx, 83 GL rows, 18 labeled exceptions.**

`labels.jsonl` line: `{"bank_id": "BNK-0007", "gl_id": "GL-0031", "truth": "matched"|"TIMING_DIFF"|"DUPLICATE"|..., }`

**Metrics (computed by `eval.py`, displayed in EvalPanel and CI):**
- Match precision / recall / F1
- Per-exception-kind classification accuracy
- False auto-closes (auto-resolved items that were actually wrong) — **must be 0**
- Inbox size (review burden)

**The improvement story (measured, never fabricated):**
1. Run with policy v1 (strict: fuzzy 0.80, no date grace) → baseline: high precision, recall ~0.7x, inbox ~18–22.
2. Human reviews inbox → approves counterparty-threshold override + timing grace → policy v2.
3. Re-run → recall 0.9x, inbox shrinks, deltas on the EvalPanel; same numbers appear as CI check names on the policy PR (`eval/recall 0.72→0.96`).

**Why synthetic:** real GL data can't be shown in a public hackathon demo (privacy). The generator encodes realistic mess (typos, dupes, timing) so the benchmark is honest and reproducible. State this framing in the Devpost description.

---

## 6. Triage & trust rules (the "batching must never cause mass mistakes" guarantee)

- Triage = **grouping and labeling only**. It never closes, posts, or writes anything.
- Each exception gets ONE `primary_kind` (for grouping) + optional `secondary_tags` (for honesty about multi-cause items).
- **Bulk-approve gate:** offered only when `confidence ≥ 0.95` AND an explicit policy rule covers the pattern AND amount ≤ policy cap. Everything else = single review.
- Reclassify button on every card → becomes a correction signal → policy candidate (the Improve step).
- Every card shows Maximor's escalation triad: **what we found / why we flagged it / what we recommend.**

---

## 7. AO session plan (solo, Codex-credit-lean)

**3 sessions, each in its own worktree, PR-per-task, reviewer loop:**

| Session | Harness | Owns | Branch |
|---|---|---|---|
| `engine` | Codex | backend/ + tests + eval | `feat/engine-*` |
| `ui` | Codex | web/ views against running API | `feat/ui-*` |
| `reviewer` | Codex (small prompts) | reviews PRs, requests changes, verifies CI | `review/*` |

**Task briefs (paste one per session message — small scope = token economy):**

- **A1 (engine):** implement `ingest.py` + `matcher.py` (exact → rule → rapidfuzz, scoring per §4) + pytest. Acceptance: `pytest` green; running on sample data produces ≥61 exact matches and flags the 4 counterparty typos as COUNTERPARTY_MISMATCH exceptions with evidence objects.
- **A2 (engine):** implement `triage.py` + `policies.py` (classification §6, versioned policies with diffs) + tests. Acceptance: 18 exceptions correctly classified per labels.jsonl; override API bumps policy version with diff record.
- **A3 (engine):** implement `eval.py` + `eval.yml` + `/eval` endpoint. Acceptance: CI check posts precision/recall on PR; EvalPanel JSON matches CLI output.
- **A4 (engine):** `narrate.py` flux commentary (template + optional LLM) + JE drafts for MISSING_ENTRY. Acceptance: close run produces 3 draft JEs that balance; commentary drafts read like controller notes.
- **B1 (ui):** app shell + CloseChecklist + MatchExplorer with evidence drawer (field scores, reasons, counterfactual). Acceptance: dashboard runs off local API, zero console errors.
- **B2 (ui):** ReviewInbox (grouped by primary_kind, bulk-approve gate §6, reclassify) + approve→policy v2 flow with diff toast.
- **B3 (ui):** PolicyCards + EvalPanel (before/after deltas) + FluxCommentary view. Acceptance: full demo loop works without backend restarts.
- **R1–R3 (reviewer):** "Review PR #N against §4/§6: check evidence objects exist on every decision, bulk-approve gate enforced, tests cover the exception taxonomy. Request changes or approve." (Keep reviewer prompts <300 words.)

**Credit economy rules:** scaffold + schema + seed data are pre-committed before sessions start (workers implement, not design). One task per message. Workers must run tests locally before opening a PR. No "build everything" prompts.

---

## 8. Build schedule (26h) with kill-switches

| Hours | Milestone | Kill-switch if behind |
|---|---|---|
| 0–1 | Repo + scaffold + schema + seed data + labels committed; 3 AO sessions live | — |
| 1–5 | A1 done: ingestion + matcher + tests; eval set frozen | Matcher fuzzy-only fallback |
| 5–11 | A2, A3 merged; B1 skeleton | — |
| 11–17 | B1+B2 merged: full inbox + evidence drawer; eval v1 numbers on panel | Drop narrate.py (A4) |
| 17–21 | Feedback loop: override → policy v2 → re-run → delta on EvalPanel + CI | Drop policy diff view (keep version log) |
| 21–24 | README, Devpost draft, deploy (or one-command local), record 3–5 min video incl. AO dashboard | UI → single-page Streamlit fallback |
| 24–26 | Buffer, submit on Devpost | — |

**Non-negotiable core:** deterministic matcher + labeled eval + review inbox + evidence objects + AO footage.

---

## 9. Demo video script (5:00)

- **0:00–0:30** — Problem: the `Recon_Q3_FINAL_v7.xlsx` chaos (email threads, macros on one laptop).
- **0:30–1:15** — **AO dashboard: sessions, worktrees, PRs, total session count** (rule requirement — do not skip).
- **1:15–2:30** — Product: drop CSVs → checklist fills → evidence drawer with counterfactual.
- **2:30–3:30** — Inbox: inspect triaged exception (found/why/recommend) → approve override → policy v1→v2 diff card.
- **3:30–4:15** — EvalPanel before/after numbers + same delta as CI check on the PR.
- **4:15–5:00** — Architecture recap + AO usage summary + what improved across iterations.

---

## 10. Devpost & README checklist

- [ ] Team name + solo member name, Track 2 selected
- [ ] Public GitHub repo, README covers: what it does / track / agent workflow / improvements across iterations / links
- [ ] Demo video posted publicly on X or LinkedIn, link attached
- [ ] AO usage explained (sessions, worktrees, reviewer loop, dashboard session count)
- [ ] Measurable results stated (eval metrics v1 vs v2)
- [ ] Live link if deployed; otherwise one-command local run verified clean-clone
- [ ] Submitted on Devpost before 10:00 PM UTC Sep 6

---

## 11. Risk register

| Risk | Mitigation |
|---|---|
| Codex credits run out | Pre-committed scaffold, tiny scoped tasks, reviewer prompts <300 words; hand-write trivial glue code locally |
| LLM API fails mid-demo | Deterministic core + fallbacks; LLM never on critical path |
| Merge conflicts between engine/ui workers | Schema committed first (§4); API mocked contract for UI via OpenAPI docs |
| Eval numbers look weak | Story is the *delta*, not the absolute; v1 is intentionally strict to show improvement |
| Time slip past hour 21 | Kill-switches in §8; Streamlit fallback UI |
| AO footage forgotten | Video script reserves 0:30–1:15 for it; record AO dashboard b-roll early (hour 5 and hour 17) |
