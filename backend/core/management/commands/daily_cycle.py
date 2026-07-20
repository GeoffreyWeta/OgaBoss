from django.core.management.base import BaseCommand
from core.engine import run_daily_cycle
from core.models import Organization

class Command(BaseCommand):
    help = "Run the daily proactive cycle for every organization"

    def handle(self, *args, **opts):
        for org in Organization.objects.all():
            self.stdout.write(f"Running daily cycle for {org.name}…")
            run_daily_cycle(org)
        self.stdout.write("Done.")
