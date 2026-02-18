# Walkthrough — Frontend Bloat Surgical Removal

## Summary

Surgically removed ~1,200 lines of dead code from the jsonify2ai frontend, preparing it for a minimalist rebuild. The TypeScript build passes cleanly with zero errors.

## Changes Made

### [App.tsx](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/App.tsx) — Core removals (~1,200 lines)

| Category | Items Removed |
|---|---|
| **Imports** | [QuickActions](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/QuickActions.tsx#69-199), [LLMOnboardingPanel](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/LLMOnboardingPanel.tsx#15-129), [IngestionActivity](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/IngestionActivity.tsx#34-219), [DocumentList](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/DocumentList.tsx#53-379) |
| **Types** | [IngestActivityItem](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/App.tsx#17-29), [IngestionEvent](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/App.tsx#80-90), telemetry fields from [Status](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/AskPanel.tsx#5-16) |
| **State variables** | `demoLoading`, `quickActionResult`, `quickActionsLoading`, `quickActionName`, `quickActionError`, `activityFeed`, `showDropzoneHelp`, `showWhatIsThis`, `hideIngestionActivity`, `docSearchFilter`, `docSortBy`, `openMenuDocId`, `selectedDocIds` |
| **Functions** | `loadDemoData`, `handleStartHere`, `handleBulkDelete`, `handleQuickActionComplete/Error`, activity feed helpers, [showIngestionActivity](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/App.tsx#437-444) |
| **useEffects** | localStorage activity feed, overflow menu clicks, activity feed re-matching, `BUILD_STAMP` mount |
| **JSX blocks** | 3-step strip, Start Here button, "What is this?", BUILD_STAMP display, System Status accordion, telemetry chips, IngestionActivity feed, Dropzone help, LLMOnboardingPanel, DocumentList (with ~120 lines of props/handlers) |

### New additions

- **`topK`** state variable (default `6`) replaces hardcoded `k = 6` in [handleAsk](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/App.tsx#524-573)
- **[AssistantOutput](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/AssistantOutput.tsx#70-394)** props set to neutral defaults (`result={null}`, `loading={false}`, etc.)

---

### [theme.ts](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/theme.ts) — Dark mode default
Changed default theme from system-detected to always dark.

### [App.css](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/App.css) — Dark-first base styles
Rewrote to dark-mode-first, removed all hardcoded `#ffffff` backgrounds.

### [types.ts](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/types.ts) — New shared types
Created to hold the [Document](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/IngestionActivity.tsx#15-21) type previously exported from deleted [IngestionActivity.tsx](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/IngestionActivity.tsx).

### [DocumentDrawer.tsx](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/DocumentDrawer.tsx)
- Import redirected from [./IngestionActivity](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/IngestionActivity.tsx#34-219) → `../types`
- `openMenuDocId` made optional
- Removed `setSelectedDocIds` / `setOpenMenuDocId` from delete handler

### [AskPanel.tsx](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/AskPanel.tsx)
- Import redirected from [./IngestionActivity](file:///c:/Users/Mugi/Desktop/jsonify2ai-main/web/src/components/IngestionActivity.tsx#34-219) → `../types`

## Verification

```
npx tsc --noEmit → 0 errors ✓
```
