# VPS Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the tiktok-faceless autonomous agent pipeline and Streamlit dashboard to a Hetzner CX22 VPS, running as systemd services with PostgreSQL, with crash-safe state persistence.

**Architecture:** The pipeline (`main.py`) runs on a cron/loop schedule as a systemd service, persisting LangGraph checkpoint state to SQLite (replacing MemorySaver). The Streamlit dashboard runs as a second systemd service behind a Caddy reverse proxy with HTTPS. PostgreSQL (or SQLite for single-account) stores all DB records. Environment variables live in a `.env` file owned by a dedicated `tiktok` system user.

**Tech Stack:** Python 3.12, uv, PostgreSQL 16 (or SQLite prod), Alembic, LangGraph SqliteSaver, Streamlit, Caddy, systemd, Hetzner CX22 (Ubuntu 24.04 LTS)

---

## Pre-Flight Checklist (do these manually before running any tasks)

- [ ] Hetzner CX22 VPS provisioned (Ubuntu 24.04 LTS, 2 vCPU, 4GB RAM, 40GB SSD)
- [ ] SSH key added; can `ssh root@<VPS_IP>`
- [ ] Domain or subdomain pointing at VPS IP (for HTTPS dashboard) — or note VPS IP for HTTP-only
- [ ] All API credentials on hand:
  - `TIKTOK_ACCESS_TOKEN`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_OPEN_ID`
  - `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`
  - `ANTHROPIC_API_KEY`
  - `CREATOMATE_API_KEY`, `CREATOMATE_TEMPLATE_ID` (optional)
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional, for alerts)
  - `DASHBOARD_PASSWORD` (choose one)

---

## Task 1: Fix MemorySaver → SqliteSaver (local, before deploy)

**Files:**
- Modify: `tiktok_faceless/graph.py`
- Modify: `pyproject.toml` (add dependency)
- Test: `tests/unit/test_graph.py`

**Why:** `MemorySaver` loses all pipeline checkpoint state on process restart. On a VPS, a crash or deploy means the pipeline starts from scratch on every run. `SqliteSaver` writes checkpoints to a `.db` file that survives restarts.

**Step 1: Install the checkpoint package**

```bash
uv add langgraph-checkpoint-sqlite
```

Expected: Package added to `pyproject.toml` dependencies.

**Step 2: Update `tiktok_faceless/graph.py`**

Replace:
```python
from langgraph.checkpoint.memory import MemorySaver
```
With:
```python
import os
from langgraph.checkpoint.sqlite import SqliteSaver
```

Replace in `build_graph()`:
```python
return graph.compile(checkpointer=MemorySaver())
```
With:
```python
checkpoint_db = os.environ.get("CHECKPOINT_DB_PATH", "./checkpoints.db")
checkpointer = SqliteSaver.from_conn_string(checkpoint_db)
return graph.compile(checkpointer=checkpointer)
```

**Step 3: Run existing graph tests**

```bash
uv run pytest tests/unit/test_graph.py -v
```

Expected: All pass. If `SqliteSaver` API differs from `MemorySaver`, tests will show the diff — fix the mock accordingly.

**Step 4: Run full test suite**

```bash
uv run pytest tests/unit/ -q
```

Expected: 456 passed, 0 failed.

**Step 5: Commit**

```bash
git add tiktok_faceless/graph.py pyproject.toml uv.lock
git commit -m "feat: replace MemorySaver with SqliteSaver for crash-safe checkpointing"
```

---

## Task 2: Add `load_env()` call and logging setup to `main.py`

**Files:**
- Modify: `tiktok_faceless/main.py`

**Why:** `load_env()` (which calls `dotenv.load_dotenv()`) must be called at process startup before any `os.environ` reads. Currently `main.py` imports `load_account_config` but never calls `load_env()`. On the VPS the `.env` file provides all credentials — without this call, they won't be loaded.

Also add structured logging so systemd captures useful output via `journalctl`.

**Step 1: Update `main.py`**

Add at top of imports:
```python
import logging.config
```

Add after existing imports:
```python
from tiktok_faceless.config import load_account_config, load_env
```
(replace the existing `load_account_config` import line)

Add a logging setup function:
```python
def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
```

Update `main()` to call both at the very start:
```python
def main() -> None:
    _setup_logging()
    load_env()
    args = parse_args()
    # ... rest unchanged
