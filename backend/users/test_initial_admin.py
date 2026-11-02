"""Initial operator provisioning never resets or promotes an existing account."""

from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class InitialAdminTests(TestCase):
    def provision(self, username='U12345', passwords=('InitialOperator!9z', 'InitialOperator!9z')):
        with mock.patch('users.management.commands.provision_initial_admin.sys.stdin.isatty', return_value=True), mock.patch('builtins.input', return_value=username), mock.patch('users.management.commands.provision_initial_admin.getpass.getpass', side_effect=passwords):
            call_command('provision_initial_admin', stdout=StringIO())

    def test_creates_admin_with_validated_hidden_password(self):
        self.provision()
        user = get_user_model().objects.get(username='U12345')
        self.assertTrue(user.is_superuser and user.is_active and user.is_staff)
        self.assertTrue(user.check_password('InitialOperator!9z'))

    def test_existing_admin_is_not_reset(self):
        user = get_user_model().objects.create_superuser(username='U12345', password='Preserved!456')
        before = user.password
        self.provision()
        user.refresh_from_db()
        self.assertEqual(user.password, before)

    def test_invalid_aw_username_or_weak_password_creates_nothing(self):
        for username, passwords in [('admin', ('InitialOperator!9z', 'InitialOperator!9z')), ('U12345', ('123', '123')), ('U12345', ('InitialOperator!9z', 'different'))]:
            with self.subTest(username=username), self.assertRaises(CommandError):
                self.provision(username, passwords)
        self.assertFalse(get_user_model().objects.exists())

    def test_existing_regular_user_is_never_promoted(self):
        user = get_user_model().objects.create_user(username='U12345', password='Preserved!456')
        with self.assertRaises(CommandError):
            self.provision()
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password('Preserved!456'))

    def test_redirected_password_input_is_refused(self):
        with mock.patch('users.management.commands.provision_initial_admin.sys.stdin.isatty', return_value=False), self.assertRaises(CommandError):
            call_command('provision_initial_admin', stdout=StringIO())
        self.assertFalse(get_user_model().objects.exists())
