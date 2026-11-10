"""Assessment must preserve authorization, source identity and saved data."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient
from ddf.models import DDF


class AssessmentSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('assessment-owner')
        self.user.user_permissions.add(*Permission.objects.filter(codename__in=['change_ddf', 'add_ddf']))
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.comments = [['1', 'Section', 'Synthetic review']]
        self.record = DDF.objects.create(created_by=self.user, comments=self.comments,
                                        comment_types=['Bilgi Görüşü'])

    def assess(self, comments=None):
        return self.client.post('/api/tools/ddf/assessment/', {
            'id': self.record.pk, 'comments': self.comments if comments is None else comments,
        }, format='json')

    @patch('ddf.views.request_assessment', return_value='Teknik Görüş')
    def test_change_permission_is_sufficient_and_preserves_source(self, upstream):
        self.user.user_permissions.remove(Permission.objects.get(codename='add_ddf'))
        response = self.assess()
        self.assertEqual(response.status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.comments, self.comments)
        self.assertEqual(self.record.comment_types, ['Teknik Görüş'])
        self.assertEqual(self.record.created_by_id, self.user.pk)

    @patch('ddf.views.request_assessment', return_value='Teknik Görüş')
    def test_add_only_cannot_modify_classification(self, upstream):
        self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(codename='add_ddf'))
        self.assertEqual(self.assess().status_code, 403)
        upstream.assert_not_called()
        self.record.refresh_from_db()
        self.assertEqual(self.record.comment_types, ['Bilgi Görüşü'])

    @patch('ddf.views.request_assessment')
    def test_unknown_and_empty_classes_preserve_existing_result(self, upstream):
        for answer in ('Unrecognized category', '', 'Teknik Görüş extra'):
            upstream.return_value = answer
            self.assertEqual(self.assess().status_code, 502)
            self.record.refresh_from_db()
            self.assertEqual(self.record.comment_types, ['Bilgi Görüşü'])

    @patch('ddf.views.request_assessment', return_value='Teknik Görüş')
    def test_different_source_is_rejected_before_transmission(self, upstream):
        response = self.assess([['1', 'Section', 'Different review']])
        self.assertEqual(response.status_code, 409)
        upstream.assert_not_called()
        self.record.refresh_from_db()
        self.assertEqual(self.record.comments, self.comments)
        self.assertEqual(self.record.comment_types, ['Bilgi Görüşü'])

    @patch('ddf.views.request_assessment')
    def test_source_changed_during_ai_request_is_not_overwritten(self, upstream):
        changed = [['1', 'Section', 'Updated review']]
        def respond(_prompt):
            DDF.objects.filter(pk=self.record.pk).update(comments=changed)
            return 'Teknik Görüş'
        upstream.side_effect = respond
        self.assertEqual(self.assess().status_code, 409)
        self.record.refresh_from_db()
        self.assertEqual(self.record.comments, changed)
        self.assertEqual(self.record.comment_types, ['Bilgi Görüşü'])

    @patch('ddf.views.request_assessment')
    def test_newer_classification_is_not_overwritten(self, upstream):
        def respond(_prompt):
            DDF.objects.filter(pk=self.record.pk).update(comment_types=['Editöryel Görüş'])
            return 'Teknik Görüş'
        upstream.side_effect = respond
        self.assertEqual(self.assess().status_code, 409)
        self.record.refresh_from_db()
        self.assertEqual(self.record.comment_types, ['Editöryel Görüş'])

    @patch('ddf.views.request_assessment')
    def test_all_four_classes_keep_the_existing_response_format(self, upstream):
        classes = ['Teknik Görüş', 'Bilgi Görüşü', 'Editöryel Görüş', 'Panel Ekleme/Çıkarma Görüşü']
        comments = [[str(index), 'Section', f'Review {index}'] for index in range(4)]
        self.record.comments = comments
        self.record.save(update_fields=['comments'])
        upstream.return_value = ',\n '.join(classes)
        response = self.assess(comments)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [f'[{name}] Review {index}' for index, name in enumerate(classes)])
        self.record.refresh_from_db()
        self.assertEqual(self.record.comment_types, classes)

    @patch('ddf.views.request_assessment')
    def test_deleted_record_is_not_recreated_by_late_response(self, upstream):
        record_id = self.record.pk
        def respond(_prompt):
            DDF.objects.filter(pk=record_id).delete()
            return 'Teknik Görüş'
        upstream.side_effect = respond
        self.assertEqual(self.assess().status_code, 409)
        self.assertFalse(DDF.objects.filter(pk=record_id).exists())