```

**Step 2: Run tests to confirm no regressions**

```bash
uv run pytest tests/unit/test_main_multi_account.py tests/unit/test_main_provision.py tests/unit/test_main_resume.py -v
```

Expected: All pass.

**Step 3: Commit**

```bash
git add tiktok_faceless/main.py
git commit -m "feat: add load_env() and structured logging setup to main entry point"
```

---

## Task 3: Create `.env.example` and `deploy/` folder

**Files:**
- Create: `.env.example`
- Create: `deploy/pipeline.service` (systemd unit)
- Create: `deploy/dashboard.service` (systemd unit)
- Create: `deploy/Caddyfile` (reverse proxy)
- Create: `deploy/setup.sh` (VPS bootstrap script)

**Why:** The operator needs to know exactly which env vars to set and what systemd units to install. These files are the single source of truth for deployment configuration.

**Step 1: Create `.env.example`**

```bash
cat > .env.example << 'EOF'
# TikTok credentials
TIKTOK_ACCESS_TOKEN=your_access_token_here
TIKTOK_CLIENT_KEY=your_client_key_here
TIKTOK_CLIENT_SECRET=your_client_secret_here
TIKTOK_OPEN_ID=your_open_id_here

# ElevenLabs TTS
ELEVENLABS_API_KEY=your_elevenlabs_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here

# Anthropic (script generation)
ANTHROPIC_API_KEY=your_anthropic_key_here

# Creatomate (video assembly) — optional
CREATOMATE_API_KEY=
CREATOMATE_TEMPLATE_ID=

# Telegram alerts — optional
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Database
DATABASE_URL=sqlite:////home/tiktok/tiktok-faceless/tiktok_faceless.db

# LangGraph checkpoint state
CHECKPOINT_DB_PATH=/home/tiktok/tiktok-faceless/checkpoints.db

# Dashboard auth
DASHBOARD_PASSWORD=choose_a_strong_password

# LangSmith tracing — optional
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=tiktok-faceless
EOF
```

**Step 2: Create `deploy/pipeline.service`**

```ini
[Unit]
Description=TikTok Faceless Pipeline
After=network.target
Wants=network.target

[Service]
Type=oneshot
User=tiktok
Group=tiktok
WorkingDirectory=/home/tiktok/tiktok-faceless
EnvironmentFile=/home/tiktok/tiktok-faceless/.env
ExecStart=/home/tiktok/tiktok-faceless/.venv/bin/python -m tiktok_faceless.main
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tiktok-pipeline

[Install]
WantedBy=multi-user.target
```

**Step 3: Create `deploy/pipeline.timer`** (runs every 30 minutes)

```ini
[Unit]
Description=Run TikTok Faceless Pipeline every 30 minutes
Requires=tiktok-pipeline.service

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Unit=tiktok-pipeline.service

[Install]
WantedBy=timers.target
```

**Step 4: Create `deploy/dashboard.service`**

```ini
[Unit]
Description=TikTok Faceless Dashboard
After=network.target

[Service]
Type=simple
User=tiktok
Group=tiktok
WorkingDirectory=/home/tiktok/tiktok-faceless
EnvironmentFile=/home/tiktok/tiktok-faceless/.env
ExecStart=/home/tiktok/tiktok-faceless/.venv/bin/streamlit run dashboard/app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tiktok-dashboard

