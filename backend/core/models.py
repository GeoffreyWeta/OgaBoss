from django.conf import settings as dj_settings
from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Constitution(models.Model):
    """The company's culture, policies, direction — every agent reads this."""
    org = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="constitution")
    content = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class Agent(models.Model):
    SHAPES = [(s, s) for s in ["circle", "diamond", "square", "chevron", "triad"]]
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="agents")
    name = models.CharField(max_length=80)
    role = models.CharField(max_length=120)
    department = models.CharField(max_length=120)
    persona = models.TextField(help_text="Character, expertise, background — the agent's system prompt core")
    mandate = models.CharField(max_length=200, blank=True, default="")
    reports_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    is_head = models.BooleanField(default=False)
    proactive = models.BooleanField(default=False, help_text="Generates ideas in the daily cycle")
    shape = models.CharField(max_length=12, choices=SHAPES, default="circle")
    active = models.BooleanField(default=True)
    is_human = models.BooleanField(default=False, help_text="A real person's seat on the org chart (never simulated)")
    user = models.OneToOneField(dj_settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="agent_seat")

    def __str__(self):
        return f"{self.name} — {self.role}"


class Capability(models.Model):
    KINDS = [
        ("data_source", "Data source (read-only JSON endpoint)"),
        ("web_note", "Standing knowledge / notes"),
        ("web_research", "Live web research (agent can search the web)"),
        ("webhook", "Outbound action — POST approved deliverables to a URL"),
    ]
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="capabilities")
    kind = models.CharField(max_length=20, choices=KINDS)
    label = models.CharField(max_length=120)
    url = models.URLField(blank=True, default="")
    auth_header = models.CharField(max_length=300, blank=True, default="", help_text="e.g. Authorization: Bearer xxx")
    notes = models.TextField(blank=True, default="")


class Member(models.Model):
    """A real human's membership in the org: signup → CEO approval → role."""
    ROLES = [("ceo", "CEO"), ("head", "Department head"), ("member", "Member")]
    STATUS = [("pending", "Awaiting CEO approval"), ("active", "Active"), ("removed", "Removed")]
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")
    user = models.OneToOneField(dj_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    display_name = models.CharField(max_length=80, blank=True, default="")
    role = models.CharField(max_length=10, choices=ROLES, default="member")
    department = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role}/{self.status})"


