"""Interactively create the first operator without resetting existing accounts."""

import getpass
import sys
import warnings

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from users.initial_admin import (create_initial_admin, initial_admin_exists,
                                 validate_initial_admin_username)


class Command(BaseCommand):
    help = 'Create the first administrator using validated, hidden terminal input.'

    def handle(self, *args, **options):
        if initial_admin_exists():
            self.stdout.write('An active administrator already exists; no account was changed.')
            return
        if not sys.stdin.isatty():
            raise CommandError('Administrator provisioning requires an interactive terminal.')
        username = input('Administrator username (one letter and five digits): ').strip()
        try:
            validate_initial_admin_username(username)
            # getpass may otherwise fall back to echoed input when a terminal is unavailable.
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                password = getpass.getpass('Administrator password: ')
                confirmation = getpass.getpass('Confirm administrator password: ')
            if password != confirmation:
                raise CommandError('Password confirmation did not match.')
            if not create_initial_admin(username, password):
                self.stdout.write('An administrator was created concurrently; no account was changed.')
                return
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from None
        except getpass.GetPassWarning:
            raise CommandError('Hidden password input is unavailable in this terminal.') from None
        self.stdout.write(self.style.SUCCESS('Initial administrator created.'))
