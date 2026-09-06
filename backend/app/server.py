"""FastAPI application for Close Copilot workspace API."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.eval import evaluate_decisions, load_labels, run_evaluation
from backend.app.ingest import ingest_pair
from backend.app.matcher import match_transactions
from backend.app.narrate import draft_journal_entry, generate_commentary
from backend.app.policies import Policy, load_policy, save_policy
from backend.app.triage import DEFAULT_REVIEW_RULES, bulk_approval_gate

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "out"
UPLOAD_DIR = OUT_DIR / "uploads"
STATE_FILE = OUT_DIR / "run_state.json"
DEFAULT_BANK = ROOT / "data" / "sample" / "bank.csv"
DEFAULT_GL = ROOT / "data" / "sample" / "gl.csv"
POLICY_FILE = ROOT / "backend" / "app" / "policies.json"
LABELS_FILE = ROOT / "eval" / "labels.jsonl"
DIST_DIR = ROOT / "dist"

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    state.initialize()
    yield

app = FastAPI(title="Close Copilot API", version="0.1.0", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models for Requests ---

class ReclassifyRequest(BaseModel):
    exception_id: str
    primary_kind: str


class ReviewRequest(BaseModel):
    exception_id: str
    action: str = "approve"
    applicable_policy_id: str | None = None


class BulkApproveRequest(BaseModel):
    exception_ids: list[str]


# --- State Management ---

class CloseState:
    def __init__(self) -> None:
        self.run_id: str = "close-2026-08"
        self.bank_path: Path = DEFAULT_BANK
        self.gl_path: Path = DEFAULT_GL
        self.transactions: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.exceptions: list[dict[str, Any]] = []
        self.policies: list[dict[str, Any]] = []
        self.review_rules: list[dict[str, Any]] = list(DEFAULT_REVIEW_RULES)
        self.baseline_evaluation: dict[str, Any] = {}
        self.current_evaluation: dict[str, Any] = {}
        self.je_drafts: list[dict[str, Any]] = []
        self.checklist: list[dict[str, str]] = [
            {"task": "Source files ingested", "status": "done"},
            {"task": "Cash reconciliation", "status": "done"},
            {"task": "Exceptions triaged", "status": "done"},
            {"task": "Controller review", "status": "in_review"},
        ]

    def initialize(self) -> None:
        if STATE_FILE.exists():
            try:
                self.load_from_disk()
                return
            except Exception:
                pass

        # Cold start
        active_policy = load_policy(POLICY_FILE)
        self.policies = [active_policy.to_dict()]
        self.run_reconciliation(save=True)

    def run_reconciliation(self, save: bool = True) -> None:
        bank_txs, gl_txs = ingest_pair(self.bank_path, self.gl_path)
        self.transactions = [*bank_txs, *gl_txs]

        current_policy_dict = self.policies[-1]
        active_policy = Policy.from_dict(current_policy_dict)

        records = match_transactions(bank_txs, gl_txs, active_policy)

        # Separate matched decisions vs exceptions
        matched: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []

        # Preserve previously resolved statuses if rerun
        existing_dispositions = {ex["id"]: ex["disposition"] for ex in self.exceptions}
        existing_primary_kinds = {ex["id"]: ex["primary_kind"] for ex in self.exceptions if "primary_kind" in ex}

        for record in records:
            if record.get("status") == "matched":
                matched.append(dict(record))
            else:
                ex = dict(record)
                ex_id = ex["id"]
                if ex_id in existing_dispositions:
                    ex["disposition"] = existing_dispositions[ex_id]
                if ex_id in existing_primary_kinds:
                    ex["primary_kind"] = existing_primary_kinds[ex_id]
                exceptions.append(ex)

        self.decisions = matched
        self.exceptions = exceptions

        # Compute eval
        labels = load_labels(LABELS_FILE) if LABELS_FILE.exists() else []
        eval_metrics = evaluate_decisions(records, labels, policy_version=active_policy.version)

        if not self.baseline_evaluation or active_policy.version == 1:
            self.baseline_evaluation = dict(eval_metrics)
        self.current_evaluation = dict(eval_metrics)

        # Update latest policy eval impact
        if len(self.policies) > 1:
            self.policies[-1]["eval_impact"] = {
                "recall": [self.baseline_evaluation.get("recall", 1.0), self.current_evaluation.get("recall", 1.0)]
            }

        # Update checklist status
        in_inbox = sum(1 for e in self.exceptions if e.get("disposition") != "auto_resolved")
        self.checklist[3]["status"] = "in_review" if in_inbox > 0 else "done"

        if save:
            self.save_to_disk()

    def get_counts(self) -> dict[str, int]:
        bank_count = sum(1 for t in self.transactions if t.get("source") == "bank")
        gl_count = sum(1 for t in self.transactions if t.get("source") == "gl")
        matched_count = len(self.decisions)
        ex_count = len(self.exceptions)
        auto_resolved = sum(1 for e in self.exceptions if e.get("disposition") == "auto_resolved")
        in_inbox = ex_count - auto_resolved
        return {
            "bank": bank_count,
            "gl": gl_count,
            "matched": matched_count,
            "exceptions": ex_count,
            "auto_resolved": auto_resolved,
            "in_inbox": in_inbox,
        }

    def get_snapshot(self) -> dict[str, Any]:
        counts = self.get_counts()
        run = {
            "run_id": self.run_id,
            "counts": counts,
            "checklist": self.checklist,
            "je_drafts": self.je_drafts,
        }
        eval_comparison = {
            "baseline": self.baseline_evaluation,
            "current": self.current_evaluation,
        }
        commentary = generate_commentary(
            self.run_id, counts, self.exceptions, self.policies, eval_comparison
        )
        return {
            "run": run,
            "transactions": self.transactions,
            "decisions": self.decisions,
            "exceptions": self.exceptions,
            "policies": self.policies,
            "review_rules": self.review_rules,
            "evaluation": eval_comparison,
            "commentary": commentary,
        }

    def save_to_disk(self) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "run_id": self.run_id,
            "bank_path": str(self.bank_path),
            "gl_path": str(self.gl_path),
            "policies": self.policies,
            "review_rules": self.review_rules,
            "baseline_evaluation": self.baseline_evaluation,
            "current_evaluation": self.current_evaluation,
            "je_drafts": self.je_drafts,
            "exceptions": self.exceptions,
        }
        STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_from_disk(self) -> None:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        self.run_id = data.get("run_id", "close-2026-08")
        self.bank_path = Path(data.get("bank_path", DEFAULT_BANK))
        self.gl_path = Path(data.get("gl_path", DEFAULT_GL))
        self.policies = data.get("policies", [])
        self.review_rules = data.get("review_rules", list(DEFAULT_REVIEW_RULES))
        self.baseline_evaluation = data.get("baseline_evaluation", {})
        self.current_evaluation = data.get("current_evaluation", {})
        self.je_drafts = data.get("je_drafts", [])
        self.exceptions = data.get("exceptions", [])
        self.run_reconciliation(save=False)


state = CloseState()





# --- Endpoint Implementations ---

@app.get("/close")
def get_close() -> dict[str, Any]:
    """Returns the FULL WorkspaceSnapshot containing both 'run' and 'decisions'."""
    return state.get_snapshot()


@app.post("/close")
def rerun_close() -> dict[str, Any]:
    state.run_reconciliation(save=True)
    return state.get_snapshot()


@app.get("/transactions")
def get_transactions() -> list[dict[str, Any]]:
    return state.transactions


@app.get("/matches")
def get_matches() -> list[dict[str, Any]]:
    return state.decisions


@app.get("/exceptions")
def get_exceptions() -> list[dict[str, Any]]:
    return state.exceptions


@app.get("/policies")
def get_policies() -> list[dict[str, Any]]:
    return state.policies


@app.get("/policies/review-rules")
def get_review_rules() -> list[dict[str, Any]]:
    return state.review_rules


@app.get("/commentary")
def get_commentary() -> list[dict[str, Any]]:
    snapshot = state.get_snapshot()
    return snapshot["commentary"]


@app.get("/eval")
def get_eval() -> dict[str, Any]:
    return {
        "baseline": state.baseline_evaluation,
        "current": state.current_evaluation,
    }


@app.post("/eval")
def post_eval() -> dict[str, Any]:
    current_policy = Policy.from_dict(state.policies[-1])
    labels = load_labels(LABELS_FILE) if LABELS_FILE.exists() else []
    records = [*state.decisions, *state.exceptions]
    metrics = evaluate_decisions(records, labels, policy_version=current_policy.version)
    state.current_evaluation = metrics
    state.save_to_disk()
    return state.get_snapshot()


@app.post("/ingest")
async def post_ingest(
    bank: UploadFile = File(...),
    gl: UploadFile = File(...),
) -> dict[str, Any]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    bank_dst = UPLOAD_DIR / f"bank_{bank.filename}"
    gl_dst = UPLOAD_DIR / f"gl_{gl.filename}"

    with bank_dst.open("wb") as buffer:
        shutil.copyfileobj(bank.file, buffer)
    with gl_dst.open("wb") as buffer:
        shutil.copyfileobj(gl.file, buffer)

    state.bank_path = bank_dst
    state.gl_path = gl_dst
    state.run_reconciliation(save=True)
    return state.get_snapshot()


@app.post("/review/reclassify")
def post_reclassify(body: ReclassifyRequest) -> dict[str, Any]:
    found = False
    for ex in state.exceptions:
        if ex.get("id") == body.exception_id:
            ex["primary_kind"] = body.primary_kind
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Exception {body.exception_id} not found")

    state.save_to_disk()
    return state.get_snapshot()


@app.post("/review")
def post_review(body: ReviewRequest) -> dict[str, Any]:
    exception_item = next(
        (ex for ex in state.exceptions if ex.get("id") == body.exception_id),
        None,
    )
    if not exception_item:
        raise HTTPException(status_code=404, detail=f"Exception {body.exception_id} not found")

    # Mark resolved
    exception_item["disposition"] = "auto_resolved"

    # Draft balanced journal entry if applicable
    je = draft_journal_entry(exception_item)
    if je and not any(d["for"] == je["for"] for d in state.je_drafts):
        state.je_drafts.append(je)

    # Check for policy progression
    latest_dict = state.policies[-1]
    latest = Policy.from_dict(latest_dict)
    kind = exception_item.get("primary_kind") or exception_item.get("kind")

    new_rule_params: dict[str, Any] = {
        "fuzzy_threshold": latest.fuzzy_threshold,
        "amount_tolerance": latest.amount_tolerance,
        "date_grace_days": latest.date_grace_days,
    }
    diff: dict[str, list[float]] = {}

    if kind == "COUNTERPARTY_MISMATCH" and latest.fuzzy_threshold > 0.60:
        new_rule_params["fuzzy_threshold"] = 0.60
        diff["fuzzy_threshold"] = [latest.fuzzy_threshold, 0.60]
    elif kind == "TIMING_DIFF" and latest.date_grace_days < 4:
        new_rule_params["date_grace_days"] = 4
        diff["date_grace_days"] = [latest.date_grace_days, 4]
    elif kind == "AMOUNT_MISMATCH" and latest.amount_tolerance < 0.05:
        new_rule_params["amount_tolerance"] = 0.05
        diff["amount_tolerance"] = [latest.amount_tolerance, 0.05]

    if diff:
        new_version = latest.version + 1
        new_policy = Policy(
            id=latest.id,
            version=new_version,
            fuzzy_threshold=new_rule_params["fuzzy_threshold"],
            amount_tolerance=new_rule_params["amount_tolerance"],
            date_grace_days=new_rule_params["date_grace_days"],
            created_by=f"override {body.exception_id} approved by controller",
            diff_vs_previous=diff,
            eval_impact={},
        )
        state.policies.append(new_policy.to_dict())
        save_policy(new_policy, POLICY_FILE)
        # Re-run reconciliation to update matches under new policy
        state.run_reconciliation(save=True)
    else:
        state.save_to_disk()

    return state.get_snapshot()


@app.post("/review/bulk-approve")
def post_bulk_approve(body: BulkApproveRequest) -> dict[str, Any]:
    approved: list[str] = []
    rejected: list[dict[str, Any]] = []

    for ex_id in body.exception_ids:
        item = next((e for e in state.exceptions if e.get("id") == ex_id), None)
        if not item:
            rejected.append({"id": ex_id, "reason": "Exception not found"})
            continue

        gate = bulk_approval_gate(item, state.review_rules)
        if not gate["eligible"]:
            rejected.append({"id": ex_id, "reason": gate["reason"]})
            continue

        # Approve
        item["disposition"] = "auto_resolved"
        approved.append(ex_id)

        # Draft journal entry if applicable
        je = draft_journal_entry(item)
        if je and not any(d["for"] == je["for"] for d in state.je_drafts):
            state.je_drafts.append(je)

    state.save_to_disk()
    return {
        "approved": approved,
        "rejected": rejected,
        "snapshot": state.get_snapshot(),
    }


# Mount built static web UI if available
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")
