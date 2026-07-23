"""Orchestration engine: deliberations, revisions, execution, daily cycle.

Every LLM call goes through call_llm(). Agents never act externally —
they think, argue, and produce artifacts that wait for CEO approval.
"""
import json
import logging
import threading

import requests
from django.conf import settings

from django.core.mail import send_mail
from django.utils import timezone

from .models import (
    Agent, ApprovalPolicy, Artifact, Capability, Deliberation, DelibMessage, Directive,
    OrgMemory, ProviderConfig, Proposal, StandingOrder, UsageRecord,
)


def notify(subject, body):
    """Best-effort email to the CEO. Silent if SMTP isn't configured."""
    if not (settings.EMAIL_HOST and settings.NOTIFY_EMAIL):
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [settings.NOTIFY_EMAIL], fail_silently=True)
    except Exception:
        log.exception("notify failed")

log = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _provider_cfg():
    try:
        return ProviderConfig.get_solo()
    except Exception:
        return None  # table not migrated yet — fall back to env-only


def provider_key(provider, cfg=None):
    """The effective API key for a provider: a UI-saved key wins, else the env
    var. `cfg` may be None (before the table exists), in which case env-only."""
    cfg = cfg if cfg is not None else _provider_cfg()
    if provider == "openai":
        saved = (cfg.openai_key if cfg else "") or ""
        return (saved or settings.OPENAI_API_KEY or "").strip()
    saved = (cfg.anthropic_key if cfg else "") or ""
    return (saved or settings.ANTHROPIC_API_KEY or "").strip()


def active_provider(cfg=None):
    """The live provider, with a safety fallback: if the selected one has no
    API key configured but the other does, use the one that can actually run."""
    cfg = cfg if cfg is not None else _provider_cfg()
    chosen = (cfg.provider if cfg else None) or getattr(settings, "LLM_PROVIDER", "anthropic")
    has_openai = bool(provider_key("openai", cfg))
    has_anthropic = bool(provider_key("anthropic", cfg))
    if chosen == "openai" and not has_openai and has_anthropic:
        return "anthropic"
    if chosen == "anthropic" and not has_anthropic and has_openai:
        return "openai"
    return chosen


def _call_anthropic(system, messages, max_tokens, model, web_search, api_key):
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if web_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {}) or {}
    text = "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text").strip()
    return text, {
        "model": data.get("model", model),
        "input_tokens": usage.get("input_tokens", 0) or 0,
        "output_tokens": usage.get("output_tokens", 0) or 0,
    }


def _call_openai(system, messages, max_tokens, model, web_search, api_key):
    # OpenAI's Chat Completions API. The message shape ({"role","content"}) is
    # already compatible; the system prompt is just the first message. Hosted
    # web search isn't wired up here, so web_search is a no-op for this provider.
    if web_search:
        log.debug("web_search requested but the OpenAI provider runs without it")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}] + messages,
    }
    resp = requests.post(
        OPENAI_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {}) or {}
    choices = data.get("choices") or []
    text = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    return text, {
        "model": data.get("model", model),
        "input_tokens": usage.get("prompt_tokens", 0) or 0,
        "output_tokens": usage.get("completion_tokens", 0) or 0,
    }


def call_llm(system, messages, max_tokens=1200, model=None, fast=False, web_search=False, org=None, agent=None, purpose=""):
    """Provider-agnostic LLM call. `fast=True` picks the cheaper model of the
    active provider; `model` overrides the model outright if you must."""
    cfg = _provider_cfg()
    provider = active_provider(cfg)
    api_key = provider_key(provider, cfg)
    if provider == "openai":
        chosen = model or (settings.OPENAI_MODEL_FAST if fast else settings.OPENAI_MODEL)
        text, meta = _call_openai(system, messages, max_tokens, chosen, web_search, api_key)
    else:
        chosen = model or (settings.ENGINE_MODEL_FAST if fast else settings.ENGINE_MODEL)
        text, meta = _call_anthropic(system, messages, max_tokens, chosen, web_search, api_key)
    try:
        UsageRecord.objects.create(
            org=org or (agent.org if agent else None), agent=agent, purpose=purpose,
            model=meta["model"],
            input_tokens=meta["input_tokens"],
            output_tokens=meta["output_tokens"],
        )
    except Exception:
        log.exception("usage metering failed")
    return text