class Directive(models.Model):
    """A CEO instruction that kicks off a deliberation."""
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="directives")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Deliberation(models.Model):
    STATUS = [("running", "running"), ("done", "done"), ("failed", "failed")]
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="deliberations")
    directive = models.ForeignKey(Directive, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliberations")
    topic = models.CharField(max_length=250)
    status = models.CharField(max_length=10, choices=STATUS, default="running")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class DelibMessage(models.Model):
    deliberation = models.ForeignKey(Deliberation, on_delete=models.CASCADE, related_name="messages")
    agent = models.ForeignKey(Agent, null=True, on_delete=models.SET_NULL)
    round = models.PositiveSmallIntegerField(default=1)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Proposal(models.Model):
    STATUS = [
        ("pending", "Awaiting CEO decision"),
        ("revision", "Sent back for revision"),
        ("approved", "Approved — executing"),
        ("artifact_pending", "Work submitted for sign-off"),
        ("done", "Done"),
        ("rejected", "Rejected"),
        ("failed", "Failed"),
    ]
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="proposals")
    deliberation = models.ForeignKey(Deliberation, null=True, on_delete=models.SET_NULL, related_name="proposals")
    title = models.CharField(max_length=200)
    summary = models.TextField()
    rationale = models.TextField(blank=True, default="", help_text="Provenance: who argued what, and why this won")
    proposed_by = models.ForeignKey(Agent, null=True, on_delete=models.SET_NULL, related_name="proposals_made")
    assigned_to = models.ForeignKey(Agent, null=True, on_delete=models.SET_NULL, related_name="proposals_assigned")
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    ceo_feedback = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class Artifact(models.Model):
    KINDS = [("html", "html"), ("markdown", "markdown"), ("text", "text")]
    STATUS = [("pending", "pending"), ("approved", "approved"), ("rejected", "rejected")]
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="artifacts")
    agent = models.ForeignKey(Agent, null=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=10, choices=KINDS, default="markdown")
    title = models.CharField(max_length=200)
    content = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    ceo_feedback = models.TextField(blank=True, default="")
    delivery = models.TextField(blank=True, default="", help_text="Result of outbound webhook delivery, if any")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class OrgMemory(models.Model):
    """Distilled organizational memory: what the CEO approves, rejects, and why.

    Auto-updated by the daily cycle; injected into every agent's context so the
    company learns the CEO's taste and compounds over time.
    """
    org = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="memory")
    playbook = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class ChatMessage(models.Model):
    """Direct 1:1 chat between the CEO and an agent (persistent memory)."""
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=10, choices=[("user", "user"), ("assistant", "assistant")])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class StandingOrder(models.Model):
    """Recurring mandate: work appears on the desk without being asked for."""
    CADENCE = [("daily", "Every day"), ("weekly", "Weekly")]
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="standing_orders")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="standing_orders")
    instruction = models.TextField(help_text="e.g. Produce one event flyer for this week's featured event")
    cadence = models.CharField(max_length=10, choices=CADENCE, default="weekly")
    weekday = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0=Mon … 6=Sun (weekly only)")
    active = models.BooleanField(default=True)
    last_run = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class UsageRecord(models.Model):
    """Payroll meter: token spend per call, attributable to an agent."""
    org = models.ForeignKey(Organization, null=True, on_delete=models.CASCADE, related_name="usage")
    agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.SET_NULL, related_name="usage")
    purpose = models.CharField(max_length=40, blank=True, default="")
    model = models.CharField(max_length=60, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class ProviderConfig(models.Model):
    """System-wide LLM provider selection — a single row.

    The app can think on Anthropic (Claude) or OpenAI (GPT). This is a live
    switch (persisted here so it survives restarts without a redeploy); only
    the designated operator may flip it (see settings.PROVIDER_ADMINS).
    """
    PROVIDERS = [("anthropic", "Anthropic (Claude)"), ("openai", "OpenAI (GPT)")]
    provider = models.CharField(max_length=20, choices=PROVIDERS, default="anthropic")
    # Keys entered through the UI. If blank, the engine falls back to the
    # corresponding environment variable. Never serialized back to the client.
    openai_key = models.TextField(blank=True, default="")
    anthropic_key = models.TextField(blank=True, default="")
    # Optional overrides for the OpenAI-compatible slot, so it can point at a
    # free provider (Groq, OpenRouter, Gemini compat, …). Blank = use defaults.
    openai_base_url = models.TextField(blank=True, default="")
    openai_model = models.CharField(max_length=120, blank=True, default="")
    updated_by = models.CharField(max_length=150, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"LLM provider: {self.provider}"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            default = getattr(dj_settings, "LLM_PROVIDER", "anthropic")
            if default not in dict(cls.PROVIDERS):
                default = "anthropic"
            obj = cls.objects.create(provider=default)
        return obj


class ApprovalPolicy(models.Model):
    """Per-department routing — simulate a real org's chain of command.

    proposal_approval: who greenlights internal work (AI manager allowed — saves tokens/attention).
    artifact_approval: who signs deliverables. HARD RULE enforced in views: anything that
    leaves the application is approved by a human (head or CEO) — never an AI.
    """
    PROPOSAL = [("ceo", "CEO"), ("head", "Human department head"), ("ai_manager", "AI manager (auto)")]
    ARTIFACT = [("ceo", "CEO"), ("head", "Human department head")]
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="policies")
    department = models.CharField(max_length=120)
    proposal_approval = models.CharField(max_length=12, choices=PROPOSAL, default="ceo")
    artifact_approval = models.CharField(max_length=12, choices=ARTIFACT, default="ceo")

    class Meta:
        unique_together = [("org", "department")]
