# LLM Dashboard

A local web dashboard for managing LLM tooling: plugins, models, a small
summarising agent and provider settings. It binds to `127.0.0.1` only.

## Run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

LLM_DASH_MOCK=1 python -m llm_dashboard     # mock LLM + mock model CLI
python -m llm_dashboard                      # real providers / real CLI
```

Open http://127.0.0.1:8000.

## Configuration (environment)

| Variable             | Default             | Purpose                                         |
| -------------------- | ------------------- | ----------------------------------------------- |
| `LLM_DASH_MOCK`      | off                 | Mock the agent's LLM calls and the model CLI    |
| `LLM_DASH_DATA_DIR`  | `~/.llm-dashboard`  | Settings, plugins, mock state (must be outside the workspace) |
| `LLM_DASH_WORKSPACE` | `./workspace`       | The only folder the agent can read from         |
| `LLM_DASH_MODEL_CLI` | `ollama`            | Model CLI used for `pull` / `list`              |
| `LLM_DASH_PORT`      | `8000`              | Port on 127.0.0.1                               |

## API

| Method | Path                      | Purpose                              |
| ------ | ------------------------- | ------------------------------------ |
| GET    | `/api/health`             | Liveness and mock-mode flag          |
| GET    | `/api/plugins`            | List installed plugins               |
| POST   | `/api/plugins`            | Install `{name, version?}`           |
| GET    | `/api/models`             | List local models                    |
| POST   | `/api/models/pull`        | Pull `{name}`                        |
| GET    | `/api/settings`           | Read settings (API key never returned) |
| PUT    | `/api/settings`           | Partial update                       |
| POST   | `/api/agent/summarize`    | Summarise `{target}` (URL or workspace file) |
| GET    | `/api/agent/workspace`    | List workspace files                 |

## Tests

```bash
pytest
```

## Security notes

- The agent's `read_file` tool is confined to the workspace (symlinks resolved).
- The agent's `fetch_page` tool refuses non-public addresses, re-checking each redirect.
- Plugin and model names are validated against strict patterns and passed as
  argv items, never through a shell.
- Installing a plugin runs that package's install-time code. Only install packages you trust.
