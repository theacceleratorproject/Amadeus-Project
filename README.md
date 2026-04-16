# Amadeus Project

A multi-agent orchestrator that routes coding tasks to the right AI tool and pipes results into a shared workspace.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  amadeus CLI                     │
│         (orchestrator/amadeus.sh)                │
├────────────────────┬────────────────────────────┤
│                    │                            │
│  architecture      │   boilerplate              │
│  debug             │   snippet                  │
│        ↓           │          ↓                 │
│   Claude Code      │      Codex CLI             │
│  (reasoning)       │    (generation)            │
│        ↓           │          ↓                 │
├────────────────────┴────────────────────────────┤
│              workspace/ (shared output)          │
│  architecture/  debug/  boilerplate/  snippets/  │
└─────────────────────────────────────────────────┘
```

## Routing Logic

| Task Type      | Agent       | Use Case                                  |
|----------------|-------------|-------------------------------------------|
| `architecture` | Claude Code | System design, API design, data modeling  |
| `debug`        | Claude Code | Bug investigation, error tracing, fixes   |
| `boilerplate`  | Codex CLI   | Scaffolding, templates, repetitive code   |
| `snippet`      | Codex CLI   | Small utility functions, one-off code     |

## Setup

```bash
# Add to your PATH (add to ~/.zshrc for persistence)
export PATH="$PATH:$HOME/Desktop/Amadeus Project/orchestrator"

# Or create a symlink
ln -s "$HOME/Desktop/Amadeus Project/orchestrator/amadeus.sh" /usr/local/bin/amadeus
```

## Usage

```bash
# Architecture task → Claude Code
amadeus architecture "Design a REST API for user authentication"

# Debug task → Claude Code
amadeus debug "Fix the null pointer in src/auth/login.ts"

# Boilerplate task → Codex CLI
amadeus boilerplate "Create a CRUD controller for the User model"

# Snippet task → Codex CLI
amadeus snippet "Write a debounce utility function in TypeScript"

# Custom output file
amadeus snippet "JWT helper" -o snippets/jwt_helper.ts

# Quiet mode (no status messages, just output)
amadeus debug "trace the memory leak" -q
```

## Directory Structure

```
Amadeus Project/
├── orchestrator/
│   └── amadeus.sh          # The orchestrator CLI
├── workspace/               # Shared output from all agents
│   ├── architecture/        # System design outputs
│   ├── debug/               # Debug investigation outputs
│   ├── boilerplate/         # Generated scaffolding
│   └── snippets/            # Generated code snippets
├── logs/                    # Execution logs
└── README.md
```

## Logs

Every run produces a timestamped log in `logs/`. Logs capture routing decisions, agent output, and errors for traceability.
