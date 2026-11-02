# Ecosystem Guides (portability)

This skill is written to the vendor-neutral Agent Skills standard
(https://agentskills.io/specification). This file records what varies between agents and
how to adapt — none of it is required to use the core workflow.

## What the standard guarantees

A skill is a directory with `SKILL.md` (frontmatter: `name`, `description` required;
`license`, `compatibility`, `metadata`, `allowed-tools` optional) plus optional
`scripts/`, `references/`, `assets/`. Agents load name+description at startup, the body
on activation, and bundled files on demand. This skill uses only the spec fields in
frontmatter, so it is portable as-is.

## Per-agent notes (as of 2026-10; verify in each agent's docs)

| Agent | Discovery | Notes |
|-------|-----------|-------|
| Claude Code | `~/.claude/skills/`, `.claude/skills/`, plugin skills | also supports `.agents/skills/` via compatibility layers; rejects reserved names (no "claude"/"anthropic" in `name` — this skill's name is safe); `allowed-tools` syntax extends the spec |
| OpenAI Codex | `.agents/skills/` scanned from cwd to repo root, `~/.agents/skills/` | skill list capped (~2% context / 8k chars) — descriptions get shortened, so trigger words must be front-loaded (they are); explicit invocation via `/skills` or `$skill-name`; optional `agents/openai.yaml` is NOT needed |
| Cursor | `.cursor/skills/`, `.agents/skills/` | supports standard format |
| Gemini CLI | `.gemini/skills/` (and standard paths) | supports standard format |
| GitHub Copilot / VS Code | `.github/skills/`, repo/user levels | standard format |
| Others (Goose, Amp, OpenCode, OpenHands…) | see agentskills.io client showcase | standard format |

## Installation

Copy the folder to one of:

- project scope: `<repo>/.agents/skills/oss-contribution-engineer/`
- user scope: `~/.agents/skills/oss-contribution-engineer/` (Claude Code users:
  `~/.claude/skills/oss-contribution-engineer/`)

Then start a session and invoke by name or by task ("help me contribute to this repo").
Validate the folder anytime with `skills-ref validate` if available, or check the
frontmatter rules manually (name matches directory, description ≤1024 chars).

## Deliberate limitations

- **No `allowed-tools` reliance** — support is experimental and varies; permissions are
  enforced by the workflow (READ_ONLY / WORKTREE_EDIT / REMOTE_WRITE), not frontmatter.
- **No vendor hooks/slash-commands** — behavior is ordinary instructions, so any
  spec-conforming agent can run it.
- **Scripts need python3 + git** (`compatibility` field documents this); scripts never
  touch the network — `duplicate_work_scan.py` prints capture commands for `gh` and then
  parses the captured JSON, so the data source can be `gh` or any platform GitHub tool
  (record which tool captured the data).
- **No automatic publishing** — REMOTE_WRITE actions are user-authorized per action
  regardless of agent capabilities.

## Adapting to a specific agent (optional)

If an agent supports richer integration you may add, *without editing SKILL.md*:
- an `AGENTS.md`/`CLAUDE.md` snippet telling the agent to load this skill for
  OSS-contribution tasks,
- vendor frontmatter in a *copied* variant (e.g., `disable-model-invocation` for
  Claude Code if you want invocation to be manual only),
- an `agents/openai.yaml` for Codex UI metadata.

Keep the canonical folder spec-clean so upgrades and sharing stay portable.
