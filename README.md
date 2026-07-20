# AI HQ — your company, run by expert agents, governed by you

Multi-agent "company in a box": every staff member is an independent expert agent with a persona,
a reporting line, and scoped capabilities. They deliberate, propose, and execute — but **nothing
ships without the CEO's approval**. Tryblie is seeded as tenant #1.

## The loop
1. **Directive** — you tell the company what you want (or the daily cron makes agents proactive).
2. **Deliberation** — the routing brain picks the owning department head + participants; they argue on the record.
3. **Proposal → your desk** — with full provenance: who argued what, and why this direction won.
4. **You decide** — approve (they execute), send back with notes (they revise), or reject.
5. **Deliverable → sign-off** — the assignee produces the real artifact (rendered HTML flyer, post, analysis). You approve or send it back for a redo. You are the hands of the company: approved work is yours to send out.

## Stack
- **Backend** `backend/` — Django 5 + DRF, token auth, Anthropic API engine (`core/engine.py`), Postgres.
- **Frontend** `frontend/` — React (Vite). Desk, team + persistent 1:1 chats, constitution editor.
- **Render** `render.yaml` — API web service, static frontend, Postgres, weekday-morning cron for the daily idea cycle.

## Deploy to Render (blueprint)
1. Push this folder to a GitHub repo.
2. Render → **New → Blueprint** → pick the repo. Render reads `render.yaml`.
3. Set the prompted env vars:
   - `ANTHROPIC_API_KEY` — your key from console.anthropic.com (this is your COGS).
   - `CEO_PASSWORD` — your login password (username defaults to `geoffrey`).
   - On **ogaboss-app**: `VITE_API_URL` = the ogaboss-api URL (e.g. `https://ogaboss-api.onrender.com`).
   - On **ogaboss-api**: `FRONTEND_ORIGIN` = the ogaboss-app URL (locks CORS down).
4. Deploy. The build migrates and seeds Tryblie automatically. Log in and send your first directive.

## Run locally
```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-…  CEO_PASSWORD=changeme
python manage.py migrate && python manage.py seed_org && python manage.py runserver
# new terminal
cd frontend && npm install && npm run dev   # VITE_API_URL defaults to http://localhost:8000
```

## Grant an agent real data (capabilities)
In Django admin (`/admin/`), add a **Capability** to an agent:
- `data_source` + URL (+ optional `Header: value` auth) → the agent reads that JSON live during
  deliberation/execution. Point Ifeanyi at a read-only Tryblie stats endpoint and his analyses use real numbers.
- `web_note` → standing knowledge injected into the agent's context.

## Productizing (multi-tenant)
The data model is org-scoped already (`Organization` on everything). To sell it:
add signup → create an Organization per customer, scope `get_org()` by the authed user,
let customers design their own roster + constitution. Token spend per org is your usage meter.

## What makes it compound (v2 upgrades)
- **Organizational memory** — every approve/tweak/reject is injected into all agents' context, and the daily
  cycle distills decisions into a durable playbook (`OrgMemory`, visible on the Constitution tab). The company
  learns the CEO's taste and stops reproposing rejected directions.
- **Model routing** — routing, daily ideas, and distillation run on `ENGINE_MODEL_FAST` (Haiku by default);
  deliberation and execution on `ENGINE_MODEL` (Sonnet). Both env-overridable. Cuts cost ~5x.
- **Web research** — agents with a `web_research` capability (seeded: Femi, Tunde, Emeka, Ade) can search the
  live web during deliberation and execution, so regulatory/market advice uses current facts.
- **Close the loop (webhooks)** — give an agent a `webhook` capability (URL + optional auth header) and every
  deliverable you approve is POSTed there as JSON `{title, kind, content, proposal, agent}`. Point Zara's at a
  Tryblie banners endpoint or a Zapier hook and "approved" means "shipped". Delivery status shows on the artifact.

## v3 — the governed company
- **Hire & edit anyone, anytime** — Team tab: "+ Hire a new agent", or ✎ any agent to view/edit their full dossier
  (name, role, persona/expertise/perspective, mandate, reporting line, head/proactive flags, deactivate).
