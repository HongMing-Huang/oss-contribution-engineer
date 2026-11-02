#!/usr/bin/env python3
"""Capability-claim verification: every ENFORCED capability in CAPABILITIES.json
must cite automated test evidence (test file + test id), and every cited test id
must exist in the test files. A claim without executable evidence fails this test.

Run: python3 -m pytest tests/test_capability_claims.py -q
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
LEDGER = SKILL / "CAPABILITIES.json"
TESTS = SKILL / "tests"


def test_every_enforced_capability_has_test_evidence():
    ledger = json.loads(LEDGER.read_text())
    failures = []
    for name, cap in ledger["capabilities"].items():
        if cap.get("status") != "ENFORCED":
            continue
        evidence = cap.get("tests") or []
        if not evidence:
            failures.append(
                "capability %r is ENFORCED but lists no automated tests — "
                "downgrade the claim or add tests" % name)
            continue
        for ref in evidence:
            # ref format: "<test-file>#<test-name>"
            if "#" not in ref:
                failures.append(
                    "capability %r cites %r without '#<test-name>' — use "
                    "tests/<file>.py#test_<name>" % (name, ref))
                continue
            rel, test_name = ref.split("#", 1)
            tf = SKILL / rel
            if not tf.exists():
                failures.append("capability %r cites missing test file %s"
                                % (name, rel))
                continue
            text = tf.read_text()
            if not re.search(r"def %s\b" % re.escape(test_name), text):
                failures.append(
                    "capability %r cites %s but test %s does not exist in it"
                    % (name, ref, test_name))
    assert not failures, "capability-claim violations:\n" + "\n".join(failures)


def test_all_capabilities_use_known_status_values():
    ledger = json.loads(LEDGER.read_text())
    known = {"ENFORCED", "IMPLEMENTED", "ADVISORY", "EXPERIMENTAL", "UNIMPLEMENTED",
             "UNAVAILABLE"}
    for name, cap in ledger["capabilities"].items():
        assert cap.get("status") in known, "capability %r has unknown status %r" % (
            name, cap.get("status"))
