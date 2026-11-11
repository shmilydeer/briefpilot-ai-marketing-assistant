# BriefPilot — AI Overseas Social Marketing Brief Assistant

A small, human-in-the-loop AI product prototype. Turn ambiguous marketing needs into a structured, editable brief, then generate reviewable TikTok and Instagram copy. Built as a portfolio/assessment MVP, **not a production marketing service**.

## Actual scope
- Real OpenAI API call #1: extract a structured marketing brief (Pydantic model)
- Human checks and edits brief fields before generation
- Real OpenAI API call #2: generate channel-specific drafts (Pydantic model)
- Editable generated hook, body, CTA and visual guidance
- Deterministic presence checks; AI-suggested claims to verify
- Manual approval status and Markdown/JSON export

**Not implemented:** login, analytics, publishing, retrieval, automated claim verification, persistent user database, team collaboration, agent orchestration.

## Architecture
`Streamlit UI → Python logic → OpenAI Chat Completions Parse / Pydantic → Human review → Markdown/JSON export`

Default model: `gpt-4o-mini`. Model access and charges depend on the owner's OpenAI API account. A ChatGPT subscription does **not** automatically provide API credit.

## Local setup
1. Install Python 3.11+.
2. `python -m venv .venv`
3. Activate: Windows `.venv\\Scripts\\activate`, macOS/Linux `source .venv/bin/activate`.
4. `pip install -r requirements.txt`
5. Set an environment variable `OPENAI_API_KEY` or create a local `.streamlit/secrets.toml` with `OPENAI_API_KEY = "your-key"`. **Never commit this file or share keys in a chat/screenshot.**
6. `streamlit run app.py`
7. `pytest -q`

## Deployment (Streamlit Community Cloud)
1. Create a GitHub repository and push these source files. Do not push `.streamlit/secrets.toml`.
2. In https://share.streamlit.io/ select **Create app**, choose repo/branch, and set entrypoint `app.py`.
3. Under **Advanced settings → Secrets**, add `OPENAI_API_KEY = "..."` and deploy.
4. Open the public URL in a private browser, run the complete flow, and download both exports.
5. To prevent surprise costs, set provider-level usage limits and monitor API spend. A public demo with a server-side key still lets visitors trigger paid API requests; restrict exposure or take the app offline when not needed.

## Product choices
- Unknown facts are empty strings; missing fields and assumptions remain visible.
- A user can edit a brief before the second model call; generated content is editable.
- Rule checks confirm presence only, **not truthfulness, quality, cultural fit, legal compliance or creative effectiveness**.
- Only a human can mark a draft approved. No automated posting.
- No personal data should be entered in demo briefs.

## Manual acceptance checklist
- [ ] Real API returns structured Brief
- [ ] Input missing key details is surfaced rather than fabricated
- [ ] Human edit changes data passed to content generation
- [ ] Selected channels return distinct drafts
- [ ] Reviewer can edit content and choose review status
- [ ] Markdown and JSON download successfully
- [ ] Deployed public URL works in incognito mode
- [ ] No API key committed to GitHub or visible in client

## Test fixtures
See `TEST_PLAN.md`. Unit tests intentionally mock nothing; they test deterministic logic without paid API calls. Live end-to-end outcomes must be recorded *after* a user with an API key executes them.

## Known limitations
- No persistent storage; Streamlit session data may disappear on reload.
- Content editing is immediate, but rerunning generation overwrites generated text.
- Structured output enforces shape, not factual correctness.
- Requests run on the server and can incur cost; simple UI is not a secure multi-tenant product.
- No full accessibility audit or cross-browser testing completed.
