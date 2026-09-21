from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connections, transaction

from users.models import UserPreferences


SOURCE_DATABASE = "db_old"
TARGET_DATABASE = "default"
USER_COPY_FIELDS = (
    "email",
    "first_name",
    "last_name",
    "is_staff",
    "is_active",
    "is_superuser",
    "password",
    "last_login",
    "date_joined",
)


def get_legacy_preference_values(user_id):
    """Read only preference columns that exist in the legacy database.

    This intentionally uses schema introspection instead of an ORM query. An old
    database may predate one or more current UserPreferences migrations; selecting
    the current model in that case would fail because its newer columns are absent.
    """
    connection = connections[SOURCE_DATABASE]
    table_name = UserPreferences._meta.db_table
    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)
        if table_name not in table_names:
            return None
        legacy_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

    fields = [
        field
        for field in UserPreferences._meta.concrete_fields
        if not field.primary_key
        and not field.auto_created
        and field.column in legacy_columns
        and field.name not in {"created_at", "updated_at"}
    ]
    if not fields:
        return None

    quote = connection.ops.quote_name
    columns = ", ".join(quote(field.column) for field in fields)
    user_column = quote(UserPreferences._meta.pk.column)
    sql = f"SELECT {columns} FROM {quote(table_name)} WHERE {user_column} = %s"
    with connection.cursor() as cursor:
        cursor.execute(sql, [user_id])
        row = cursor.fetchone()
    if row is None:
        return None

    values = {}
    for field, value in zip(fields, row):
        if hasattr(field, "from_db_value"):
            value = field.from_db_value(value, None, connection)
        values[field.name] = value
    return values


def database_identity(connection):
    """Compare database targets without including credentials in diagnostics."""

    config = connection.settings_dict
    name = config["NAME"]
    if config.get("ENGINE") == "django.db.backends.sqlite3" and name != ":memory:":
        name = str(Path(name).expanduser().resolve())
    return tuple(config.get(key, "") for key in ("ENGINE", "HOST", "PORT")) + (name,)


class Command(BaseCommand):
    help = "Copy users and their available preferences from db_old to default"

    def add_arguments(self, parser):
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Also update the account fields of users that already exist in the target database.",
        )

    def handle(self, *args, **options):
        if SOURCE_DATABASE not in connections:
            raise CommandError("Configure DB_OLD_URL before copying users.")
        if database_identity(connections[SOURCE_DATABASE]) == database_identity(connections[TARGET_DATABASE]):
            raise CommandError("The legacy database must differ from the target database.")
        copied_count = 0
        updated_count = 0
        skipped_count = 0
        preference_count = 0

        users = User.objects.using(SOURCE_DATABASE).all().iterator()
        for legacy_user in users:
            defaults = {field: getattr(legacy_user, field) for field in USER_COPY_FIELDS}
            try:
                with transaction.atomic(using=TARGET_DATABASE):
                    target_user, created = User.objects.using(TARGET_DATABASE).get_or_create(
                        username=legacy_user.username,
                        defaults=defaults,
                    )
                    if created:
                        outcome = "copied"
                    elif options["update_existing"]:
                        for field, value in defaults.items():
                            setattr(target_user, field, value)
                        target_user.save(using=TARGET_DATABASE, update_fields=list(defaults))
                        outcome = "updated"
                    else:
                        outcome = "skipped"

                    preference_values = get_legacy_preference_values(legacy_user.pk)
                    if preference_values is not None:
                        UserPreferences.objects.using(TARGET_DATABASE).update_or_create(
                            user=target_user,
                            defaults=preference_values,
                        )
                copied_count += outcome == "copied"
                updated_count += outcome == "updated"
                skipped_count += outcome == "skipped"
                preference_count += preference_values is not None
            except IntegrityError:
                self.stderr.write(
                    self.style.WARNING(
                        "An account could not be copied due to a conflict; its changes were rolled back."
                    )
                )
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(f"{copied_count} users copied."))
        if options["update_existing"]:
            self.stdout.write(self.style.SUCCESS(f"{updated_count} existing users updated."))
        self.stdout.write(f"{skipped_count} existing or conflicting users skipped.")
        self.stdout.write(self.style.SUCCESS(f"{preference_count} user preferences copied."))