#!/usr/bin/env bash
# commit-safe-code.sh — Allowlisted code/docs commit + push (no runtime/secrets).
#
# Intended for daily Hermes cron via git-daily-management.sh.
# Stages only known source paths; hard-excludes state/logs/trades/secrets;
# skips oversized blobs; scans staged text for secret-like patterns.
#
# Usage:
#   ./scripts/hermes/git/commit-safe-code.sh
#   ./scripts/hermes/git/commit-safe-code.sh --dry
#   ./scripts/hermes/git/commit-safe-code.sh --no-push
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

DRY=false
NO_PUSH=false
for arg in "${@:-}"; do
  case "$arg" in
    --dry) DRY=true ;;
    --no-push) NO_PUSH=true ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
  esac
done

TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
MAX_BYTES=${SAFE_CODE_MAX_BYTES:-2097152}  # 2 MiB per file default

echo "=== Safe code commit @ ${TIMESTAMP} ==="
echo "Project: $PROJECT_ROOT"
echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
echo "Max file size: ${MAX_BYTES} bytes"
if [[ "$DRY" == true ]]; then echo "Mode: DRY (no commit/push)"; fi

# Build candidate list via Python (classification + gates).
mapfile -t CANDIDATES < <(python3 - "$PROJECT_ROOT" "$MAX_BYTES" <<'PY'
import os, re, subprocess, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
max_bytes = int(sys.argv[2])
os.chdir(root)

# Prefix allowlist (directories relative to repo root)
ALLOW_DIRS = (
    "phase6/",
    "trading/",
    "config/",
    "docs/",
    "scripts/",
    "db/",
    "handoffs/",
    "systemd/",
    "provisioning/",
    "hermes-state/",
    "apps/",
    "web/",
    "ui/",
)

# Exact root files allowed
ALLOW_ROOT_FILES = {
    ".env.example",
    ".gitignore",
    ".hermes.md",
    "AGENTS.md",
    "README.md",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "crypto-dashboard.service",
    "phase6_dashboard.html",
    "serve_dashboard.py",
    "fetch_reddit_sentiment.py",
    "fetch_x_sentiment.py",
    "fetch_fng_sentiment.py",
    "fetch_funding_sentiment.py",
    "fetch_rss_sentiment.py",
    "combined_strategy_backtest.py",
    "run_backtest.sh",
    "test_t0_registry.py",
}

# Hard deny substrings / prefixes (never stage)
DENY_PREFIXES = (
    "data/",
    "logs/",
    "trades/",
    "backtests/data/",
    "secrets/",
    "venv/",
    ".venv/",
    "node_modules/",
    ".git/",
    "hermes/",  # owned by sync-hermes-state.sh
)

DENY_NAMES = {
    ".env",
    "auth.json",
    "sentiment_cache.json",
    "sentiment_cron.log",
}

DENY_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".db",
    ".db-wal",
    ".db-shm",
    ".log",
    ".pyc",
    ".pyo",
    ".pid",
)

# Extra path regex denies
# Note: do NOT match .env.example (template is allowlisted).
DENY_RE = re.compile(
    r"(^|/)\.env$|"
    r"(^|/)\.env\.(?!example(?:$|\.))[A-Za-z0-9_.-]+$|"
    r"(^|/)__pycache__(/|$)|"
    r"(^|/)\.pytest_cache(/|$)|"
    r"\.bak($|\.)|"
    r"phase6_runner_state|"
    r"capital_external_flows|"
    r"preserve_sleeve|"
    r"shadow_tp_events|"
    r"rsi_indicator_history",
    re.I,
)

# Prefer source-like extensions under allow dirs (still allow Makefile etc.)
PREFER_EXT = {
    ".py", ".sh", ".bash", ".md", ".rst", ".txt", ".toml", ".yaml", ".yml",
    ".json", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".sql", ".service",
    ".example", ".cfg", ".ini", ".csv",  # small configs only; size gate applies
}

def denied(rel: str) -> str | None:
    if rel in DENY_NAMES or Path(rel).name in DENY_NAMES:
        return "deny-name"
    for p in DENY_PREFIXES:
        if rel == p.rstrip("/") or rel.startswith(p):
            return f"deny-prefix:{p}"
    low = rel.lower()
    for s in DENY_SUFFIXES:
        if low.endswith(s):
            return f"deny-suffix:{s}"
    if DENY_RE.search(rel):
        return "deny-re"
    return None

def allowed(rel: str) -> bool:
    if rel in ALLOW_ROOT_FILES:
        return True
    for d in ALLOW_DIRS:
        if rel.startswith(d):
            return True
    return False

