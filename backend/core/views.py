from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import engine
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail

from django.db.models import Sum
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.text import slugify

from .models import (
    Agent, ApprovalPolicy, Artifact, Capability, ChatMessage, Constitution, Deliberation,
    Directive, Member, Organization, Proposal, StandingOrder, UsageRecord,
)


def get_member(user):
    try:
        return user.membership
    except Member.DoesNotExist:
        return None


def is_ceo(request):
    m = get_member(request.user)
    return bool(m and m.role == "ceo" and m.status == "active")


def can_decide_proposal(request, p):
    m = get_member(request.user)
    if not m or m.status != "active":
        return False
    if m.role == "ceo":
        return True
    if m.role == "head" and m.department:
        dept_agents = [a for a in (p.proposed_by, p.assigned_to) if a]
        return any(a.department == m.department for a in dept_agents)
    return False


def get_org(request=None):
    if request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        m = get_member(request.user)
        if m and m.status != "removed":
            return m.org
    return Organization.objects.first()


def agent_dict(a):
    return {
        "id": a.id, "name": a.name, "role": a.role, "department": a.department,
        "mandate": a.mandate, "shape": a.shape, "is_head": a.is_head,
        "proactive": a.proactive, "reports_to": a.reports_to_id,
        "persona": a.persona, "active": a.active, "is_human": a.is_human,
        "linked_user": a.user.username if a.user else None,
        "capabilities": [{"kind": c.kind, "label": c.label} for c in a.capabilities.all()],
    }


def proposal_dict(p, deep=False):
    d = {
        "id": p.id, "title": p.title, "summary": p.summary, "status": p.status,
        "rationale": p.rationale, "ceo_feedback": p.ceo_feedback,
        "proposed_by": p.proposed_by.name if p.proposed_by else None,
        "assigned_to": p.assigned_to.name if p.assigned_to else None,
        "created_at": p.created_at.isoformat(), "updated_at": p.updated_at.isoformat(),
        "artifacts": [
            {"id": a.id, "kind": a.kind, "title": a.title, "status": a.status,
             "agent": a.agent.name if a.agent else None, "delivery": a.delivery,
             **({"content": a.content} if deep else {})}
            for a in p.artifacts.all()
        ],
    }
    if deep and p.deliberation:
        d["deliberation"] = {
            "topic": p.deliberation.topic,
            "status": p.deliberation.status,
            "messages": [
                {"agent": m.agent.name if m.agent else "CEO", "role": m.agent.role if m.agent else "CEO",
                 "round": m.round, "content": m.content}
                for m in p.deliberation.messages.all()
            ],
        }
    return d


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    # Match register(), which stores usernames lowercased, so login is
    # effectively case-insensitive and "GeoffreyWeta" == "geoffreyweta".
    username = (request.data.get("username") or "").strip().lower()
    user = authenticate(username=username, password=request.data.get("password", ""))
    if not user:
        return Response({"error": "Wrong username or password."}, status=status.HTTP_401_UNAUTHORIZED)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "username": user.username})


@api_view(["GET"])
def desk(request):
    org = get_org(request)
    m = get_member(request.user)
    qs = org.proposals.all()
    if m and m.role == "head" and m.department:
        from django.db.models import Q
        qs = qs.filter(Q(proposed_by__department=m.department) | Q(assigned_to__department=m.department))
    pending = qs.filter(status__in=["pending", "artifact_pending"])
    working = qs.filter(status__in=["approved", "revision"])
    recent = qs.filter(status__in=["done", "rejected", "failed"])[:10]
    return Response({
        "org": {"name": org.name},
        "pending": [proposal_dict(p) for p in pending],
        "working": [proposal_dict(p) for p in working],
        "recent": [proposal_dict(p) for p in recent],
    })


@api_view(["GET"])
def org_chart(request):
    org = get_org(request)
    return Response({"agents": [agent_dict(a) for a in org.agents.filter(active=True)]})


@api_view(["GET", "PUT"])
def constitution(request):
    org = get_org(request)
    const, _ = Constitution.objects.get_or_create(org=org)
    if request.method == "PUT":
        if not is_ceo(request):
            return Response({"error": "CEO only."}, status=403)
        const.content = request.data.get("content", "")
        const.save()
    return Response({"content": const.content, "updated_at": const.updated_at.isoformat()})


