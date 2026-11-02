"""Interactively create the first operator without resetting existing accounts."""

import getpass
import sys
import warnings

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from users.username_policy import validate_username_format


class Command(BaseCommand):
    help = 'Create the first administrator using validated, hidden terminal input.'

    def handle(self, *args, **options):
        user_model = get_user_model()
        if user_model.objects.filter(is_superuser=True, is_active=True).exists():
            self.stdout.write('An active administrator already exists; no account was changed.')
            return
        if not sys.stdin.isatty():
            raise CommandError('Administrator provisioning requires an interactive terminal.')
        username = input('Administrator username (one letter and five digits): ').strip()
        try:
            validate_username_format(username)
            if user_model.objects.filter(username__iexact=username).exists():
                raise CommandError('That account already exists; it will not be changed or promoted.')
            user = user_model(username=username, is_active=True, is_staff=True, is_superuser=True)
            # getpass may otherwise fall back to echoed input when a terminal is unavailable.
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                password = getpass.getpass('Administrator password: ')
                confirmation = getpass.getpass('Confirm administrator password: ')
            if password != confirmation:
                raise CommandError('Password confirmation did not match.')
            validate_password(password, user=user)
            with transaction.atomic():
                if user_model.objects.filter(is_superuser=True, is_active=True).exists():
                    self.stdout.write('An administrator was created concurrently; no account was changed.')
                    return
                user.set_password(password)
                user.save(force_insert=True)
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from None
        except getpass.GetPassWarning:
            raise CommandError('Hidden password input is unavailable in this terminal.') from None
        except IntegrityError:
            raise CommandError('The account already exists; no account was changed.') from None
        self.stdout.write(self.style.SUCCESS('Initial administrator created.'))
