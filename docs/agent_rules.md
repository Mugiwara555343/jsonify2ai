# Agent Operating Rules

This policy governs AI agent behavior within the `jsonify2ai` repository.

## Modes

### 1. READ-ONLY Mode (Analysis)
- **Goal:** Understand system state, debug, or verify.
- **Allowed:** `grep`, `cat`, `ls`, `curl`, logs analysis.
- **Forbidden:** Modifying any file, restarting services (unless asked).

### 2. CHANGE Mode (Edit)
- **Goal:** Implement features, fix bugs, or refute invariants.
- **Requirements:**
  1. **Contract Check:** If altering `worker` routers or `api` routes, update `docs/contracts.md`.
  2. **Golden Path:** After *any* code change, you MUST verify `docs/golden_path.md` (or at least the relevant subset) passes.
  3. **Rebuild:** If modifying `web` or `api`, you MUST assume a rebuild is needed (`docker compose up -d --build`).

## Forbidden Behaviors
- **NO** assuming ports (always check `.env` or `docker-compose.yml`).
- **NO** "fixing" unrelated style issues while debugging.
- **NO** bypassing invariants (e.g., hardcoding IDs).
- **NO** using `localhost` inside containers (use service names).

## PR / Summary Template
Every task completion notification must include:

```markdown
## Change Summary
- **Mode:** [Read-only | Change]
- **Files Touched:** ...
- **Contracts Updated:** [Yes/No/N/A]
- **Golden Path Verified:** [Yes (Steps X-Y) | No]
- **Rebuild Required:** [Yes/No]

## Root Cause (if bug fix)
[Explanation]
```