- **Humans in the org** — people sign up ("Join a company" with your company code, default `tryblie`), you enroll
  them from Admin → People with a role. Department heads get real decision rights: they can approve/tweak/reject
  proposals in their department; **final deliverable sign-off stays CEO-only**. Human seats appear on the org
  chart, are never simulated, and can head AI reports.
- **Meeting rooms** — Meet tab: pick any people, set a topic, watch the transcript build live; every meeting ends
  as a proposal on the desk.
- **Standing orders** — recurring mandates per agent (daily or a weekday), set in the agent editor. The daily cron
  executes them straight to a deliverable awaiting your sign-off. "Zara: one flyer every Friday."
- **Payroll meter** — Admin tab: real token usage per agent/department this month with estimated USD. The
  usage-billing foundation for productizing.
- **Email notifications** — set `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`,
  `NOTIFY_EMAIL` (ZeptoMail SMTP works) and you get an email whenever a proposal or deliverable lands.
- **Multi-tenant** — everything is scoped to the logged-in user's organization. "Found a company" on the signup
  screen creates a fresh org with its own constitution and a starter Chief of Staff — the sellable path.

## Appearance — 11 themes × light/dark
The ◐ button in the top bar opens the appearance panel. Eleven full styles, each with true light and dark
variants: **Studio** (clean, quiet), **Glass** (frosted, gradient ground, pulse strip), **Editorial**
(serif docket, ruled rows), **Brutal** (thick borders, stamp tags), **Dossier** (tabbed case files),
**Clay** (puffy, borderless, soft), **Neumorph** (carved from one surface, inset inputs), **Maximal**
(clashing pink/yellow/teal, tilted cards, "LOOK AT THIS!!"), **Terminal** (all-mono green phosphor,
[DECIDE] brackets, log rows), **Bento** (tile grid desk with a featured first tile), **Y2K** (glossy
chrome gradients, pill buttons, "★ new 4 u ★"). The choice is saved per
device. Themes change more than colors — each has its own **layout system and voice**: Studio is a clean
list; Glass adds a live pulse strip and roomy cards; Editorial renders the desk as a numbered docket with
serif headlines and inline "Decide →" actions; Brutal puts rotated stamp-tags on chunky cards ("Needs your
ink"); Dossier turns every proposal into a tabbed case file with a tilted PENDING stamp ("Open case files").
Section titles, buttons, and placeholders re-word themselves per theme via the `strings` map in
`themes.js`, and layout branches live in `ProposalItem` / `TeamRow` in `App.jsx` keyed off `layout`. Every color, radius, border, shadow, and typeface is a CSS variable in `frontend/src/themes.js`;
add a new theme by adding one object there, and per-style structural quirks live at the bottom of
`frontend/src/styles.css` under `html[data-theme="…"]`.

## Chain of command (v4)
- **Per-department approval policy** (Admin → Approvals): who greenlights *proposals* (CEO, human head, or
  an AI manager auto-reviewing on the fast model — saves the CEO's attention and tokens), and who signs
  *deliverables* (CEO or human head). **Hard rule, enforced server-side and un-configurable: anything that
  leaves the application is signed by a human.** AI can approve AI's internal work; AI can never sign outbound.
- **Scoped desks** — human department heads see only their department's queue; the CEO sees everything.
- **Connections & powers from the UI** (agent editor): plug integrations in without touching code — data
  sources (any REST API: GA4, Meta Graph/Instagram, the company's own backend) with URL + auth header,
  outbound webhooks, web research, standing knowledge. Tokens are stored server-side and never exposed back
  to the client. OAuth-flow connectors (one-click Google/Meta sign-in) are the natural next layer on top.

## Cost + scaling notes
- Each deliberation ≈ 4–6 model calls; daily cycle ≈ 3 calls per proactive agent (5 seeded). Tune `proactive` flags to control burn.
- Background work runs in threads for v1 (fine on one Render instance). The upgrade path when it grows: Celery + Redis.