[Install]
WantedBy=multi-user.target
```

**Step 5: Create `deploy/Caddyfile`** (replace `dashboard.yourdomain.com` with actual domain)

```
dashboard.yourdomain.com {
    reverse_proxy 127.0.0.1:8501
    encode gzip
}
```

**Step 6: Create `deploy/setup.sh`** (run once as root on fresh VPS)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== tiktok-faceless VPS setup ==="

# System packages
apt-get update -qq
apt-get install -y -qq git python3.12 python3.12-venv curl sqlite3

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# Install Caddy
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq && apt-get install -y -qq caddy

# Create system user
useradd --system --create-home --shell /bin/bash tiktok || true

# Clone repo
sudo -u tiktok git clone https://github.com/YOUR_USERNAME/tiktok-faceless.git /home/tiktok/tiktok-faceless

# Create venv and install
sudo -u tiktok bash -c "cd /home/tiktok/tiktok-faceless && uv sync --no-dev"

echo ""
echo "=== Next steps ==="
echo "1. Copy .env.example to .env and fill in credentials:"
echo "   cp /home/tiktok/tiktok-faceless/.env.example /home/tiktok/tiktok-faceless/.env"
echo "   nano /home/tiktok/tiktok-faceless/.env"
echo ""
echo "2. Run DB migrations:"
echo "   sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && source .env && uv run alembic upgrade head'"
echo ""
echo "3. Provision your first account:"
echo "   sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && source .env && uv run python -m tiktok_faceless.main --provision-account acc1'"
echo ""
echo "4. Install systemd units:"
echo "   cp deploy/pipeline.service /etc/systemd/system/tiktok-pipeline.service"
echo "   cp deploy/pipeline.timer /etc/systemd/system/tiktok-pipeline.timer"
echo "   cp deploy/dashboard.service /etc/systemd/system/tiktok-dashboard.service"
echo "   systemctl daemon-reload"
echo "   systemctl enable --now tiktok-pipeline.timer"
echo "   systemctl enable --now tiktok-dashboard"
echo ""
echo "5. Configure Caddy (update domain in deploy/Caddyfile first):"
echo "   cp deploy/Caddyfile /etc/caddy/Caddyfile"
echo "   systemctl reload caddy"
```

**Step 7: Make setup.sh executable and commit**

```bash
chmod +x deploy/setup.sh
git add .env.example deploy/
git commit -m "feat: add systemd units, Caddyfile, and VPS bootstrap script"
```

---

## Task 4: Add Alembic migration for `paused_agent_queues` column

**Files:**
- Create: `tiktok_faceless/db/migrations/versions/<hash>_add_paused_agent_queues.py`

**Why:** The `Account` model has a `paused_agent_queues` field but it may not exist in the DB schema yet depending on when the initial migration was created. Running `alembic upgrade head` on a fresh VPS DB will fail if this column was added to the model but not to any migration.

**Step 1: Check current model vs migration state (local)**

```bash
DATABASE_URL=sqlite:///./deploy_check.db uv run alembic upgrade head
DATABASE_URL=sqlite:///./deploy_check.db uv run python -c "
from tiktok_faceless.db.session import get_engine
from sqlalchemy import inspect
engine = get_engine('sqlite:///./deploy_check.db')
cols = [c['name'] for c in inspect(engine).get_columns('accounts')]
print(cols)
"
rm -f deploy_check.db
```

Expected output includes `paused_agent_queues`. If it does — Task 4 is done, skip to Task 5.
If it's missing — continue to Step 2.

**Step 2: Generate migration**

```bash
DATABASE_URL=sqlite:///./migration_check.db uv run alembic revision --autogenerate -m "add_paused_agent_queues_to_accounts"
rm -f migration_check.db
```

Review the generated file in `tiktok_faceless/db/migrations/versions/`. Confirm it adds a nullable `paused_agent_queues` column to `accounts`.

**Step 3: Test migration round-trip**

```bash
DATABASE_URL=sqlite:///./test_migrate.db uv run alembic upgrade head
DATABASE_URL=sqlite:///./test_migrate.db uv run alembic downgrade -1
DATABASE_URL=sqlite:///./test_migrate.db uv run alembic upgrade head
rm -f test_migrate.db
```