def parse_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        t = t[start : end + 1]
    return json.loads(t)


def agent_can_search(agent):
    return agent.capabilities.filter(kind="web_research").exists()


def memory_context(org):
    """Distilled playbook + the CEO's most recent raw decisions."""
    mem = getattr(org, "memory", None)
    chunks = []
    if mem and mem.playbook:
        chunks.append("WHAT WE'VE LEARNED ABOUT THE CEO (distilled playbook):\n" + mem.playbook)
    recent = org.proposals.exclude(status__in=["pending", "revision"]).order_by("-updated_at")[:8]
    if recent:
        lines = []
        for p in recent:
            fb = f" — CEO said: \"{p.ceo_feedback}\"" if p.ceo_feedback else ""
            lines.append(f"- [{p.status.upper()}] {p.title}{fb}")
        chunks.append("RECENT CEO DECISIONS (learn from these — don't repropose rejected directions):\n" + "\n".join(lines))
    return ("\n" + "\n\n".join(chunks) + "\n") if chunks else ""


def agent_system(agent, extra=""):
    const = getattr(agent.org, "constitution", None)
    const_text = const.content if const else ""
    caps = capability_context(agent)
    caps += memory_context(agent.org)
    return (
        f"You are {agent.name}, {agent.role} at {agent.org.name}. "
        f"You are a world-class expert. Department: {agent.department}.\n"
        f"YOUR CHARACTER & EXPERTISE:\n{agent.persona}\n\n"
        f"COMPANY CONSTITUTION (policies, culture, direction — always act within it):\n{const_text}\n"
        f"{caps}"
        f"\nHard rule: nothing ships without CEO (the human) approval. You propose, argue, and produce work — the CEO decides.\n{extra}"
    )


def capability_context(agent):
    """Fetch read-only data sources granted to this agent and inline them."""
    chunks = []
    for cap in agent.capabilities.all():
        if cap.kind == "web_note" and cap.notes:
            chunks.append(f"[Standing knowledge — {cap.label}]\n{cap.notes}")
        elif cap.kind == "data_source" and cap.url:
            try:
                headers = {}
                if cap.auth_header and ":" in cap.auth_header:
                    k, v = cap.auth_header.split(":", 1)
                    headers[k.strip()] = v.strip()
                r = requests.get(cap.url, headers=headers, timeout=15)
                body = r.text[:6000]
                chunks.append(f"[Live data — {cap.label} ({cap.url})]\n{body}")
            except Exception as e:  # data being down shouldn't kill a deliberation
                chunks.append(f"[Live data — {cap.label}] UNAVAILABLE ({e})")
    if not chunks:
        return ""
    return "\nDATA YOU HAVE ACCESS TO:\n" + "\n\n".join(chunks) + "\n"


def ai_agents(org):
    return org.agents.filter(active=True, is_human=False)


def roster_text(org):
    lines = []
    for a in ai_agents(org):
        boss = f", reports to {a.reports_to.name}" if a.reports_to else ""
        lines.append(f"- id={a.id} {a.name} ({a.role}, {a.department}{boss}) — {a.mandate}")
    return "\n".join(lines)


def pick_team(org, directive_text):
    """Route a directive: choose the owning head + 1-2 participants."""
    system = (
        f"You are the routing brain of {org.name}. Given the CEO's directive and the roster, "
        "choose the department head who owns it plus 1-2 relevant participants. "
        'Respond ONLY with JSON: {"head_id": int, "participant_ids": [int, ...], "topic": "short title"}'
    )
    text = call_llm(system, [{"role": "user", "content": f"ROSTER:\n{roster_text(org)}\n\nDIRECTIVE:\n{directive_text}"}], 400, fast=True, org=org, purpose="routing")
    data = parse_json(text)
    head = ai_agents(org).get(id=data["head_id"])
    participants = list(ai_agents(org).filter(id__in=data.get("participant_ids", [])).exclude(id=head.id))[:2]
    return head, participants, data.get("topic", directive_text[:80])


