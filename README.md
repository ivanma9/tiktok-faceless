# tiktok-faceless

Autonomous TikTok affiliate content system — researches trending products, scripts and produces short-form video, publishes, analyzes performance, and manages affiliate revenue with zero human intervention.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — the only package manager used in this project

## Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repo
git clone https://github.com/your-org/tiktok-faceless.git
cd tiktok-faceless

# Install all dependencies
uv sync --extra dev

# Copy env template and fill in credentials
cp .env.example .env
```

## Running

```bash
# Run the pipeline
uv run python -m tiktok_faceless.main

# Run the dashboard (separate terminal)
uv run streamlit run dashboard/app.py
```

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy tiktok_faceless/

# Format
uv run ruff format .
```

## Deployment (VPS via systemd)

1. Copy repo to `/home/ubuntu/tiktok-faceless` on the Hetzner CX22 VPS
2. Create `/etc/tiktok-faceless.env` with all env vars from `.env.example`
3. Copy and enable the systemd service:

```bash
sudo cp systemd/tiktok-faceless.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tiktok-faceless
sudo systemctl start tiktok-faceless
```

4. Check status:

```bash
sudo systemctl status tiktok-faceless
journalctl -u tiktok-faceless -f
```

## Project Structure

```
tiktok_faceless/        # Main package
├── agents/             # 7 agent modules (orchestrator, research, script, ...)
├── clients/            # Typed API wrappers (TikTok, ElevenLabs, Creatomate, ...)
├── db/                 # SQLAlchemy models, session, queries, Alembic migrations
├── models/             # Pydantic response/request models (not DB models)
├── utils/              # Shared utilities (retry, timing, suppression, alerts, video)
├── state.py            # PipelineState, AgentError, VideoLifecycle
├── config.py           # AccountConfig + env var loading
├── graph.py            # LangGraph graph assembly
└── main.py             # Entry point

dashboard/              # Streamlit monitoring dashboard
tests/                  # pytest test suite
systemd/                # systemd unit file for VPS deployment
```