@api_view(["POST"])
def create_directive(request):
    org = get_org(request)
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"error": "Directive text required."}, status=400)
    directive = Directive.objects.create(org=org, text=text)
    delib = Deliberation.objects.create(org=org, directive=directive, topic=text[:200])
    engine.in_thread(engine.run_deliberation, delib.id, text)
    return Response({"deliberation_id": delib.id, "status": "running"})


@api_view(["GET"])
def deliberation_detail(request, pk):
    d = get_object_or_404(Deliberation, pk=pk, org=get_org(request))
    return Response({
        "id": d.id, "topic": d.topic, "status": d.status, "error": d.error,
        "messages": [
            {"agent": m.agent.name if m.agent else "CEO", "role": m.agent.role if m.agent else "CEO",
             "content": m.content}
            for m in d.messages.all()
        ],
        "proposal_ids": [p.id for p in d.proposals.all()],
    })


@api_view(["GET"])
def proposal_detail(request, pk):
    p = get_object_or_404(Proposal, pk=pk, org=get_org(request))
    return Response(proposal_dict(p, deep=True))


@api_view(["POST"])
def proposal_decide(request, pk):
    p = get_object_or_404(Proposal, pk=pk, org=get_org(request))
    if not can_decide_proposal(request, p):
        return Response({"error": "You don't have decision rights on this proposal."}, status=403)
    action = request.data.get("action")
    feedback = (request.data.get("feedback") or "").strip()
    if action == "approve":
        p.status = "approved"
        p.ceo_feedback = feedback
        p.save()
        engine.in_thread(engine.run_execution, p.id)
    elif action == "tweak":
        if not feedback:
            return Response({"error": "Tweak needs feedback."}, status=400)
        p.status = "revision"
        p.ceo_feedback = feedback
        p.save()
        engine.in_thread(engine.run_revision, p.id)
    elif action == "reject":
        p.status = "rejected"
        p.ceo_feedback = feedback
        p.save()
    else:
        return Response({"error": "action must be approve, tweak, or reject."}, status=400)
    return Response(proposal_dict(p))


@api_view(["POST"])
def artifact_decide(request, pk):
    a = get_object_or_404(Artifact, pk=pk, proposal__org=get_org(request))
    allowed = is_ceo(request)
    if not allowed:
        m = get_member(request.user)
        agent = a.agent or a.proposal.assigned_to
        if m and m.status == "active" and m.role == "head" and agent and agent.department == m.department:
            pol = ApprovalPolicy.objects.filter(org=a.proposal.org, department=m.department).first()
            allowed = bool(pol and pol.artifact_approval == "head")
    if not allowed:
        return Response({"error": "Deliverables need a human signature — yours isn't authorized for this department."}, status=403)
    action = request.data.get("action")
    feedback = (request.data.get("feedback") or "").strip()
    if action == "approve":
        a.status = "approved"
        a.ceo_feedback = feedback
        a.save()
        a.proposal.status = "done"
        a.proposal.save(update_fields=["status"])
        engine.in_thread(engine.deliver_artifact, a.id)
    elif action == "redo":
        a.status = "rejected"
        a.ceo_feedback = feedback
        a.save()
        a.proposal.status = "approved"
        a.proposal.ceo_feedback = feedback
        a.proposal.save()
        engine.in_thread(engine.run_execution, a.proposal_id)
    else:
        return Response({"error": "action must be approve or redo."}, status=400)
    return Response({"id": a.id, "status": a.status})


@api_view(["GET", "POST"])
def agent_chat(request, pk):
    agent = get_object_or_404(Agent, pk=pk, org=get_org(request))
    if agent.is_human:
        return Response({"error": f"{agent.name} is a real person — reach them outside HQ."}, status=400)
    if request.method == "POST":
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"error": "Message required."}, status=400)
        ChatMessage.objects.create(agent=agent, role="user", content=text)
        history = [
            {"role": m.role, "content": m.content}
            for m in agent.chat_messages.order_by("-created_at")[:30][::-1]
        ]
        reply = engine.call_llm(
            engine.agent_system(agent, "You are chatting 1:1 with the CEO on mobile. Short paragraphs."),
            history, 1200,
        )
        ChatMessage.objects.create(agent=agent, role="assistant", content=reply)
    msgs = agent.chat_messages.order_by("-created_at")[:50][::-1]
    return Response({
        "agent": agent_dict(agent),
        "messages": [{"role": m.role, "content": m.content} for m in msgs],
    })


