# TODO

## Agent Tasks

BE-07 / A17, Put an LLM behind your API (`task-api`), on a real local model (Ollama, qwen3.5:4b)
- [x] First real call works (Stage 0 hello script) and the model's thinking mode is handled
- [x] Fix: Retry-After is ignored (headers are httpx.Headers, not a dict; and it can be an HTTP date)
- [x] Real answers for three inputs, read and noted (Stage 2)
- [x] Real 422 + quarantine line from a prompt that demands a bad category (Stage 3 checkpoint)
- [x] Real 504 from a too-short timeout; kill switch makes zero calls (Stage 4)
- [x] Real eval score on the 8 cases, with date and prompt version (Stage 5)
- [x] Cost log for one real call + estimate for 10,000 requests a day
- [x] Prompt-injection test against the real model (the BANANA extra)
- [x] README: replace the stub score with the real one, keep the stub as the offline mode
- [x] Tests still green

BE-09, AI decision flow (`ai-decision-flow`), on the same real model
- [x] Real YES/NO answers through Inngest, three inputs end to end
- [x] Screenshots of a real run, README updated, tests green

BE-04 / A3, Containerize your stack (`task-api`)
- [x] Everything checkable without Docker re-checked against the A3 brief
- [x] One script that runs every A3 checkpoint once Docker exists (`verify-docker.ps1`)

Both
- [x] Push, and check the remote matches

## Zeref Tasks

- [ ] Install WSL (admin terminal + reboot), then Docker Desktop, then run `task-api/verify-docker.ps1`
- [ ] Paste the full briefs for the two capstones picked: Image Relevance & Auto-Tagging, LLM Usage Metering & Billing Service

## In Progress
