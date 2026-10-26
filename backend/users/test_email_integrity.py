"""Email identity invariants must also hold outside serializer validation."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections, transaction
from django.test import TransactionTestCase

User = get_user_model()


class EmailDatabaseIntegrityTests(TransactionTestCase):
    def test_direct_and_bulk_writes_cannot_duplicate_identity(self):
        owner = User.objects.create_user('u91001', email='owner@example.invalid')
        other = User.objects.create_user('u91002', email='other@example.invalid')
        for write in (
            lambda: User.objects.create_user('u91003', email='OWNER@example.invalid'),
            lambda: User.objects.filter(pk=other.pk).update(email='OWNER@example.invalid'),
            lambda: User.objects.bulk_create([User(username='u91004', email='owner@example.invalid')]),
            lambda: User.objects.bulk_create([User(username='u91005', email='owner@example.invalid')], ignore_conflicts=True),
        ):
            with self.subTest(write=write), self.assertRaises(IntegrityError), transaction.atomic():
                write()
        other.refresh_from_db()
        self.assertEqual(other.email, 'other@example.invalid')
        self.assertEqual(User.objects.count(), 2)
        owner.delete()
        User.objects.filter(pk=other.pk).update(email='owner@example.invalid')

    def test_concurrent_creates_have_exactly_one_winner(self):
        barrier = Barrier(2)

        def create(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    User.objects.create_user(f'u9100{index}', email=(
                        'Race@example.invalid' if index == 1 else 'race@example.invalid'
                    ))
                    return 'created'
                except IntegrityError:
                    return 'conflict'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, (1, 2)))
        self.assertCountEqual(results, ['created', 'conflict'])
        self.assertEqual(User.objects.filter(email__iexact='race@example.invalid').count(), 1)

    def test_concurrent_updates_have_exactly_one_winner(self):
        users = [User.objects.create_user(f'u9500{index}', email=f'before{index}@example.invalid')
                 for index in (1, 2)]
        barrier = Barrier(2)

        def update(user_id):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    User.objects.filter(pk=user_id).update(email='target@example.invalid')
                    return 'updated'
                except IntegrityError:
                    return 'conflict'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, [user.pk for user in users]))
        self.assertCountEqual(results, ['updated', 'conflict'])
        self.assertEqual(User.objects.filter(email='target@example.invalid').count(), 1)
        self.assertEqual(User.objects.filter(email__startswith='before').count(), 1)

    def test_blank_emails_and_case_only_edits_remain_available(self):
        User.objects.create_user('u91001')
        User.objects.create_user('u91002')
        owner = User.objects.create_user('u91003', email='owner@example.invalid')
        User.objects.filter(pk=owner.pk).update(email='OWNER@example.invalid')
        self.assertEqual(User.objects.count(), 3)


class EmailGuardMigrationTests(TransactionTestCase):
    def test_migration_preserves_all_rows_and_reserves_legacy_collisions(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        from .models import EmailIdentity

        executor = MigrationExecutor(connection)
        executor.migrate([('users', '0001_initial')])
        try:
            first = User.objects.create_user('u92001', email='Legacy@example.invalid')
            second = User.objects.create_user('u92002', email='legacy@example.invalid')
            User.objects.create_user('u92003', email='unique@example.invalid')
            User.objects.create_user('u92004')
            User.objects.create_user('u92005')
            before = list(User.objects.order_by('pk').values())
        finally:
            MigrationExecutor(connection).migrate([('users', '0002_email_identity_guard')])
        self.assertEqual(list(User.objects.order_by('pk').values()), before)
        self.assertEqual(EmailIdentity.objects.get(email='legacy@example.invalid').owner_count, 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('u92006', email='LEGACY@example.invalid')
        first.first_name = 'Edited'
        first.email = first.email.upper()
        first.save()
        first.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('u92006', email='LEGACY@example.invalid')
        second.delete()
        User.objects.create_user('u92006', email='LEGACY@example.invalid')
        self.assertEqual(EmailIdentity.objects.get(email='legacy@example.invalid').owner_count, 1)


class EmailWriteSurfaceTests(TransactionTestCase):
    def test_validated_serializer_loses_race_as_email_error_without_partial_update(self):
        from rest_framework.exceptions import ValidationError
        from .serializers import UserProfileSerializer

        owner = User.objects.create_user('u93001', email='before@example.invalid')
        serializer = UserProfileSerializer(owner, data={
            'email': 'race@example.invalid', 'first_name': 'Not persisted',
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        User.objects.create_user('u93002', email='RACE@example.invalid')
        with self.assertRaises(ValidationError) as caught:
            serializer.save()
        self.assertIn('email', caught.exception.detail)
        owner.refresh_from_db()
        self.assertEqual(owner.email, 'before@example.invalid')
        self.assertEqual(owner.first_name, '')

    def test_administration_create_conflict_after_validation_is_a_field_error(self):
        import secrets
        from rest_framework.exceptions import ValidationError
        from .serializers import UserSerializer

        serializer = UserSerializer(data={
            'username': 'u93001', 'email': 'race@example.invalid',
            'password': secrets.token_urlsafe(24),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        User.objects.create_user('u93002', email='RACE@example.invalid')
        with self.assertRaises(ValidationError) as caught:
            serializer.save()
        self.assertIn('email', caught.exception.detail)
        self.assertFalse(User.objects.filter(username='u93001').exists())

    def test_invitation_racing_email_write_preserves_unused_invitation(self):
        import secrets
        from unittest.mock import patch
        from rest_framework.exceptions import ValidationError
        from . import invitation_service

        admin = User.objects.create_superuser('a93001')
        invitation, link = invitation_service.create_invitation(admin, 'race@example.invalid', [])
        create_user = invitation_service.create_invited_user

        def competing_create(invite, account):
            User.objects.create_user('u93002', email='RACE@example.invalid')
            return create_user(invite, account)

        # Inject a competing database write after the service's availability read.
        with patch.object(invitation_service, 'create_invited_user', side_effect=competing_create):
            with self.assertRaises(ValidationError) as caught:
                invitation_service.accept_invitation(link.split('#')[1], {
                    'username': 'u93001', 'first_name': '', 'last_name': '',
                    'password': secrets.token_urlsafe(24),
                })
        self.assertIn('email', caught.exception.detail)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)
        self.assertFalse(User.objects.filter(username='u93001').exists())

    def test_database_normalization_matches_validation_for_unicode_and_spaces(self):
        from django.core.exceptions import ValidationError
        from .email_policy import accounts_for_email, validate_email_identity

        for index, email in enumerate(('person@ä.example', 'person@Ä.example')):
            existing = accounts_for_email(email).exists()
            if existing:
                with self.assertRaises(ValidationError):
                    validate_email_identity(email)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    User.objects.create(username=f'u9400{index}', email=email)
            else:
                validate_email_identity(email)
                User.objects.create(username=f'u9400{index}', email=email)
        with self.assertRaises(ValidationError):
            validate_email_identity(' person@ä.example ')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('u94003', email=' person@ä.example ')

    def test_admin_late_conflict_returns_safe_feedback_and_rolls_back(self):
        from unittest.mock import patch
        from django.test import Client
        from .admin import CustomUserAdmin

        operator = User.objects.create_superuser('a96001')
        owner = User.objects.create_user('u96001', email='before@example.invalid')
        client = Client()
        client.force_login(operator)
        save_model = CustomUserAdmin.save_model

        def competing_save(model_admin, request, obj, form, change):
            User.objects.create_user('u96002', email='RACE@example.invalid')
            return save_model(model_admin, request, obj, form, change)

        url = f'/admin/auth/user/{owner.pk}/change/'
        with patch.object(CustomUserAdmin, 'save_model', competing_save):
            response = client.post(url, {
                'username': owner.username, 'email': 'race@example.invalid',
                'first_name': 'Not persisted', 'last_name': '', 'is_active': 'on',
                'date_joined_0': '2026-10-24', 'date_joined_1': '12:00:00',
                'preferences-TOTAL_FORMS': '0', 'preferences-INITIAL_FORMS': '0',
                'preferences-MIN_NUM_FORMS': '0', 'preferences-MAX_NUM_FORMS': '1',
                '_save': 'Save',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, url)
        owner.refresh_from_db()
        self.assertEqual(owner.first_name, '')
        self.assertEqual(owner.email, 'before@example.invalid')
        self.assertFalse(User.objects.filter(username='u96002').exists())
        self.assertTrue(any('email address is unavailable' in str(message)
                            for message in response.wsgi_request._messages))

    def test_sqlite_replace_policy_cannot_bypass_identity_guard(self):
        from django.db import connection
        if connection.vendor != 'sqlite':
            self.skipTest('INSERT OR REPLACE is SQLite-specific.')
        User.objects.create_user('u97001', email='owner@example.invalid')
        other = User.objects.create_user('u97002', email='other@example.invalid')
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE OR REPLACE auth_user SET email = %s WHERE id = %s',
                           ['OWNER@example.invalid', other.pk])
        other.refresh_from_db()
        self.assertEqual(other.email, 'other@example.invalid')

    def test_simultaneous_api_creates_return_created_and_validation_error(self):
        import secrets
        from unittest.mock import patch
        from rest_framework.test import APIClient
        from .serializers import UserSerializer

        admin = User.objects.create_superuser('a98001')
        barrier = Barrier(2)
        validate = UserSerializer.validate_email
        password = secrets.token_urlsafe(24)

        def synchronized_validation(serializer, value):
            result = validate(serializer, value)
            barrier.wait(timeout=10)
            return result

        def create(index):
            connections.close_all()
            try:
                client = APIClient()
                client.force_authenticate(admin)
                response = client.post('/api/users/', {
                    'username': f'u9800{index}', 'email': 'race@example.invalid',
                    'password': password,
                }, format='json')
                if response.status_code == 400:
                    self.assertIn('email', response.data['errors'])
                return response.status_code
            finally:
                connections.close_all()

        with patch.object(UserSerializer, 'validate_email', synchronized_validation):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(create, (1, 2)))
        self.assertCountEqual(results, [201, 400])
        self.assertEqual(User.objects.filter(email='race@example.invalid').count(), 1)

    def test_stale_administration_serializer_preserves_newer_credentials_and_email(self):
        from .serializers import UserSerializer

        stale = User.objects.create_user('u99001', email='before@example.invalid')
        serializer = UserSerializer(stale, data={'first_name': 'Updated'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        User.objects.filter(pk=stale.pk).update(password='!new-password-state', email='after@example.invalid')
        serializer.save()
        stale.refresh_from_db()
        self.assertEqual(stale.password, '!new-password-state')
        self.assertEqual(stale.email, 'after@example.invalid')
        self.assertEqual(stale.first_name, 'Updated')

    def test_stale_administration_serializer_cannot_resurrect_deleted_account(self):
        from django.http import Http404
        from .serializers import UserSerializer

        stale = User.objects.create_user('u99001')
        serializer = UserSerializer(stale, data={'first_name': 'Updated'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        User.objects.filter(pk=stale.pk).delete()
        with self.assertRaises(Http404):
            serializer.save()
        self.assertFalse(User.objects.filter(pk=stale.pk).exists())

    def test_sqlite_insert_replace_cannot_delete_existing_identity_owner(self):
        from django.db import connection
        if connection.vendor != 'sqlite':
            self.skipTest('INSERT OR REPLACE is SQLite-specific.')
        from .models import EmailIdentity
        owner = User.objects.bulk_create([User(username='u99001', email='owner@example.invalid')])[0]
        before = list(EmailIdentity.objects.order_by('email').values())
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('''INSERT OR REPLACE INTO auth_user
                (password, last_login, is_superuser, username, first_name, last_name,
                 email, is_staff, is_active, date_joined)
                SELECT password, last_login, is_superuser, username, first_name, last_name,
                       %s, is_staff, is_active, date_joined FROM auth_user WHERE id = %s''',
                           ['replacement@example.invalid', owner.pk])
        owner.refresh_from_db()
        self.assertEqual(owner.email, 'owner@example.invalid')
        self.assertEqual(list(EmailIdentity.objects.order_by('email').values()), before)

    def test_sqlite_update_replace_cannot_delete_another_identity_owner(self):
        from django.db import connection
        from .models import EmailIdentity
        if connection.vendor != 'sqlite':
            self.skipTest('UPDATE OR REPLACE is SQLite-specific.')
        first, second = User.objects.bulk_create([
            User(username='u99101', email='first@example.invalid'),
            User(username='u99102', email='second@example.invalid'),
        ])
        before = list(EmailIdentity.objects.order_by('email').values())
        for field, value in (('username', first.username), ('id', first.pk)):
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'UPDATE OR REPLACE auth_user SET {field} = %s WHERE id = %s',
                                   [value, second.pk])
            self.assertEqual(User.objects.count(), 2)
            self.assertEqual(list(EmailIdentity.objects.order_by('email').values()), before)

    def test_invitation_keeps_unicode_domain_identity_without_casefold_expansion(self):
        from .invitation_serializers import InvitationCreateSerializer
        from .invitation_service import accept_invitation, create_invitation
        from rest_framework.exceptions import ValidationError
        import secrets

        admin = User.objects.create_superuser('a99201')
        User.objects.create_user('u99201', email='person@strasse.invalid')
        serializer = InvitationCreateSerializer(data={'email': 'Person@straße.invalid'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        invitation, link = create_invitation(admin, serializer.validated_data['email'], [])
        self.assertEqual(invitation.email, 'person@straße.invalid')
        self.assertNotEqual(invitation.email, 'person@strasse.invalid')
        user = accept_invitation(link.split('#')[1], {
            'username': 'u99202', 'first_name': '', 'last_name': '',
            'password': secrets.token_urlsafe(24),
        })
        self.assertEqual(user.email, 'person@straße.invalid')
        with self.assertRaises(ValidationError):
            create_invitation(admin, 'PERSON@straße.invalid', [])