@api_view(["GET"])
def me(request):
    m = get_member(request.user)
    return Response({
        "username": request.user.username,
        "role": m.role if m else None,
        "department": m.department if m else "",
        "status": m.status if m else None,
        "is_ceo": bool(m and m.role == "ceo" and m.status == "active"),
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """Create a user account only. Choosing/creating a company is a separate
    step (see found_company / join_company), so signup no longer requires
    picking an organization up front."""
    username = (request.data.get("username") or "").strip().lower()
    password = request.data.get("password") or ""
    display = (request.data.get("display_name") or "").strip()
    email = (request.data.get("email") or "").strip()
    if not username or len(password) < 8:
        return Response({"error": "Username and a password of 8+ characters required."}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({"error": "That username is taken."}, status=400)
    if email and User.objects.filter(email__iexact=email).exists():
        return Response({"error": "That email is already registered."}, status=400)
    user = User.objects.create_user(username=username, password=password, first_name=display, email=email)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "username": username, "status": "none"})


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset(request):
    """Email a password-reset link. Always returns ok so we never reveal
    whether an account exists."""
    ident = (request.data.get("identifier") or "").strip()
    user = None
    if ident:
        user = (User.objects.filter(email__iexact=ident).first()
                or User.objects.filter(username__iexact=ident).first())
    if user and user.email:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.FRONTEND_URL}/reset?uid={uid}&token={token}"
        send_mail(
            "Reset your OgaBoss password",
            f"Hi {user.first_name or user.username},\n\n"
            f"Click the link below to set a new password:\n{link}\n\n"
            "If you didn't request this, you can safely ignore this email.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
    return Response({"ok": True, "note": "If an account matches, a reset link is on its way."})


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """Validate the emailed token and set a new password."""
    uidb64 = request.data.get("uid") or ""
    token = request.data.get("token") or ""
    new_password = request.data.get("new_password") or ""
    if len(new_password) < 8:
        return Response({"error": "Password must be at least 8 characters."}, status=400)
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if not user or not default_token_generator.check_token(user, token):
        return Response({"error": "This reset link is invalid or has expired."}, status=400)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    Token.objects.filter(user=user).delete()  # invalidate old sessions
    new_token, _ = Token.objects.get_or_create(user=user)
    return Response({"ok": True, "token": new_token.key, "username": user.username})


@api_view(["POST"])
def password_change(request):
    """Change the password of the logged-in user."""
    current = request.data.get("current_password") or ""
    new_password = request.data.get("new_password") or ""
    if not request.user.check_password(current):
        return Response({"error": "Current password is incorrect."}, status=400)
    if len(new_password) < 8:
        return Response({"error": "New password must be at least 8 characters."}, status=400)
    request.user.set_password(new_password)
    request.user.save(update_fields=["password"])
    Token.objects.filter(user=request.user).delete()
    new_token, _ = Token.objects.get_or_create(user=request.user)
    return Response({"ok": True, "token": new_token.key})


def _member_display_name(user):
    return (user.first_name or "").strip() or user.username.title()


def _bootstrap_org(name, user_id):
    slug = slugify(name) or f"org-{user_id}"
    if Organization.objects.filter(slug=slug).exists():
        slug = f"{slug}-{user_id}"
    org = Organization.objects.create(name=name, slug=slug)
    Constitution.objects.create(org=org, content=f"# {name} — Constitution\n\nWrite your culture, policies, and direction here. Every agent reads this before acting.")
    Agent.objects.create(
        org=org, name="Alex", role="Chief of Staff", department="Office of the CEO",
        persona="World-class Chief of Staff. Protects the CEO's focus, drafts crisply, thinks in the ONE thing that moves the company this week.",
        mandate="Priorities, drafting, meeting prep", is_head=True, proactive=True, shape="circle",
    )
    return org


@api_view(["POST"])
def found_company(request):
    """Authenticated user creates their own company and becomes its CEO."""
    if get_member(request.user):
        return Response({"error": "You already belong to a company."}, status=400)
    name = (request.data.get("new_org_name") or "").strip()
    if not name:
        return Response({"error": "Company name required."}, status=400)
    org = _bootstrap_org(name, request.user.id)
    Member.objects.create(org=org, user=request.user, display_name=_member_display_name(request.user), role="ceo", status="active")
    return Response({"status": "active", "note": f"{name} is founded — you're the CEO. Build your team."})


@api_view(["POST"])
def join_company(request):
    """Authenticated user requests to join an existing company by its code."""
    if get_member(request.user):
        return Response({"error": "You already belong to a company."}, status=400)
    slug = (request.data.get("org_slug") or "").strip().lower()
    org = Organization.objects.filter(slug=slug).first() if slug else None
    if not org:
        return Response({"error": "No company found with that code."}, status=400)
    Member.objects.create(org=org, user=request.user, display_name=_member_display_name(request.user))
    return Response({"status": "pending", "note": "Request sent — the CEO will review your enrollment."})


@api_view(["GET"])
def members_list(request):
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    ms = get_org(request).members.select_related("user").order_by("status", "-created_at")
    return Response({"members": [
        {"id": m.id, "username": m.user.username, "display_name": m.display_name,
         "role": m.role, "department": m.department, "status": m.status}
        for m in ms
    ]})


@api_view(["POST"])
def member_update(request, pk):
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    m = get_object_or_404(Member, pk=pk, org=get_org(request))
    action = request.data.get("action")
    if action == "approve":
        m.role = request.data.get("role", "member")
        m.department = request.data.get("department", "")
        m.status = "active"
        m.save()
        if m.role == "head" and m.department:
            Agent.objects.update_or_create(
                org=m.org, user=m.user,
                defaults={
                    "name": m.display_name or m.user.username.title(),
                    "role": f"Head of {m.department}", "department": m.department,
                    "persona": "Human teammate — real person, never simulated.",
                    "mandate": "Human department head — decides proposals in this department.",
                    "is_head": True, "is_human": True, "shape": "triad", "active": True,
                },
            )
    elif action == "remove":
        m.status = "removed"
        m.save()
        Agent.objects.filter(org=m.org, user=m.user).update(active=False)
    else:
        return Response({"error": "action must be approve or remove."}, status=400)
    return Response({"id": m.id, "status": m.status, "role": m.role})


@api_view(["POST"])
def agent_create(request):
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    d = request.data
    if not d.get("name") or not d.get("role"):
        return Response({"error": "Name and role are required."}, status=400)
    a = Agent.objects.create(
        org=get_org(request), name=d["name"], role=d["role"],
        department=d.get("department", "General"), persona=d.get("persona", ""),
        mandate=d.get("mandate", ""), shape=d.get("shape", "circle"),
        is_head=bool(d.get("is_head")), proactive=bool(d.get("proactive")),
        reports_to_id=d.get("reports_to") or None,
    )
    return Response(agent_dict(a), status=201)


@api_view(["GET", "PUT", "DELETE"])
def agent_detail(request, pk):
    a = get_object_or_404(Agent, pk=pk, org=get_org(request))
    if request.method in ("PUT", "DELETE") and not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    if request.method == "PUT":
        d = request.data
        for f in ("name", "role", "department", "persona", "mandate", "shape"):
            if f in d:
                setattr(a, f, d[f])
        for f in ("is_head", "proactive", "active"):
            if f in d:
                setattr(a, f, bool(d[f]))
        if "reports_to" in d:
            a.reports_to_id = d["reports_to"] or None
        a.save()
    if request.method == "DELETE":
        a.active = False
        a.save(update_fields=["active"])
    return Response(agent_dict(a))


@api_view(["POST"])
def assist_agent(request):
    """AI drafts a full agent spec from a one-line brief, fitted to the company."""
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    org = get_org(request)
    brief = (request.data.get("brief") or "").strip()
    if not brief:
        return Response({"error": "Describe the role you want."}, status=400)
    shapes = ["circle", "diamond", "square", "chevron", "triad"]
    const = getattr(org, "constitution", None)
    const_text = const.content if const else ""
    system = (
        f"You design world-class team members for {org.name}. From the CEO's short brief, "
        "produce ONE agent spec that fits the company and complements the existing team. "
        "The persona must be vivid and specific — expertise, background, perspective, how they work. "
        f"shape is one of: {', '.join(shapes)}. "
        'Respond ONLY with JSON: {"name": str (a realistic first name), "role": str, '
        '"department": str, "mandate": str (one line), "persona": str (2-4 sentences), '
        '"shape": str, "is_head": bool, "proactive": bool}'
    )
    prompt = f"COMPANY CONSTITUTION:\n{const_text}\n\nEXISTING TEAM:\n{engine.roster_text(org)}\n\nCEO WANTS:\n{brief}"
    try:
        data = engine.parse_json(engine.call_llm(system, [{"role": "user", "content": prompt}], 800, org=org, purpose="assist_agent"))
    except Exception as e:
        return Response({"error": f"AI is unavailable right now ({e})."}, status=502)
    shape = data.get("shape") if data.get("shape") in shapes else "circle"
    return Response({
        "name": (data.get("name") or "").strip(),
        "role": (data.get("role") or "").strip(),
        "department": (data.get("department") or "").strip(),
        "mandate": (data.get("mandate") or "").strip(),
        "persona": (data.get("persona") or "").strip(),
        "shape": shape,
        "is_head": bool(data.get("is_head")),
        "proactive": bool(data.get("proactive")),
    })


@api_view(["POST"])
def assist_ideas(request):
    """AI proposes concrete directive ideas tailored to the company."""
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    org = get_org(request)
    seed = (request.data.get("seed") or "").strip()
    const = getattr(org, "constitution", None)
    const_text = const.content if const else ""
    system = (
        f"You are the strategist for {org.name}. Propose concrete, high-leverage next moves the CEO "
        "could direct the team to pursue. Each idea is one actionable directive, specific to this "
        "company, phrased as an instruction the team can run with immediately. "
        'Respond ONLY with JSON: {"ideas": [str, str, str, str]} (4 ideas, each under 25 words).'
    )
    focus = f"\n\nThe CEO is currently thinking about: {seed}" if seed else ""
    prompt = f"COMPANY CONSTITUTION:\n{const_text}\n{engine.memory_context(org)}{focus}\n\nGive four ideas."
    try:
        data = engine.parse_json(engine.call_llm(system, [{"role": "user", "content": prompt}], 700, model=settings.ENGINE_MODEL_FAST, org=org, purpose="assist_ideas"))
    except Exception as e:
        return Response({"error": f"AI is unavailable right now ({e})."}, status=502)
    ideas = [str(x).strip() for x in (data.get("ideas") or []) if str(x).strip()][:6]
    return Response({"ideas": ideas})


@api_view(["POST", "GET"])
def meetings(request):
    org = get_org(request)
    m = get_member(request.user)
    if request.method == "POST":
        if not (m and m.status == "active" and m.role in ("ceo", "head")):
            return Response({"error": "Only the CEO or department heads convene meetings."}, status=403)
        topic = (request.data.get("topic") or "").strip()
        ids = request.data.get("agent_ids") or []
        if not topic or not ids:
            return Response({"error": "Topic and at least one participant required."}, status=400)
        delib = Deliberation.objects.create(org=org, topic=topic)
        engine.in_thread(engine.run_custom_meeting, delib.id, topic, ids)
        return Response({"deliberation_id": delib.id, "status": "running"})
    ds = org.deliberations.order_by("-created_at")[:15]
    return Response({"meetings": [
        {"id": d.id, "topic": d.topic, "status": d.status, "created_at": d.created_at.isoformat(),
         "proposal_ids": [p.id for p in d.proposals.all()]}
        for d in ds
    ]})


PRICE_PER_MTOK = {"sonnet": (3.0, 15.0), "haiku": (1.0, 5.0), "opus": (15.0, 75.0)}


def est_cost(model, tin, tout):
    rates = (3.0, 15.0)
    for k, v in PRICE_PER_MTOK.items():
        if k in (model or ""):
            rates = v
    return (tin / 1e6) * rates[0] + (tout / 1e6) * rates[1]


@api_view(["GET"])
def usage(request):
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    org = get_org(request)
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    for a in org.agents.filter(is_human=False):
        rows = a.usage.filter(created_at__gte=month_start).values("model").annotate(
            tin=Sum("input_tokens"), tout=Sum("output_tokens"))
        tin = sum(r["tin"] or 0 for r in rows)
        tout = sum(r["tout"] or 0 for r in rows)
        cost = sum(est_cost(r["model"], r["tin"] or 0, r["tout"] or 0) for r in rows)
        if tin or tout:
            out.append({"agent": a.name, "department": a.department,
                        "input_tokens": tin, "output_tokens": tout, "est_usd": round(cost, 3)})
    overhead = org.usage.filter(agent__isnull=True, created_at__gte=month_start).values("model").annotate(
        tin=Sum("input_tokens"), tout=Sum("output_tokens"))
    o_tin = sum(r["tin"] or 0 for r in overhead)
    o_tout = sum(r["tout"] or 0 for r in overhead)
    o_cost = sum(est_cost(r["model"], r["tin"] or 0, r["tout"] or 0) for r in overhead)
    if o_tin or o_tout:
        out.append({"agent": "— Company overhead (routing, memory)", "department": "",
                    "input_tokens": o_tin, "output_tokens": o_tout, "est_usd": round(o_cost, 3)})
    out.sort(key=lambda r: -r["est_usd"])
    return Response({"month": month_start.strftime("%B %Y"), "rows": out,
                     "total_est_usd": round(sum(r["est_usd"] for r in out), 2)})


@api_view(["GET", "POST"])
def standing_orders(request):
    org = get_org(request)
    if request.method == "POST":
        if not is_ceo(request):
            return Response({"error": "CEO only."}, status=403)
        d = request.data
        agent = get_object_or_404(Agent, pk=d.get("agent"), org=org)
        if not d.get("instruction"):
            return Response({"error": "Instruction required."}, status=400)
        o = StandingOrder.objects.create(
            org=org, agent=agent, instruction=d["instruction"],
            cadence=d.get("cadence", "weekly"),
            weekday=d.get("weekday") if d.get("cadence", "weekly") == "weekly" else None,
        )
    return Response({"orders": [
        {"id": o.id, "agent": o.agent.name, "agent_id": o.agent_id, "instruction": o.instruction,
         "cadence": o.cadence, "weekday": o.weekday, "active": o.active}
        for o in org.standing_orders.filter(active=True).select_related("agent")
    ]})


@api_view(["DELETE"])
def standing_order_delete(request, pk):
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    o = get_object_or_404(StandingOrder, pk=pk, org=get_org(request))
    o.active = False
    o.save(update_fields=["active"])
    return Response({"id": o.id, "active": False})


@api_view(["GET", "POST"])
def policies(request):
    org = get_org(request)
    if request.method == "POST":
        if not is_ceo(request):
            return Response({"error": "CEO only."}, status=403)
        d = request.data
        pa = d.get("proposal_approval", "ceo")
        aa = d.get("artifact_approval", "ceo")
        if aa == "ai_manager":
            return Response({"error": "Deliverables must be signed by a human — the CEO or a human head."}, status=400)
        ApprovalPolicy.objects.update_or_create(
            org=org, department=d.get("department", ""),
            defaults={"proposal_approval": pa, "artifact_approval": aa},
        )
    depts = sorted(set(org.agents.filter(active=True).values_list("department", flat=True)))
    pols = {p.department: p for p in org.policies.all()}
    return Response({"policies": [
        {"department": dep,
         "proposal_approval": pols[dep].proposal_approval if dep in pols else "ceo",
         "artifact_approval": pols[dep].artifact_approval if dep in pols else "ceo",
         "has_human_head": org.members.filter(role="head", status="active", department=dep).exists(),
         "has_ai_managers": org.agents.filter(active=True, is_human=False, department=dep, reports__isnull=False).distinct().exists()}
        for dep in depts
    ]})


@api_view(["GET", "POST"])
def agent_capabilities(request, pk):
    agent = get_object_or_404(Agent, pk=pk, org=get_org(request))
    if request.method == "POST":
        if not is_ceo(request):
            return Response({"error": "CEO only."}, status=403)
        d = request.data
        if d.get("kind") not in dict(Capability.KINDS):
            return Response({"error": "Unknown capability kind."}, status=400)
        Capability.objects.create(
            agent=agent, kind=d["kind"], label=d.get("label", d["kind"]),
            url=d.get("url", ""), auth_header=d.get("auth_header", ""), notes=d.get("notes", ""),
        )
    return Response({"capabilities": [
        {"id": c.id, "kind": c.kind, "label": c.label, "url": c.url,
         "has_auth": bool(c.auth_header), "notes": c.notes}
        for c in agent.capabilities.all()
    ]})


@api_view(["DELETE"])
def capability_delete(request, pk):
    if not is_ceo(request):
        return Response({"error": "CEO only."}, status=403)
    c = get_object_or_404(Capability, pk=pk, agent__org=get_org(request))
    c.delete()
    return Response({"deleted": pk})


@api_view(["GET"])
def playbook(request):
    org = get_org(request)
    mem = getattr(org, "memory", None)
    return Response({"playbook": mem.playbook if mem else "", "updated_at": mem.updated_at.isoformat() if mem else None})


@api_view(["POST"])
def trigger_daily(request):
    org = get_org(request)
    engine.in_thread(engine.run_daily_cycle, org)
    return Response({"status": "running", "note": "Ideas will land on the desk shortly."})
