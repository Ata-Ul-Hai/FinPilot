# FinPilot — 3-Minute Demo Video Script & Shot List

> **Track 2: Autonomous Office of the CFO · Syndicate by Maximor Hackathon**  
> **Duration:** 3:00 minutes (strict pacing)  
> **Core Theme:** *We don't demand trust — we make it verifiable.*

---

## Shot List & Narrative Breakdown

### [0:00 – 0:30] The Hook: The Trust Gap & Spreadsheet Chaos
* **Visual:** Split-screen showing messy Excel reconciliation spreadsheets (`Recon_MonthEnd_vfinal_FINAL2.xlsx`) and the Maximor trust statistic: **96% of finance teams want AI, but only 14% trust it**.
* **Voiceover:**  
  > *"Every month-end close descends into the same chaos: two CSV exports, thousands of transactions, broken macros, and email threads trying to resolve timing gaps and counterparty typos. Finance teams don't avoid AI because they love spreadsheets — they avoid it because 86% don't trust black-box models with their general ledger. FinPilot takes a different stance: we don't ask controllers for trust — we make every close decision verifiable."*

---

### [0:30 – 1:15] AO Dashboard & Build Evidence (Mandatory Requirement)
* **Visual:** Screen-record the **Agent Orchestrator (AO) dashboard**, displaying the total session count, active agent sessions, git worktrees, and the closed PR loop on GitHub.
* **Key Artifacts to Highlight on Screen:**
  - **AO Dashboard:** Total session count and active worker sessions.
  - **Session 1 (`ao/finpilot-3/engine-a1` · PR #1):** Pure deterministic engine (canonical ingestion, rapidfuzz matcher, seed data generator, 24 unit tests, `schema/close.schema.json`, frozen `eval/labels.jsonl`).
  - **Session 2 (`ao/finpilot-4/ui` · PR #2):** Complete React + TypeScript dashboard with evidence drawer and trust gates.
  - **Session 3 (Reviewer session):** Audited both engine and UI PRs, posting review findings on PR #2.
  - **Antigravity integration pass:** Built the FastAPI workspace contract binding UI to engine and wired the GitHub Actions eval CI.
* **Voiceover:**  
  > *"FinPilot was built as a multi-agent relay. Inside Agent Orchestrator, three sessions ran in isolated git worktrees: engine-a1 shipped the deterministic matcher with frozen ground-truth labels as PR #1; the UI session shipped this dashboard as PR #2; a reviewer session audited both with findings posted on the pull requests. The integration layer — the FastAPI contract binding UI to engine, and the eval CI — was completed in a second agentic IDE, Antigravity. Every merge was gated by GitHub Actions running our eval against frozen labels."*

---

### [1:15 – 2:00] Ingest, Reconcile & The Evidence Drawer
* **Visual:** Navigate to `http://localhost:5173` (or `http://localhost:8000`). Select `data/sample/bank.csv` and `data/sample/gl.csv`. Click **Ingest & run close**.
* **Actions on Screen:**
  1. Close checklist rail lights up green: 79 bank rows and 79 GL rows ingested.
  2. Match Explorer loads: 61 matched pairs, 18 exceptions flagged.
  3. Click a matched pair (`BNK-0001 ↔ GL-0001` or `BNK-0018 ↔ GL-0048`).
  4. The slide-over **Evidence Drawer** opens.
  5. Hover over the raw source rows side-by-side, normalized field scores, and the counterfactual boundary statement: *"would not auto-match if reference or amount differed, or date gap exceeded 1d"*.
  6. Hit `Escape` to close the drawer.
* **Voiceover:**  
  > *"We drop in raw bank and GL CSVs. In milliseconds, 61 exact pairs clear deterministic safety gates. When we open any decision's evidence drawer, there is no hallucinated reasoning: raw source rows are displayed side-by-side with exact field scores and an explicit counterfactual boundary showing exactly why this row met policy criteria."*

---

### [2:00 – 2:40] The Money Shot: Review Inbox, Policy Diff & Eval Delta
* **Visual:** Click **Review inbox** in the sidebar navigation.
* **Actions on Screen:**
  1. Show 18 exceptions categorized by primary cause (4 Timing Differences, 3 Duplicates, 3 Missing Entries, 4 Amount Mismatches, 4 Counterparty Mismatches).
  2. Highlight the **Maximor Escalation Triad** on an exception card: **Found / Flagged / Recommend**.
  3. Test the **Bulk Approval Trust Gate**: select a duplicate (`EX-0001`) and a bank fee (`EX-0017`). Point out that the gate safely blocks the duplicate: *"Duplicates always require individual controller approval"*.
  4. Individually approve the `COUNTERPARTY_MISMATCH` exception (`EX-0012`): approve with override to relax fuzzy threshold.
  5. Click **Policies** tab: show `MATCH-01 v2` card displaying the immutable diff: `fuzzy_threshold: 0.80 → 0.60`.
  6. Show live before/after numbers:
     - **Bank rows auto-matched (Close pulse):** $\mathbf{77\% \longrightarrow 82\%}$ ($61 \longrightarrow 65\text{ of }79$)
     - **Inbox size:** $\mathbf{18 \longrightarrow 14}$
     - **Precision (vs frozen labels):** $\mathbf{100\% \longrightarrow 100\%}$
     - **Recall (vs frozen labels):** $\mathbf{100\% \longrightarrow 100\%}$
     - **False auto-closes:** $\mathbf{0 \longrightarrow 0}$
* **Voiceover:**  
  > *"In the Review Inbox, exceptions are triaged with Maximor's triad: what we found, why we flagged it, and what we recommend. Our trust gate prevents batching errors — duplicates and high exposures are strictly quarantined for individual review. When our controller approves a counterparty typo override, Policy MATCH-01 bumps from v1 to v2 with a visible parameter diff. Immediately, the close pulse climbs from 77 to 82 percent of bank rows auto-matched, the inbox drops to 14, and against frozen labels precision and recall stay pinned at 100 with zero false auto-closes."*

---

### [2:40 – 3:00] Automated CI Verification & Wrap-Up
* **Visual:** Switch briefly to GitHub Actions PR view (`eval.yml`) showing the exact same metrics evaluated automatically in CI, then back to the **Flux Commentary** tab showing balanced journal entry drafts ($\text{Dr 6120 / Cr 1010}$).
* **Voiceover:**  
  > *"Every policy evolution runs the exact same test harness in GitHub Actions CI. Approved adjustments draft balanced debits and credits ready for controller sign-off without touching production ledgers. That is FinPilot: Audit-Ready Agents for the Autonomous Office of the CFO."*

---

## Recording Checklist
- [ ] Record AO Dashboard b-roll early showing session count and worktrees.
- [ ] Clear browser cache / ensure sidebar badge reads `Live API`.
- [ ] Confirm hotkeys (`Escape` on drawer) work smoothly.
- [ ] Verify audio levels and upload to X or LinkedIn within the 3–5 minute hackathon rule.
