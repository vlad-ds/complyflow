# Railway Deployment Configs

This folder contains Railway service configurations for different deployment targets.

## Services

| Config | Description | Schedule |
|--------|-------------|----------|
| `alerts-cron.railway.json` | Contract deadline alerts | Daily at 9 AM UTC |
| `regwatch-ingest.railway.json` | Regulatory document ingestion | On-demand |
| `weekly-digest-cron.railway.json` | Weekly regulatory summary | Mondays at 8 AM UTC |

The main API service uses `railway.json` in the repository root.

## Usage

In Railway dashboard, set each service's "Config Path" to point to the appropriate file:
- Alerts service: `deploy/alerts-cron.railway.json`
- Regwatch ingest: `deploy/regwatch-ingest.railway.json`
- Weekly digest: `deploy/weekly-digest-cron.railway.json`
