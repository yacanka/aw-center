"""Create a local-only development login user."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


DEFAULT_USERNAME = "u10001"


class Command(BaseCommand):
    """Ensure a deterministic local development user exists."""

    help = "Create or update a local development superuser when DEBUG=True."

    def add_arguments(self, parser):
        """Register command-line arguments."""
        parser.add_argument("--username", default=DEFAULT_USERNAME)
        parser.add_argument("--password", default=None)
        parser.add_argument("--email", default="dev.user@example.local")

    def handle(self, *args, **options):
        """Create or update the local development user."""
        if not settings.DEBUG:
            raise CommandError("ensure_development_user can only run with DEBUG=True.")
        if not options["password"]:
            raise CommandError("Pass the local development password with --password.")

        user = self._ensure_user(options)
        self.stdout.write(self.style.SUCCESS(f"Development login ready: {user.username}"))

    def _ensure_user(self, options):
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=options["username"],
            defaults={
                "email": options["email"],
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        self._update_user(user, options, created)
        return user

    def _update_user(self, user, options, created):
        user.email = user.email or options["email"]
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(options["password"])
        user.save()
        action = "Created" if created else "Updated"
        self.stdout.write(f"{action} local development user '{user.username}'.")
