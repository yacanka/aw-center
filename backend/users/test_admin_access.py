"""Administration boundary and privilege escalation regressions."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AdminAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('a10001', password='Test-only-password!42')
        self.staff = User.objects.create_user('s10001', is_staff=True)
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label='auth'))
        self.user = User.objects.create_user('u10001', first_name='Example')
        self.group = Group.objects.create(name='Reviewers')
        self.client = APIClient()

    def test_non_staff_with_all_auth_permissions_is_denied(self):
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='auth'))
        self.client.force_authenticate(self.user)
        for path in ('/api/users/', '/api/users/groups/', '/api/users/permissions/'):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.patch(f'/api/users/{self.staff.pk}/', {'first_name': 'Changed'}).status_code, 403)

    def test_delegated_admin_can_read_and_edit_ordinary_profile(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/users/').status_code, 200)
        response = self.client.patch(f'/api/users/{self.user.pk}/', {'first_name': 'Updated'})
        self.assertEqual(response.status_code, 200)

    def test_delegated_admin_cannot_escalate_or_modify_administrators(self):
        self.client.force_authenticate(self.staff)
        for payload in ({'groups': [self.group.pk]}, {'user_permissions': []}, {'is_staff': True}, {'is_active': False}):
            response = self.client.patch(f'/api/users/{self.user.pk}/', payload, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.patch(f'/api/users/{self.admin.pk}/', {'password': 'Other-test-password!42'}).status_code, 400)
        self.assertEqual(self.client.delete(f'/api/users/{self.admin.pk}/').status_code, 400)
        self.assertEqual(self.client.post('/api/users/groups/', {'name': 'Elevated'}).status_code, 403)
        self.assertEqual(self.client.patch(f'/api/users/groups/{self.group.pk}/', {'name': 'Elevated'}).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/users/groups/{self.group.pk}/').status_code, 403)
        response = self.client.post('/api/users/invitations/', {'email': 'test@example.test', 'group_ids': [self.group.pk]}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_superuser_can_manage_access_but_cannot_lock_out_self(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'/api/users/{self.user.pk}/', {'is_staff': True, 'is_active': False, 'groups': [self.group.pk]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertFalse(self.user.is_active)
        for payload in ({'is_active': False}, {'is_staff': False}):
            self.assertEqual(self.client.patch(f'/api/users/{self.admin.pk}/', payload, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/users/{self.admin.pk}/').status_code, 400)

    def test_superuser_can_create_update_and_remove_shared_roles(self):
        self.client.force_authenticate(self.admin)
        permission = Permission.objects.get(codename='view_user')
        response = self.client.post('/api/users/groups/', {'name': 'User readers', 'permission_ids': [permission.pk]}, format='json')
        self.assertEqual(response.status_code, 201)
        role_id = response.data['id']
        response = self.client.patch(f'/api/users/groups/{role_id}/', {'permission_ids': []}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['permissions'], [])
        self.assertEqual(self.client.delete(f'/api/users/groups/{role_id}/').status_code, 204)

    def test_filters_are_applied_before_pagination(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/users/', {'search': 'Example', 'account': 'active'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.user.pk)
        self.assertEqual(self.client.get('/api/users/', {'search': 'Example', 'account': 'admin'}).data['count'], 0)

    def test_failed_password_validation_does_not_save_profile(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'/api/users/{self.user.pk}/', {'first_name': 'Changed', 'password': '123'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Example')

    def test_session_authenticated_mutation_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.patch(f'/api/users/{self.user.pk}/', {'first_name': 'Changed'}).status_code, 403)

    def test_staff_without_permissions_cannot_read_with_get_or_head(self):
        self.staff.user_permissions.clear()
        self.client.force_authenticate(self.staff)
        for path in ('/api/users/', '/api/users/groups/', '/api/users/permissions/'):
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.head(path).status_code, 403)