Expected: All three commands succeed without error.

**Step 4: Commit**

```bash
git add tiktok_faceless/db/migrations/versions/
git commit -m "feat: add alembic migration for paused_agent_queues column"
```

---

## Task 5: Push to GitHub (or equivalent remote)

**Why:** The VPS setup script clones from GitHub. The repo needs to be pushed before `setup.sh` can run.

**Step 1: Create GitHub repo (if not exists)**

```bash
gh repo create tiktok-faceless --private --source=. --remote=origin --push
```

Or if repo already exists:

```bash
git remote -v  # confirm remote is set
git push origin main
```

**Step 2: Confirm push**

```bash
git log origin/main --oneline -5
```

Expected: Shows the last 5 commits including the deployment files.

---

## Task 6: VPS Initial Setup (run manually on the server)

**SSH into the VPS and run these commands directly.**

**Step 1: SSH in as root**

```bash
ssh root@<VPS_IP>
```

**Step 2: Run bootstrap script**

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/tiktok-faceless/main/deploy/setup.sh | bash
```

Or copy it manually:
```bash
scp deploy/setup.sh root@<VPS_IP>:/tmp/setup.sh
ssh root@<VPS_IP> bash /tmp/setup.sh
```

**Step 3: Fill in credentials**

```bash
cp /home/tiktok/tiktok-faceless/.env.example /home/tiktok/tiktok-faceless/.env
nano /home/tiktok/tiktok-faceless/.env
# Fill in every non-optional credential
chown tiktok:tiktok /home/tiktok/tiktok-faceless/.env
chmod 600 /home/tiktok/tiktok-faceless/.env
```

**Step 4: Run DB migrations**

```bash
sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && set -a && source .env && set +a && uv run alembic upgrade head'
```

Expected: `Running upgrade -> 4c34fe0b3891, initial schema` ... `Running upgrade ... -> head`

**Step 5: Provision the first account**

```bash
sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && set -a && source .env && set +a && uv run python -m tiktok_faceless.main --provision-account acc1'
```

Expected: `INFO tiktok_faceless.main Provisioned account acc1`

**Step 6: Run a single pipeline cycle to smoke test**

```bash
sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && set -a && source .env && set +a && uv run python -m tiktok_faceless.main'
```

Watch the logs. Expected: Pipeline runs through all 5 nodes without unhandled exceptions. TikTok API calls will fail if the access token is expired — that's expected if you haven't re-authed recently.

---

## Task 7: Install and start systemd services

**Run on VPS as root.**

**Step 1: Install service files**

```bash
cp /home/tiktok/tiktok-faceless/deploy/pipeline.service /etc/systemd/system/tiktok-pipeline.service
cp /home/tiktok/tiktok-faceless/deploy/pipeline.timer /etc/systemd/system/tiktok-pipeline.timer
cp /home/tiktok/tiktok-faceless/deploy/dashboard.service /etc/systemd/system/tiktok-dashboard.service
systemctl daemon-reload
```

**Step 2: Enable and start dashboard**

```bash
systemctl enable --now tiktok-dashboard
systemctl status tiktok-dashboard
```

Expected: `Active: active (running)`

**Step 3: Enable and start pipeline timer**

```bash
systemctl enable --now tiktok-pipeline.timer
systemctl list-timers tiktok-pipeline.timer
```

Expected: Shows next trigger time ~30 minutes from now.

**Step 4: Trigger a manual pipeline run to confirm it works under systemd**

```bash
systemctl start tiktok-pipeline
journalctl -u tiktok-pipeline -n 50 --no-pager
```

Expected: Log output showing pipeline execution across all nodes.

---

## Task 8: Configure Caddy HTTPS reverse proxy

**Run on VPS as root.**

**Step 1: Update Caddyfile with your actual domain**

```bash
nano /home/tiktok/tiktok-faceless/deploy/Caddyfile
# Replace dashboard.yourdomain.com with your actual subdomain
```

**Step 2: Install Caddyfile**

```bash
cp /home/tiktok/tiktok-faceless/deploy/Caddyfile /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

