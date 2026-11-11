# BriefPilot — One-Page PRD v0.1 (2026-11-11)

**Problem:** Small brand marketers receive underspecified requests and spend time translating them into actionable creative briefs; unreviewed AI copy risks unsupported claims and channel mismatch.

**Target user:** Solo marketer / small business owner preparing TikTok and Instagram campaigns.

**Job to be done:** Given a fuzzy marketing request, produce a brief I can correct and a channel-specific first draft I can audit and export.

**Core flow:** Raw request → AI structured extraction → missing info/assumptions → human edits → AI channel drafts → rule checks + human review → export.

**In scope:** One request per session; text input; exactly two separate AI model calls; TikTok and Instagram; review and export.

**Out of scope:** User accounts, automated posting, audience insights, web search, payment, analytics, long-term storage, complex agents.

**Success criteria (functional, not commercial):** (1) A reviewer can complete the entire flow in an online demo. (2) Every draft is generated via an actual LLM call. (3) Users can see and correct AI interpretations. (4) Output has explicit review status. (5) Test evidence is recorded transparently.

**Key risks:** Unsupported claims, prompt injection in user text, service/API cost, public demo abuse, missing details and poor channel differentiation. These are partly mitigated with prompts, a schema, review flags, input limits and manual approval; not eliminated.

**Technical choices:** Python/Streamlit, OpenAI API Pydantic schema, session state, GitHub and Streamlit Community Cloud. No database.
