# Scripts

Canonical entry points for the jsonify2ai stack.

### Stack Management
- `scripts/start_all.sh` (or `.ps1`): **Start stack**. Launches all docker-compose services (api, worker, web, qdrant) in detached mode.
- `scripts/stop_all.sh` (or `.ps1`): **Stop stack**. Stops all running services.

### Verification
- `scripts/dev/smoke_http.sh`: **Golden path smoke**. Runs a full end-to-end test (Upload -> Search -> Ask -> Export).
- `scripts/ensure_tokens.sh` (or `.ps1`): **Verify env/tokens**. Generates or validates JWT tokens for authentication.
- `scripts/doctor.ps1`: **Doctor**. diagnostics script to check environment health.

### Organization
- `scripts/`: Canonical entry points aimed at general usage.
- `scripts/dev/`: Development scripts and smoke tests kept for compatibility.
- `scripts/dev/tools/`: Internal tooling, heavy-lifting scripts, and non-canonical utilities.
- `scripts/_archive/`: Deprecated or superseded scripts.
