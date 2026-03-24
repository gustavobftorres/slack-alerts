# Balancer Slack Warnings

This repository runs two automated checks and posts alerts to Slack:

- **Pool alerts**: monitors selected Balancer pools for TVL drops/spikes and newly paused pools.
- **Touchpoint alerts**: posts daily touchpoint reminders grouped by attendee.

Both checks are designed to run in GitHub Actions on a schedule, but you can also run them locally.

## Installation and Local Configuration

### Prerequisites

- Python `3.12` (same as GitHub Actions)
- `pip`
- Access to:
  - Slack incoming webhook
  - Notion integration token
  - Relevant Notion database IDs

### 1) Clone and enter the repository

```bash
git clone <your-repo-url>
cd slack-warnings
```

### 2) Create and activate a virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Create a local `.env`

Create a `.env` file in the repository root:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
NOTION_API_KEY=secret_xxx
NOTION_POOLS_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_TOUCHPOINT_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BALANCER_V2_SUBGRAPH=https://api.studio.thegraph.com/query/24660/balancer-ethereum-v2/version/latest
```

Note:
- `BALANCER_V2_SUBGRAPH` is optional locally (the app has a default fallback URL).

### 5) Verify static config

Review `config.yaml`:
- `alerts`: thresholds and minimum TVL filter.
- `chains`: Balancer chains queried in API.
- `api_url`: Balancer GraphQL endpoint.
- `snapshot_path`: path of persistent comparison snapshot.

## Running Locally

### Pool alerts job

```bash
python src/main.py
```

### Touchpoint alerts job

```bash
python src/touchpoint_check.py
```

Optional Monday simulation:

```bash
python src/touchpoint_check.py --monday
```

## Environment Variables and GitHub Actions

This repo uses GitHub Actions workflows:

- `.github/workflows/daily-check.yml`
- `.github/workflows/touchpoint-check.yml`

Both workflows pass runtime configuration using `env` from GitHub **Secrets**.

### Required GitHub Secrets

Set these in **Repository Settings -> Secrets and variables -> Actions -> Secrets**:

- `SLACK_WEBHOOK_URL`
- `NOTION_API_KEY`
- `NOTION_POOLS_DB_ID` (used by daily pool check)
- `NOTION_TOUCHPOINT_DB_ID` (used by touchpoint check)

Optional:
- `BALANCER_V2_SUBGRAPH` (used by daily pool check fallback for missing v2 pools)

## Repository Structure

```text
.
├── .github/workflows/
│   ├── daily-check.yml          # Scheduled pool monitoring workflow
│   └── touchpoint-check.yml     # Scheduled touchpoint workflow
├── config.yaml                  # Alert thresholds + chain/API config
├── data/
│   └── snapshot.json            # Last pool snapshot used for diffing
├── src/
│   ├── main.py                  # Entry point: pool monitoring flow
│   ├── alerts.py                # Alert detection rules
│   ├── balancer_api.py          # Balancer API + v2 subgraph fetchers
│   ├── notion_pools.py          # Notion pools DB parser/query
│   ├── slack_notifier.py        # Pool alert Slack formatter/sender
│   ├── touchpoint_check.py      # Entry point: touchpoint flow
│   ├── touchpoint_alerts.py     # Touchpoint filtering rules
│   ├── notion_client.py         # Notion touchpoint DB client
│   └── touchpoint_notifier.py   # Touchpoint Slack formatter/sender
└── requirements.txt             # Python dependencies
```

## Testing and Validation

There is currently **no automated test suite** (no `pytest` tests yet). For now, use this validation workflow:

### 1) Run both flows manually

```bash
python src/main.py
python src/touchpoint_check.py --monday
```

## Common First-Time Issues

- **`SLACK_WEBHOOK_URL environment variable is not set`**  
  Missing `.env` locally or missing GitHub secret in Actions.

- **Notion API 401/403**  
  Invalid `NOTION_API_KEY` or integration is not shared with the target database.

- **No pools/touchpoints returned**  
  Wrong DB ID, unexpected Notion property schema, or filters exclude everything.

- **No alerts sent**  
  Expected when nothing matches thresholds/criteria. Check logs and thresholds in `config.yaml`.
