# AI Company — Final Production-MVP

## What this includes

- One command-center chat
- CEO / Manager orchestration
- Job Hunter / opportunity analyst
- Profitability gate
- Proposal drafter
- Project Manager
- Specialist workers: Researcher, Developer, Designer, Writer
- Two-stage QA / Reviewer
- Automatic rework loop
- SQLite persistence
- Project/task/event audit log
- Cost budget tracking
- Human approval gates before external submissions or irreversible actions
- Web research through OpenAI hosted Web Search
- Pluggable job-source layer; no unauthorized Upwork botting
- API + browser dashboard

## Important boundary

This is a deployable production-MVP architecture, but it does NOT pretend to have credentials or permission to transact on a user's external accounts.
Before connecting Upwork or another marketplace, use that platform's official API/integration and keep submission/contract/payment actions behind an explicit approval gate.

## Run locally

1. Python 3.10+
2. Create a virtual environment.
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`.
5. Set `OPENAI_API_KEY`.
6. Optionally set `OPENAI_MODEL` to a model available in your OpenAI account.
7. `uvicorn app:app --reload`
8. Open `http://127.0.0.1:8000`

## Core workflow

User
  -> Manager
  -> Job Hunter / Researcher
  -> Opportunity Analyst
  -> Human Approval (external action)
  -> Project Manager
  -> Specialist
  -> Reviewer 1
  -> Reviewer 2
  -> Rework if needed
  -> Manager
  -> Human Approval for final delivery when configured

## Budget model

Agent "salary" is represented as an internal monthly budget, not a guaranteed vendor price.
Actual model/tool/API costs depend on usage and provider pricing.

## Production hardening still required before public launch

- Managed PostgreSQL instead of SQLite
- Authentication / RBAC
- Secret manager
- HTTPS / reverse proxy
- Rate limits
- Background job queue
- Object storage for artifacts
- Monitoring and alerting
- Payment provider
- Marketplace-specific official API integration
- Automated evaluation suite
