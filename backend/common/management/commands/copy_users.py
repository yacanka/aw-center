from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import IntegrityError

class Command(BaseCommand):
    help = 'Copy users from db1 to db2'

    def handle(self, *args, **options):
        users = User.objects.using('db_old').all()

        copied_count = 0
        skipped_count = 0

        for user in users:
            try:
                new_user, created = User.objects.using('default').get_or_create(
                    username=user.username,
                    defaults={
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'is_staff': user.is_staff,
                        'is_active': user.is_active,
                        'is_superuser': user.is_superuser,
                        'password': user.password,
                        'date_joined': user.date_joined,
                    }
                )

                if created:
                    copied_count += 1
                else:
                    skipped_count += 1

            except IntegrityError as e:
                print(f"Conflicts: {user.username} ({user.email}) - {e}")
                skipped_count += 1

        print(f"{copied_count} users copied.")
        print(f"{skipped_count} users already exist, skipped.")