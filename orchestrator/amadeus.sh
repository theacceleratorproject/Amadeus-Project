#!/usr/bin/env bash
#
# amadeus — multi-agent task orchestrator
# Routes tasks to Claude Code or Codex CLI based on task type,
# pipes results into the shared workspace.

set -euo pipefail

SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$0")"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
WORKSPACE="$PROJECT_ROOT/workspace"
LOGS="$PROJECT_ROOT/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# ── Colors ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

usage() {
  cat <<EOF
${BOLD}amadeus${NC} — multi-agent task orchestrator

${BOLD}USAGE${NC}
  amadeus <task-type> <prompt> [options]

${BOLD}CHAINING${NC}
  amadeus architecture "Design API" | amadeus snippet "Generate endpoints from this"

  When piped, the upstream output is appended to the prompt as context.

${BOLD}TASK TYPES${NC}
  ${CYAN}architecture${NC}  → Claude Code  │ System design, API design, data modeling
  ${CYAN}debug${NC}         → Claude Code  │ Bug investigation, error tracing, fixes
  ${CYAN}boilerplate${NC}   → Codex CLI    │ Scaffolding, templates, repetitive code
  ${CYAN}snippet${NC}       → Codex CLI    │ Small utility functions, one-off code

${BOLD}OPTIONS${NC}
  -o, --output <file>   Write output to a specific file (relative to workspace)
  -q, --quiet           Suppress status messages
  -h, --help            Show this help

${BOLD}EXAMPLES${NC}
  amadeus architecture "Design a REST API for user authentication"
  amadeus debug "Fix the null pointer in src/auth/login.ts"
  amadeus boilerplate "Create a CRUD controller for the User model"
  amadeus snippet "Write a debounce utility function in TypeScript"
  amadeus architecture "Design auth" | amadeus snippet "Generate FastAPI from this"

EOF
  exit 0
}

log() {
  local level="$1"; shift
  local msg="$*"
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [$level] $msg" >> "$LOGS/amadeus_${TIMESTAMP}.log"
  if [[ "$QUIET" != "true" ]]; then
    case "$level" in
      INFO)  echo -e "${GREEN}[INFO]${NC}  $msg" >&2 ;;
      ROUTE) echo -e "${CYAN}[ROUTE]${NC} $msg" >&2 ;;
      DONE)  echo -e "${GREEN}[DONE]${NC}  $msg" >&2 ;;
      ERROR) echo -e "${RED}[ERROR]${NC} $msg" >&2 ;;
    esac
  fi
}

route_task() {
  local task_type="$1"
  case "$task_type" in
    architecture|debug)
      echo "claude"
      ;;
    boilerplate|snippet)
      echo "codex"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

output_dir() {
  local task_type="$1"
  case "$task_type" in
    architecture) echo "$WORKSPACE/architecture" ;;
    debug)        echo "$WORKSPACE/debug" ;;
    boilerplate)  echo "$WORKSPACE/boilerplate" ;;
    snippet)      echo "$WORKSPACE/snippets" ;;
  esac
}

run_claude() {
  local prompt="$1"
  local outfile="$2"
  log ROUTE "Sending to Claude Code (reasoning-heavy task)"
  claude -p "$prompt" --output-format text 2>>"$LOGS/amadeus_${TIMESTAMP}.log" | tee "$outfile"
}

run_codex() {
  local prompt="$1"
  local outfile="$2"
  log ROUTE "Sending to Codex CLI (generation task)"
  codex -q "$prompt" 2>>"$LOGS/amadeus_${TIMESTAMP}.log" | tee "$outfile"
}

# ── Parse args ──────────────────────────────────────────
QUIET="false"
OUTPUT_FILE=""

[[ $# -eq 0 ]] && usage

TASK_TYPE="${1:-}"
PROMPT="${2:-}"

shift 2 2>/dev/null || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) OUTPUT_FILE="$2"; shift 2 ;;
    -q|--quiet)  QUIET="true"; shift ;;
    -h|--help)   usage ;;
    *) echo -e "${RED}Unknown option: $1${NC}" >&2; usage ;;
  esac
done

if [[ -z "$TASK_TYPE" || -z "$PROMPT" ]]; then
  echo -e "${RED}Error: task-type and prompt are required${NC}" >&2
  usage
fi

# ── Read stdin if piped (chaining support) ─────────────
STDIN_CONTEXT=""
if [[ ! -t 0 ]]; then
  STDIN_CONTEXT=$(cat)
  if [[ -n "$STDIN_CONTEXT" ]]; then
    log INFO "Received piped context ($(echo "$STDIN_CONTEXT" | wc -c | tr -d ' ') bytes)"
    PROMPT="$PROMPT

--- Context from previous task ---
$STDIN_CONTEXT"
  fi
fi

# ── Route and execute ──────────────────────────────────
AGENT=$(route_task "$TASK_TYPE")
OUTDIR=$(output_dir "$TASK_TYPE")

if [[ "$AGENT" == "unknown" ]]; then
  echo -e "${RED}Unknown task type: $TASK_TYPE${NC}" >&2
  echo "Valid types: architecture, debug, boilerplate, snippet" >&2
  exit 1
fi

# Determine output file — use only the user prompt (not piped context) for the filename
if [[ -n "$OUTPUT_FILE" ]]; then
  OUTPATH="$WORKSPACE/$OUTPUT_FILE"
  mkdir -p "$(dirname "$OUTPATH")"
else
  SAFE_NAME=$(echo "${2:-$PROMPT}" | head -1 | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g' | cut -c1-50)
  OUTPATH="$OUTDIR/${TIMESTAMP}_${SAFE_NAME}.md"
fi

log INFO "Task type:  $TASK_TYPE"
log INFO "Agent:      $AGENT"
log INFO "Output:     $OUTPATH"
log INFO "Prompt:     $(echo "$PROMPT" | head -1)"
echo "" >&2

case "$AGENT" in
  claude) run_claude "$PROMPT" "$OUTPATH" ;;
  codex)  run_codex "$PROMPT" "$OUTPATH" ;;
esac

echo "" >&2
log DONE "Output saved to $OUTPATH"
