# Backend AI Engineering — FlyRank internship

Six projects covering nine assignments. Each folder is self-contained: its own
README, its own run command, its own tests.

| Folder | What it is | Assignments | State |
|---|---|---|---|
| [task-api](task-api/) | A to-do API that stores tasks three different ways — a list in memory, then a SQLite file, then PostgreSQL in a container — behind routes that never change. Plus `POST /triage`, an LLM endpoint with validation, repair and a kill switch. | BE-01, BE-02, BE-04, BE-07 | **Verified**: CRUD, Postgres, Docker and the live model |
| [polite-scraper](polite-scraper/) | Scrapes 60 books from a practice sandbox into checked JSON, slowly and with its name on every request. | BE-05 | Verified |
| [background-job](background-job/) | An API that answers in 0.4 seconds and does 8 seconds of work elsewhere, with retries and a cron job. | BE-06 | Verified |
| [pdf-report-generator](pdf-report-generator/) | 200 orders → one SQL query → an HTML page → a real 7-page PDF, served by link. | BE-08 | Verified |
| [auth-api](auth-api/) | Sign up, log in, and a guard that stands in front of the protected routes. | BE-03 | **Verified** end to end against a live project |
| [ai-decision-flow](ai-decision-flow/) | A flowchart you draw in the browser where every box is a yes/no question and the answer picks the arrow. | BE-09 | **Verified** on a real model, through Inngest |

## Run the tests

Every project has one command and no test framework to install.

```bash
cd task-api             && python test_api.py && python test_triage.py
#   and, with a Postgres to point at:
cd task-api             && DATABASE_URL="postgresql://..." python test_postgres.py
cd polite-scraper       && python src/test_parser.py
cd background-job       && python test_api.py
cd pdf-report-generator && python test_report.py
cd auth-api             && python test_auth.py
cd ai-decision-flow     && npm install && npm test
```

58 tests with no setup (counted from the test functions), plus 5 more when a
Postgres is available. All passing as of 6 Oct 2026.

## What is honestly not finished

Nothing in the briefs. Docker (BE-04) was the last open item: on 6 Oct 2026
`task-api/verify-docker.ps1` passed all 12 checkpoints on Docker Desktop 4.94.0,
including a task surviving `docker compose down` and `up`.

The two LLM projects run on a **real model** since 6 Oct 2026: `qwen3.5:4b`
on Ollama, locally, no account and no cost. BE-07 scored 8/8 on its eval, and
its README explains why the honest number is 4/4 (four cases are the prompt's
own examples). BE-09 sent three messages through Inngest and each took the path
I wrote down before running it. Both keep a keyword stub (`LLM_STUB=1`) so they
run with nothing installed.

## One repo, not six

The assignment briefs allow it. BE-06: *"own repo or a clearly named folder
(e.g. `background-job/`) in a shared one."* BE-08 says the same.

Each folder was merged in with `git subtree`, so **every stage commit survived** —
56 of them, one per stage as the briefs require. `git log --oneline` shows the
whole history. A copy-paste would have thrown that away, and the commit history
is part of what is being marked.
