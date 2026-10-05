# Validation Report — <change>

> Generated from the evidence manifest (`scripts/validation_report.py --markdown`).
> Every command shows its true status; SKIPPED/UNAVAILABLE stays visible.

| Command | Purpose | Executed | Result | Evidence |
|---------|---------|----------|--------|----------|
| `<command>` | RED proof on unmodified upstream | yes | PASS/FAIL | artifact path (sha256 …, exit …) |
| `<command>` | GREEN after fix | yes | | |
| `<command>` | neighbor tests | yes / no | PASS / SKIPPED | reason if skipped |
| `<command>` | package suite | | | |
| `<command>` | formatter/lint/typecheck | | | |
| `<command>` | build | | | |
| `<command>` | integration | | | |
| `<command>` | live external validation | | | never fabricated |

## Summary
<!-- executed / passed / failed / not-executed counts -->

## Conclusion
<!-- PASSED / INCOMPLETE — n steps not executed / FAILED -->

## Untested areas (explicit)
<!-- what was NOT tested and why; what could differ in CI or other environments -->

## Evidence artifacts
<!-- paths under .oss-contrib-evidence/; verify hashes with evidence_manifest.py verify -->
