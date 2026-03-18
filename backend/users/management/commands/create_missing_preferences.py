from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import UserPreferences


class Command(BaseCommand):
    help = 'Create preferences for users who do not have them'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find users without preferences
        users_without_prefs = User.objects.filter(preferences__isnull=True)
        count = users_without_prefs.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('All users already have preferences!')
            )
            return
        
        self.stdout.write(f'Found {count} users without preferences')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes made'))
            for user in users_without_prefs[:10]:  # Show first 10
                self.stdout.write(f'  Would create preferences for: {user.username}')
            if count > 10:
                self.stdout.write(f'  ... and {count - 10} more')
            return
        
        # Create preferences
        created_count = 0
        for user in users_without_prefs:
            UserPreferences.objects.create(user=user)
            created_count += 1
            
            if created_count % 100 == 0:
                self.stdout.write(f'Created {created_count}/{count}...')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} preferences!')
        )