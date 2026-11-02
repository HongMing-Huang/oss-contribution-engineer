# HISTORICAL — V3 research artifacts

These 16 documents were the **pre-implementation research bundle** for V3
(2026-10-05): V2 audit, comparative matrix, paper synthesis, and 12 design specs.

They are historical input, not current truth. Where they disagree with the code,
the code and `oss-contribution-engineer/CAPABILITIES.json` win. In particular:

- several specs describe capabilities that are ADVISORY or UNIMPLEMENTED
  (AOCI runtime integration, call/reference/inheritance graphs, calibrated
  abstention);
- V4/V5 changed routing (workflow policies replaced unconditional hybrid),
  packing (no-regret guard, span charging), and the state machine (now enforced
  by scripts/contribution_session.py).

Do not extend this directory; executable evidence now lives in
`oss-contribution-engineer/tests/` and `eval/results/`.