out = subprocess.check_output(["git", "status", "--porcelain", "-u"], text=True)
selected = []
skipped = []
for line in out.splitlines():
    if not line.strip():
        continue
    # porcelain v1: XY SPACE path  OR  XY SPACE old -> new
    path = line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    path = path.strip().strip('"')
    if not path:
        continue
    why = denied(path)
    if why:
        skipped.append((path, why))
        continue
    if not allowed(path):
        skipped.append((path, "not-allowlisted"))
        continue
    p = root / path
    if p.is_file():
        try:
            sz = p.stat().st_size
        except OSError:
            skipped.append((path, "stat-fail"))
            continue
        if sz > max_bytes:
            skipped.append((path, f"too-large:{sz}"))
            continue
        # Under allow dirs, skip obvious non-source binaries without extension gate
        name = p.name
        ext = p.suffix.lower()
        # Dockerfiles / Compose often use dotted suffixes (Dockerfile.gateway)
        if name == "Dockerfile" or name.startswith("Dockerfile.") or name in {
            "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
        }:
            pass
        elif path not in ALLOW_ROOT_FILES and ext and ext not in PREFER_EXT:
            if ext not in {"", ".md"}:
                skipped.append((path, f"ext:{ext}"))
                continue
    selected.append(path)

# Print skips summary to stderr via markers
print(f"# selected={len(selected)} skipped={len(skipped)}", file=sys.stderr)
by = {}
for _, w in skipped:
    by[w] = by.get(w, 0) + 1
for w, n in sorted(by.items(), key=lambda x: -x[1])[:20]:
    print(f"# skip {n:4d}  {w}", file=sys.stderr)
for path in selected:
    print(path)
PY
)

echo "Candidates: ${#CANDIDATES[@]}"
if [[ "${#CANDIDATES[@]}" -eq 0 ]]; then
  echo "Nothing safe to stage. Done."
  exit 0
fi

# Show sample
echo "--- sample candidates (first 40) ---"
printf '%s\n' "${CANDIDATES[@]:0:40}"
if [[ "${#CANDIDATES[@]}" -gt 40 ]]; then
  echo "... +$(( ${#CANDIDATES[@]} - 40 )) more"
fi

if [[ "$DRY" == true ]]; then
  echo "=== DRY RUN: would stage ${#CANDIDATES[@]} paths (no commit) ==="
  exit 0
fi

# Reset any prior partial stage for this job, then add explicitly
git reset HEAD -- . >/dev/null 2>&1 || true

# Stage in batches to avoid arg max
BATCH=80
for ((i=0; i<${#CANDIDATES[@]}; i+=BATCH)); do
  chunk=("${CANDIDATES[@]:i:BATCH}")
  git add -A -- "${chunk[@]}"
done

# Secret scan on staged diff (text)
echo "--- secret scan (staged) ---"
SCAN_RC=0
python3 - <<'PY' || SCAN_RC=$?
import re, subprocess, sys
diff = subprocess.check_output(["git", "diff", "--cached", "--no-color", "-U0"], text=True, errors="replace")
# Only added lines
added = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
patterns = [
    (r"(?i)(api[_-]?key|secret[_-]?key|private[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{12,}", "credential assignment"),
    (r"\bsk-[A-Za-z0-9_-]{20,}\b", "sk- token"),
    (r"\bghp_[A-Za-z0-9]{20,}\b", "github pat"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "slack token"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key block"),
    (r"(?i)coinbase.*(?:api|secret).{0,40}['\"][A-Za-z0-9+/=_-]{20,}['\"]", "exchange-ish secret"),
]
hits = []
for pat, label in patterns:
    for m in re.finditer(pat, added):
        snippet = m.group(0)[:80].replace("\n", " ")
        hits.append(f"{label}: {snippet}...")
if hits:
    print("SECRET SCAN FAILED — refusing commit:")
    for h in hits[:20]:
        print(" ", h)
    sys.exit(2)
print("Secret scan: clean")
sys.exit(0)
PY

if [[ "$SCAN_RC" -ne 0 ]]; then
  echo "ERROR: secret scan failed; unstaging."
  git reset HEAD -- . >/dev/null 2>&1 || true
  exit 2
fi

if git diff --cached --quiet; then
  echo "Nothing staged after filters."
  exit 0
fi

STAGED_N=$(git diff --cached --name-only | wc -l | tr -d ' ')
echo "Staged files: $STAGED_N"

git commit -m "$(cat <<EOF
chore(git): safe code backup ${TIMESTAMP}

Allowlisted source/docs/config only (no data/state, logs, trades, secrets).
Daily job: scripts/hermes/git/commit-safe-code.sh
Staged paths: ${STAGED_N}
EOF
)"

echo "Committed: $(git log -1 --oneline)"

if [[ "$NO_PUSH" == true ]]; then
  echo "Skipping push (--no-push)."
  exit 0
fi

if git remote | grep -qx origin; then
  echo "--- Pushing to origin ---"
  # Never force-push from cron
  if git push origin HEAD; then
    echo "Push OK."
  else
    echo "ERROR: push failed" >&2
    exit 1
  fi
else
  echo "WARN: no origin remote; commit is local only"
fi

echo "=== Safe code commit complete ==="
git status -sb | head -5
