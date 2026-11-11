# BriefPilot — Test Plan & Evidence Log

## Unit tests
Run `pytest -q`; store exact date, command output and any failures below. This does NOT verify live LLM quality.

## E2E cases (must be performed with a real API key)
| ID | Test input | Expected behaviour | Actual result | Evidence | Status |
|---|---|---|---|---|---|
| T01 | UK reusable travel cup brand, with audience and awareness goal but no discount | Extract facts, flag missing offer/CTA if absent, generate TikTok + Instagram drafts | Not yet executed | Pending | Pending |
| T02 | Independent skincare brand with vague claim "works instantly" | Make unsupported efficacy claim visible for verification, never fabricate study data | Not yet executed | Pending | Pending |
| T03 | Creator launching a workshop without date, price or booking URL | Do not invent workshop details; allow manual edit, check missing fields, export drafts | Not yet executed | Pending | Pending |

## Review method
1. Save screenshots of input, extracted brief, human edit, drafts, quality checks, downloaded files.
2. In each run, label **Observed / Failed / Not tested**. Never claim user studies, conversions, or performance improvements.
3. Check downloaded Markdown/JSON for review status and channel content.
4. Verify public URL in a fresh private/incognito browser and note whether it works without a login.

## Execution log
No live API executions have yet been performed. Do not replace this line until actual testing.