def run_deliberation(deliberation_id, directive_text):
    """Head frames → participants respond → head synthesizes into a proposal."""
    delib = Deliberation.objects.get(id=deliberation_id)
    org = delib.org
    try:
        head, participants, topic = pick_team(org, directive_text)
        delib.topic = topic
        delib.save(update_fields=["topic"])

        transcript = []

        def speak(agent, prompt, rnd):
            content = call_llm(
                agent_system(agent, "You are in an internal meeting. Be concrete, opinionated, brief (under 180 words). If you have web access and current facts matter, check them."),
                [{"role": "user", "content": prompt}],
                900,
                web_search=agent_can_search(agent), agent=agent, purpose="deliberation",
            )
            DelibMessage.objects.create(deliberation=delib, agent=agent, round=rnd, content=content)
            transcript.append(f"{agent.name} ({agent.role}): {content}")
            return content

        speak(head, f"The CEO directed: \"{directive_text}\". Open the meeting: frame the problem and your initial position.", 1)
        for p in participants:
            speak(p, f"Meeting topic: \"{directive_text}\".\nDiscussion so far:\n" + "\n\n".join(transcript) + "\n\nGive your expert take. Agree, disagree, or extend — with reasons.", 1)

        synth_prompt = (
            f"Discussion so far:\n" + "\n\n".join(transcript) +
            "\n\nAs the owning head, synthesize a single proposal for the CEO's desk. "
            f"Choose who executes it from: {', '.join([f'{a.name} (id={a.id})' for a in [head] + participants])}. "
            'Respond ONLY with JSON: {"title": str, "summary": str (what we will do and why, under 150 words), '
            '"rationale": str (who argued what, points of disagreement, why this direction won), "assigned_to_id": int}'
        )
        data = parse_json(call_llm(agent_system(head), [{"role": "user", "content": synth_prompt}], 900, agent=head, purpose="synthesis"))
        assigned = ai_agents(org).filter(id=data.get("assigned_to_id")).first() or head
        prop_obj = Proposal.objects.create(
            org=org, deliberation=delib, title=data["title"], summary=data["summary"],
            rationale=data.get("rationale", ""), proposed_by=head, assigned_to=assigned,
        )
        notify(f"[HQ] Proposal on your desk: {data['title']}", data["summary"])
        delib.status = "done"
        delib.save(update_fields=["status"])
        apply_policy(prop_obj.id)
    except Exception as e:
        log.exception("deliberation failed")
        delib.status, delib.error = "failed", str(e)
        delib.save(update_fields=["status", "error"])


def run_revision(proposal_id):
    """CEO tweaked it — the team revises and resubmits."""
    prop = Proposal.objects.get(id=proposal_id)
    try:
        head = prop.proposed_by or prop.assigned_to
        delib = prop.deliberation or Deliberation.objects.create(org=prop.org, topic=prop.title, status="running")
        delib.status = "running"
        delib.save(update_fields=["status"])
        DelibMessage.objects.create(deliberation=delib, agent=None, round=2, content=f"CEO feedback: {prop.ceo_feedback}")
        prompt = (
            f"Your proposal \"{prop.title}\" came back from the CEO with feedback:\n\"{prop.ceo_feedback}\"\n"
            f"Original summary: {prop.summary}\n\n"
            "Revise the proposal to address the feedback. "
            'Respond ONLY with JSON: {"title": str, "summary": str, "rationale": str (what changed and why)}'
        )
        data = parse_json(call_llm(agent_system(head), [{"role": "user", "content": prompt}], 900, agent=head, purpose="revision"))
        DelibMessage.objects.create(deliberation=delib, agent=head, round=2, content=f"Revised: {data['summary']}")
        prop.title, prop.summary = data["title"], data["summary"]
        prop.rationale = (prop.rationale + "\n\nREVISION: " + data.get("rationale", "")).strip()
        prop.status = "pending"
        prop.save()
        delib.status = "done"
        delib.save(update_fields=["status"])
    except Exception as e:
        log.exception("revision failed")
        prop.status = "failed"
        prop.save(update_fields=["status"])