**Step 3: Verify HTTPS**

Open `https://dashboard.yourdomain.com` in a browser.
Expected: Streamlit dashboard loads, prompts for password.

Enter the `DASHBOARD_PASSWORD` from `.env`.
Expected: Dashboard shows account summary table, KPI strip, agent health.

---

## Task 9: Smoke test the full stack

**Do these checks from your laptop, not the VPS.**

**Step 1: Dashboard loads and authenticates**

- Open `https://dashboard.yourdomain.com`
- Enter password → dashboard renders
- Account `acc1` appears in sidebar selector
- KPI strip shows — (no data yet), which is correct for a fresh account

**Step 2: Pipeline ran and left a checkpoint**

```bash
ssh tiktok@<VPS_IP> ls -lh /home/tiktok/tiktok-faceless/checkpoints.db
```

Expected: File exists and is non-zero bytes.

**Step 3: DB has the account row**

```bash
ssh tiktok@<VPS_IP> sqlite3 /home/tiktok/tiktok-faceless/tiktok_faceless.db "SELECT account_id, phase FROM accounts;"
```

Expected: `acc1|warmup`

**Step 4: Check pipeline timer is healthy**

```bash
ssh root@<VPS_IP> systemctl status tiktok-pipeline.timer
```

Expected: `Active: active (waiting)` with a next trigger shown.

**Step 5: Check dashboard service is healthy**

```bash
ssh root@<VPS_IP> systemctl status tiktok-dashboard
```

Expected: `Active: active (running)`

---

## Task 10: Set up log rotation and monitoring

**Run on VPS as root.**

**Step 1: Configure journald retention**

```bash
mkdir -p /etc/systemd/journald.conf.d/
cat > /etc/systemd/journald.conf.d/tiktok.conf << 'EOF'
[Journal]
SystemMaxUse=500M
MaxRetentionSec=30day
EOF
systemctl restart systemd-journald
```

**Step 2: Create a simple health-check alias**

```bash
cat > /usr/local/bin/tiktok-status << 'EOF'
#!/bin/bash
echo "=== Pipeline Timer ==="
systemctl status tiktok-pipeline.timer --no-pager -l
echo ""
echo "=== Dashboard ==="
systemctl status tiktok-dashboard --no-pager -l
echo ""
echo "=== Last Pipeline Run ==="
journalctl -u tiktok-pipeline -n 20 --no-pager
EOF
chmod +x /usr/local/bin/tiktok-status
```

Run anytime with: `tiktok-status`

**Step 3: Confirm disk usage is reasonable**

```bash
df -h /
du -sh /home/tiktok/tiktok-faceless/
```

Expected: Plenty of headroom on a 40GB disk at this stage.

---

## Post-Deploy Operations Reference

### Update the code on VPS

```bash
ssh tiktok@<VPS_IP>
cd /home/tiktok/tiktok-faceless
git pull origin main
uv sync --no-dev
sudo systemctl restart tiktok-dashboard
# Pipeline picks up new code on next timer trigger automatically
```

### Run Alembic migration after a schema change

```bash
sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && set -a && source .env && set +a && uv run alembic upgrade head'
```

### Manually resume a paused agent

```bash
sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && set -a && source .env && set +a && uv run python -m tiktok_faceless.main --resume-agent research --account-id acc1'
```

### Provision a second account

```bash
# Add acc2 credentials to .env first, then:
sudo -u tiktok bash -c 'cd /home/tiktok/tiktok-faceless && set -a && source .env && set +a && uv run python -m tiktok_faceless.main --provision-account acc2'
```

### View live pipeline logs

```bash
journalctl -u tiktok-pipeline -f
```

### View live dashboard logs

```bash
journalctl -u tiktok-dashboard -f
```
