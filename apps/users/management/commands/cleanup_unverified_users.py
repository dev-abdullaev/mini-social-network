from django.core.management.base import BaseCommand

from apps.users.tasks import cleanup_unverified_users


class Command(BaseCommand):
    help = "Delete unverified users older than UNVERIFIED_USER_TTL_HOURS."

    def handle(self, *args, **options):
        deleted = cleanup_unverified_users()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} unverified user(s)."))
