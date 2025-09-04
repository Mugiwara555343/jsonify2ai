.PHONY: up down logs ps

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

snapshot:
	@mkdir -p snapshots
	@git ls-files > snapshots/git_files.txt
	@git status -sb > snapshots/git_status.txt
	@tree -a -I ".git|node_modules|.venv|__pycache__" -n > snapshots/tree_full.txt || powershell -Command "tree /A /F > snapshots/tree_full.txt"
	@tree -da -I ".git|node_modules|.venv|__pycache__" -n > snapshots/tree_dirs.txt || powershell -Command "tree /A > snapshots/tree_dirs.txt"
	@PYTHONPATH=$$(pwd) python - << 'PY' > snapshots/python_probe.txt ; \
import sys, importlib.util, pathlib, os, json ; \
print("cwd:", pathlib.Path().resolve()) ; \
print("PYTHONPATH:", os.environ.get("PYTHONPATH")) ; \
print("sys.path[0:5]:", json.dumps(sys.path[0:5], ensure_ascii=False, indent=2)) ; \
spec = importlib.util.find_spec("worker.app.config") ; \
print("worker.app.config found?:", bool(spec), "origin:", getattr(spec, "origin", None))
PY