ARTIFACT_INSTRUCTIONS = (
    "Now execute the approved proposal and produce the actual deliverable, not a description of it.\n"
    "- If the work is visual (flyer, graphic, card, page): kind='html' — a single complete self-contained HTML document "
    "with inline CSS, real copy, mobile-sized (majority of viewers are on phones). Use the company's brand colors if the constitution names them.\n"
    "- If the work is writing (post, script, email, plan, analysis): kind='markdown'.\n"
    'Respond ONLY with JSON: {"kind": "html"|"markdown"|"text", "title": str, "content": str}'
)


def run_execution(proposal_id):
    prop = Proposal.objects.get(id=proposal_id)
    try:
        agent = prop.assigned_to or prop.proposed_by
        context = f"Approved proposal: {prop.title}\n{prop.summary}"
        if prop.ceo_feedback:
            context += f"\nCEO notes: {prop.ceo_feedback}"
        data = parse_json(call_llm(agent_system(agent, ARTIFACT_INSTRUCTIONS), [{"role": "user", "content": context}], 4000, web_search=agent_can_search(agent), agent=agent, purpose="execution"))
        Artifact.objects.create(
            proposal=prop, agent=agent, kind=data.get("kind", "markdown"),
            title=data.get("title", prop.title), content=data.get("content", ""),
        )
        prop.status = "artifact_pending"
        prop.save(update_fields=["status"])
        notify(f"[HQ] Deliverable ready for sign-off: {data.get('title', prop.title)}", f"From {agent.name} — open HQ to review.")
    except Exception as e:
        log.exception("execution failed")
        prop.status = "failed"
        prop.save(update_fields=["status"])


def run_daily_cycle(org):
    """Each proactive agent generates one idea, their manager weighs in, it lands on the desk."""
    for agent in org.agents.filter(active=True, proactive=True, is_human=False):
        try:
            delib = Deliberation.objects.create(org=org, topic=f"Daily idea — {agent.name}", status="running")
            idea = call_llm(
                agent_system(agent, "Daily proactive cycle: propose ONE concrete, high-leverage idea for the company right now, from your role's lens. Do NOT repropose directions the CEO has rejected. Under 150 words."),
                [{"role": "user", "content": "What should we do next? One idea."}],
                600, fast=True, agent=agent, purpose="daily_idea",
            )
            DelibMessage.objects.create(deliberation=delib, agent=agent, round=1, content=idea)
            reviewer = agent.reports_to
            rationale = ""
            if reviewer:
                review = call_llm(
                    agent_system(reviewer, "Briefly review your report's idea: strengthen, challenge, or refine it. Under 100 words."),
                    [{"role": "user", "content": f"{agent.name} proposes:\n{idea}"}],
                    400, fast=True, agent=reviewer, purpose="daily_review",
                )
                DelibMessage.objects.create(deliberation=delib, agent=reviewer, round=1, content=review)
                rationale = f"{agent.name} proposed; {reviewer.name} reviewed: {review}"
            data = parse_json(call_llm(
                agent_system(agent),
                [{"role": "user", "content": f"Your idea:\n{idea}\n\nCondense into a proposal. Respond ONLY with JSON: {{\"title\": str, \"summary\": str}}"}],
                500, fast=True, agent=agent, purpose="daily_condense",
            ))
            prop_obj = Proposal.objects.create(
                org=org, deliberation=delib, title=data["title"], summary=data["summary"],
                rationale=rationale, proposed_by=agent, assigned_to=agent,
            )
            delib.status = "done"
            delib.save(update_fields=["status"])
            apply_policy(prop_obj.id)
        except Exception:
            log.exception("daily cycle failed for %s", agent)
    run_standing_orders(org)
    distill_memory(org)


