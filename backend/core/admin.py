from django.contrib import admin
from .models import (Organization, Constitution, Agent, Capability, Directive,
                     Deliberation, DelibMessage, Proposal, Artifact, ChatMessage)

for m in (Organization, Constitution, Agent, Capability, Directive,
          Deliberation, DelibMessage, Proposal, Artifact, ChatMessage):
    admin.site.register(m)
