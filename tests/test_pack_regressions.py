#!/usr/bin/env python3
"""Regression tests for the Context Pack builder (pytest).

Each test reproduces a real defect found during V3/V4 operation or an edge case
the goal brief requires. Run: python3 -m pytest tests/test_pack_regressions.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from context_planner import build_pack, goal_query_tokens, symbol_spans  # noqa: E402


def make_goal(intent: str, scope: list[str] | None = None) -> dict:
    return {"digest": "testdigest", "intent": intent, "likely_domains": [],
            "unknowns": [], "scope": [{"path": p, "status": "guess"} for p in (scope or [])]}


def make_plan(cands: list[dict], src_budget: int = 12000, test_budget: int = 4000,
              structural_share: float = 0.0) -> dict:
    return {
        "plan_version": 2, "task_type": "issue2code",
        "token_allocation": {"source": src_budget, "test": test_budget,
                             "cognition": 4000, "history": 2000, "spec": 2000},
        "radius_1": cands,
        "structural_quota": {"max_share": structural_share},
        "excluded_candidates": [],
    }


def cand(path: str, is_test: bool = False, evidence_class: str = "direct") -> dict:
    return {"path": path, "rank": 1, "is_test": is_test,
            "evidence_class": evidence_class,
            "evidence": [{"family": "lexical", "rank": 1}],
            "tier_reason": "test candidate"}


# ---------------------------------------------------------------- defect 1:
# head-only span scan missed a symbol defined late in the file (write_usage @158)
def test_late_symbol_is_delivered(tmp_path: Path):
    body = "def filler_%d():\n    pass\n\n\n" * 1
    lines = ["def unrelated():", "    pass", ""]
    for i in range(120):
        lines += ["def pad_%d():" % i, "    pass", ""]
    lines += ["def target_function():", "    return 42", ""]
    (tmp_path / "big.py").write_text("\n".join(lines))
    pack, _ = build_pack(tmp_path, make_goal("fix target_function behavior"),
                         make_plan([cand("big.py")]))
    spans = [s["symbol"] for s in pack["source_ranges"]]
    assert "target_function" in spans, "late-file symbol must be discoverable (whole-file scan)"


# ---------------------------------------------------------------- defect 2:
# separator-order tokenization: "usage-line" must match symbol "write_usage"
def test_punctuation_normalization_usage_line(tmp_path: Path):
    (tmp_path / "mod.py").write_text(
        "def other():\n    pass\n\n\ndef write_usage(prog):\n    pass\n")
    pack, _ = build_pack(tmp_path, make_goal("fix usage-line rendering"),
                         make_plan([cand("mod.py")]))
    symbols = [s["symbol"] for s in pack["source_ranges"]]
    assert "write_usage" in symbols, "usage-line must tokenize to usage+line and match write_usage"


# ------------------------------------------------------- edge: multiple same-name
def test_multiple_same_name_symbols(tmp_path: Path):
    (tmp_path / "dup.py").write_text(
        "def helper():\n    return 1\n\n\ndef middle():\n    pass\n\n\n"
        "def helper():\n    return 2\n")
    spans = symbol_spans((tmp_path / "dup.py").read_text())
    helpers = [s for s in spans if s[0] == "helper"]
    assert len(helpers) == 2, "same-name symbols must each get their own span"
    pack, _ = build_pack(tmp_path, make_goal("fix helper behavior"),
                         make_plan([cand("dup.py")]))
    got = [(s["symbol"], s["lines"]) for s in pack["source_ranges"]]
    assert sum(1 for sym, _ in got if sym == "helper") == 2, \
        "both same-name spans should be deliverable (per-file cap is 3)"


# ------------------------------------------------------- edge: large file
def test_large_file_span_charging(tmp_path: Path):
    lines = []
    for i in range(2000):
        lines += ["def pad_%d():" % i, "    pass", ""]
    lines += ["def needle():", "    return 1", ""]
    (tmp_path / "huge.py").write_text("\n".join(lines))
    # tiny budget: whole file is ~2000*15*? est tokens >> budget, but the span fits
    pack, _ = build_pack(tmp_path, make_goal("fix needle behavior"),
                         make_plan([cand("huge.py")], src_budget=2000))
    syms = [s["symbol"] for s in pack["source_ranges"]]
    assert "needle" in syms, "span charging must allow the target span inside a huge file"
    assert pack["token_accounting"]["source_used_est"] <= 2000, "budget must hold"


# ------------------------------------------------- edge: query matches path, not symbol
def test_path_match_no_symbol(tmp_path: Path):
    (tmp_path / "auth.py").write_text("def a():\n    return 1\n\n\ndef b():\n    return 2\n")
    # "session" appears only in the path, not in any symbol name
    pack, _ = build_pack(tmp_path, make_goal("fix session handling in auth"),
                         make_plan([cand("auth.py")]))
    assert pack["source_ranges"], "path-match without symbol match must still deliver fallback spans"


# ------------------------------------------------- edge: symbol match without lexical overlap
def test_symbol_match_without_lexical_overlap(tmp_path: Path):
    (tmp_path / "x.py").write_text("def serialize_frame():\n    return 1\n")
    # intent shares no body words with the file; the anchor symbol carries the match
    pack, _ = build_pack(tmp_path, make_goal("investigate the encoder"),
                         make_plan([cand("x.py")]), anchor_symbols=["serialize_frame"])
    syms = [s["symbol"] for s in pack["source_ranges"]]
    assert "serialize_frame" in syms, "anchor symbol must drive matching without lexical overlap"


# --------------------------------------------- structural quota + direct-first order
def test_structural_quota_never_displaces_direct(tmp_path: Path):
    (tmp_path / "direct.py").write_text("def wanted():\n    return 1\n")
    (tmp_path / "hub.py").write_text("def hub():\n    return 2\n")
    cands = [cand("hub.py", evidence_class="structural"),
             cand("direct.py", evidence_class="direct")]
    pack, _ = build_pack(tmp_path, make_goal("fix wanted"),
                         make_plan(cands, structural_share=0.5))
    packed = {s["path"] for s in pack["source_ranges"]}
    assert "direct.py" in packed, "direct evidence must always pack"
    assert "hub.py" in packed, "structural may fill remaining capacity"
    # quota 0: structural excluded entirely, direct unaffected
    pack0, _ = build_pack(tmp_path, make_goal("fix wanted"),
                          make_plan(list(cands), structural_share=0.0))
    packed0 = {s["path"] for s in pack0["source_ranges"]}
    assert "direct.py" in packed0 and "hub.py" not in packed0, \
        "share=0 must reject structural-only candidates without touching direct"


def test_displaced_direct_reported_under_budget_pressure(tmp_path: Path):
    lines: list[str] = ["def giant():"]          # one span > whole budget
    lines += ["    x = %d" % i for i in range(300)]
    lines += [""]
    for i in range(20):
        lines += ["def pad_%d():" % i, "    pass", ""]
    (tmp_path / "first.py").write_text("\n".join(lines))
    (tmp_path / "second.py").write_text("def second_thing():\n    return 1\n")
    cands = [cand("first.py"), cand("second.py")]
    pack, _ = build_pack(tmp_path, make_goal("fix second_thing"),
                         make_plan(cands, src_budget=40))
    assert pack["no_regret"]["displaced_direct"], \
        "direct candidate that lost its slot under budget pressure must be reported"
    assert "second.py" in pack["no_regret"]["displaced_direct"]


def test_tokenizer_splits_separators_before_stripping():
    toks = goal_query_tokens({"intent": "fix usage-line rendering",
                              "likely_domains": [], "unknowns": [], "scope": []}, [])
    assert "usage" in toks and "line" in toks, "separator split must happen before cleanup"