def in_thread(fn, *args):
    t = threading.Thread(target=fn, args=args, daemon=True)
    t.start()


def deliver_artifact(artifact_id):
    """Fire the executing agent's webhook capabilities with the approved deliverable."""
    art = Artifact.objects.get(id=artifact_id)
    agent = art.agent
    results = []
    if agent:
        for cap in agent.capabilities.filter(kind="webhook"):
            try:
                headers = {"Content-Type": "application/json"}
                if cap.auth_header and ":" in cap.auth_header:
                    k, v = cap.auth_header.split(":", 1)
                    headers[k.strip()] = v.strip()
                r = requests.post(
                    cap.url,
                    headers=headers,
                    json={"title": art.title, "kind": art.kind, "content": art.content,
                          "proposal": art.proposal.title, "agent": agent.name},
                    timeout=30,
                )
                results.append(f"{cap.label}: {r.status_code}")
            except Exception as e:
                results.append(f"{cap.label}: FAILED ({e})")
    art.delivery = "; ".join(results) if results else ""
    art.save(update_fields=["delivery"])


def distill_memory(org):
    """Compress recent CEO decisions into a durable playbook the whole company reads."""
    decided = org.proposals.exclude(status__in=["pending", "revision"]).order_by("-updated_at")[:20]
    if not decided:
        return
    mem, _ = OrgMemory.objects.get_or_create(org=org)
    lines = []
    for p in decided:
        fb = f' CEO: "{p.ceo_feedback}"' if p.ceo_feedback else ""
        lines.append(f"[{p.status}] {p.title} — {p.summary[:150]}{fb}")
    prompt = (
        "You maintain the institutional memory of this company. Below are the CEO's recent decisions "
        "and the current playbook. Update the playbook: durable lessons about what the CEO approves, "
        "rejects, and why — their taste, standards, and strategic direction. "
        "Under 300 words, plain bullet lines, no preamble.\n\n"
        f"CURRENT PLAYBOOK:\n{mem.playbook or '(empty)'}\n\nRECENT DECISIONS:\n" + "\n".join(lines)
    )
    try:
        mem.playbook = call_llm(
            "You distill decisions into durable organizational lessons.",
            [{"role": "user", "content": prompt}], 600, fast=True, org=org, purpose="memory",
        )
        mem.save()
    except Exception:
        log.exception("memory distillation failed")


def run_custom_meeting(deliberation_id, topic, agent_ids):
    """CEO-convened room: chosen people, chosen topic, ends as a proposal."""
    delib = Deliberation.objects.get(id=deliberation_id)
    org = delib.org
    try:
        team = list(ai_agents(org).filter(id__in=agent_ids))
        if not team:
            raise ValueError("No active AI agents selected.")
        head = next((a for a in team if a.is_head), team[0])
        transcript = []
        for a in team:
            prompt = (f"The CEO convened this meeting. Topic: \"{topic}\"." +
                      ("\nDiscussion so far:\n" + "\n\n".join(transcript) if transcript else "") +
                      "\n\nGive your expert take — concrete, opinionated, under 180 words.")
            content = call_llm(
                agent_system(a, "You are in a meeting the CEO convened."),
                [{"role": "user", "content": prompt}], 900,
                web_search=agent_can_search(a), agent=a, purpose="meeting",
            )
            DelibMessage.objects.create(deliberation=delib, agent=a, round=1, content=content)
            transcript.append(f"{a.name} ({a.role}): {content}")
        synth = (
            "Discussion:\n" + "\n\n".join(transcript) +
            f"\n\nSynthesize one proposal for the CEO. Choose the executor from: {', '.join(f'{a.name} (id={a.id})' for a in team)}. "
            'Respond ONLY with JSON: {"title": str, "summary": str, "rationale": str, "assigned_to_id": int}'
        )
        data = parse_json(call_llm(agent_system(head), [{"role": "user", "content": synth}], 900, agent=head, purpose="synthesis"))
        assigned = ai_agents(org).filter(id=data.get("assigned_to_id")).first() or head
        prop_obj = Proposal.objects.create(
            org=org, deliberation=delib, title=data["title"], summary=data["summary"],
            rationale=data.get("rationale", ""), proposed_by=head, assigned_to=assigned,
        )
        notify(f"[HQ] Meeting outcome: {data['title']}", data["summary"])
        delib.status = "done"
        delib.save(update_fields=["status"])
        apply_policy(prop_obj.id)
    except Exception as e:
        log.exception("meeting failed")
        delib.status, delib.error = "failed", str(e)
        delib.save(update_fields=["status", "error"])


