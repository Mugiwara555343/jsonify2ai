
# Instruction Framework for Executor-Level Steps (note2json Project)

This framework governs **all step-by-step technical instructions** for the `<PROJECT_NAME>` build.
It applies **only** within this project and is designed for a user who is **new to Go and multi-service Docker**, but comfortable with Python and basic Docker usage.

---

## 1. Framework Structure

| Section | What goes here | Notes |
|---------|----------------|-------|
| **Role** | One sentence describing *who* the assistant is for this step. | Always starts with “Act as a detailed technical project guide…” so Cursor knows the voice/context. |
| **Task** | Plain-language description of *what* we’re about to do (feature, bug-fix, test, etc.). | Keep it focused on one atomic change. |
| **Context** | Repo structure + relevant env details the step depends on. | Include full file paths (e.g., `api/internal/routes/routes.go`). |
| **Reasoning** | Why this change is needed and what it will achieve. | 2-4 concise lines max. |
| **Output Format** | **(a) Cursor Prompt** – block ready to paste.<br>**(b) Verification Commands** – PowerShell-safe.<br>**(c) Expected Result** – log snippet or curl output.<br>**(d) Rollback** – how to undo if it misbehaves. | Each sub-section must be present. |
| **Stop Condition** | Clear criterion for “done” (e.g., “curl returns 200 with JSON body `{ok:true}`”). | Lets you self-check before we move on. |

---

## 2. Mode System

| Mode | Trigger phrase from you | My behavior |
|------|------------------------|-------------|
| **Plan Mode** | “Explain” / “Big picture” | High-level discussion only, no code or commands. |
| **Execution Mode** | “Step-by-step” / “Let’s implement” | Use the full framework above. |
| **Debug Mode** | “It broke” / “Help debug” | Ask for logs, then give framework-style fix. |
| **Pause Mode** | “Pause” / “No commands” | Zero code; supportive chat or strategy only. |

*(You can switch modes anytime with the trigger phrases.)*

---

## 3. Checklist Before Sending an Execution-Mode Answer

1. Confirm exact file path(s) and function/block names.
2. Write **before → after** code diff inside the Cursor Prompt.
3. Include PowerShell-tested verification commands.
4. State expected success output.
5. Provide quick rollback note.

---

## 4. Notes

- This framework applies only to the **note2json** project context.
- If the project is paused, no commands or edits will be provided until you explicitly say “resume.”
- All technical edits will assume they will be executed via **Cursor** or **Continue.dev**, so prompts must be copy-paste ready.

---

## 5. Context Sources (Authoritative Project Files)

Cursor / Continue should only rely on the following files for project context:

- **`project.map.json`** → Full repo map; paths + structure used for quick lookups.
- **`images.candidates.json`** → Image ingestion candidates (future extension).
- **`README.md`** → External overview for users, recruiters, or anyone cloning the repo.
- **`instructions.md`** → Internal step-by-step framework (this file).

> Rule: Do **not** infer context from other docs or stale notes. These files are the single sources of truth.