def run_standing_orders(org):
    """Due mandates execute straight to a deliverable awaiting sign-off."""
    today = timezone.localdate()
    for o in org.standing_orders.filter(active=True).select_related("agent"):
        due = o.cadence == "daily" or (o.cadence == "weekly" and o.weekday == today.weekday())
        if not due or o.last_run == today or not o.agent.active or o.agent.is_human:
            continue
        try:
            delib = Deliberation.objects.create(org=org, topic=f"Standing order — {o.agent.name}", status="done")
            DelibMessage.objects.create(deliberation=delib, agent=o.agent, round=1,
                                        content=f"Standing order: {o.instruction}")
            prop = Proposal.objects.create(
                org=org, deliberation=delib, title=f"{o.agent.name}: {o.instruction[:120]}",
                summary=f"Recurring mandate ({o.get_cadence_display().lower()}): {o.instruction}",
                rationale="Standing order set by the CEO — executed without deliberation.",
                proposed_by=o.agent, assigned_to=o.agent, status="approved",
            )
            run_execution(prop.id)
            o.last_run = today
            o.save(update_fields=["last_run"])
        except Exception:
            log.exception("standing order failed for %s", o.agent)


def apply_policy(proposal_id):
    """Route a fresh proposal per department policy. If the policy delegates internal
    approval to an AI manager, the manager reviews once (fast model) and may greenlight
    execution. Deliverables ALWAYS stop at a human regardless of this path."""
    prop = Proposal.objects.get(id=proposal_id)
    agent = prop.proposed_by or prop.assigned_to
    if not agent or prop.status != "pending":
        return
    pol = ApprovalPolicy.objects.filter(org=prop.org, department=agent.department).first()
    if not pol or pol.proposal_approval != "ai_manager":
        return
    mgr = agent.reports_to
    if not (mgr and mgr.active and not mgr.is_human):
        return
    try:
        data = parse_json(call_llm(
            agent_system(mgr, "You hold delegated approval authority for internal work in your department. Review strictly against the constitution and company memory."),
            [{"role": "user", "content":
              f"Proposal from {agent.name}:\nTitle: {prop.title}\nSummary: {prop.summary}\n\n"
              'Approve for execution, or hold for the human desk? Respond ONLY with JSON: '
              '{"decision": "approve"|"hold", "note": str (one line)}'}],
            400, fast=True, agent=mgr, purpose="delegated_review",
        ))
        note = data.get("note", "")
        DelibMessage.objects.create(
            deliberation=prop.deliberation, agent=mgr, round=2,
            content=f"[Delegated review] {data.get('decision', 'hold').upper()}: {note}",
        ) if prop.deliberation else None
        if data.get("decision") == "approve":
            prop.status = "approved"
            prop.rationale = (prop.rationale + f"\n\nAUTO-APPROVED by {mgr.name} under {agent.department} policy: {note}").strip()
            prop.save()
            run_execution(prop.id)
        else:
            prop.rationale = (prop.rationale + f"\n\nHELD by {mgr.name}: {note}").strip()
            prop.save(update_fields=["rationale"])
    except Exception:
        log.exception("delegated review failed — proposal stays on the human desk")
