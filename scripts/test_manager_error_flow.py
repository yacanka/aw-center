"""Correct an opening error in place, without navigating away from the flow."""
import unittest
from threading import Event
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.manager.view_model import ManagerState
from scripts import test_manager_view as fixtures


class ErrorFieldStateTests(unittest.TestCase):
    def test_selected_ca_failure_identifies_the_editable_ca_field(self):
        from scripts.launcher import certificates
        from scripts.manager import operations
        context = Mock()
        context.load_verify_locations.side_effect = FileNotFoundError()
        with patch.dict('os.environ', {}, clear=True), \
             patch.object(certificates, 'export_context', return_value=context):
            with self.assertRaises(certificates.PackageTrustError) as caught:
                with certificates.package_trust_environment({}, ca_file=Path('/selected-ca.pem')):
                    self.fail('Invalid CA must not reach installation')
        error = caught.exception
        events = []
        with patch.object(operations, '_dispatch', side_effect=error):
            operations.execute({'action': 'ensure'}, events.append, lambda: None, Event())
        failure = next(event for event in events if event['type'] == 'error')
        self.assertEqual(failure['code'], 'package_trust_extra_ca')
        self.assertEqual(failure['field'], 'ca_file')
        for stage in ('system', 'python', 'node', 'bundle', 'tool'):
            with self.subTest(stage=stage):
                self.assertFalse(getattr(certificates.PackageTrustError(stage), 'field', None))

    def test_inherited_node_ca_failure_is_not_attributed_to_the_selected_ca(self):
        from scripts.launcher import certificates
        context = Mock()
        context.load_verify_locations.side_effect = [None, FileNotFoundError()]
        with patch.dict('os.environ', {'NODE_EXTRA_CA_CERTS': '/inherited-ca.pem'}, clear=True), \
             patch.object(certificates, 'export_context', return_value=context):
            with self.assertRaises(certificates.PackageTrustError) as caught:
                with certificates.package_trust_environment({}, ca_file=Path('/selected-ca.pem')):
                    self.fail('Invalid inherited CA must not reach installation')
        self.assertFalse(getattr(caught.exception, 'field', None))

    def test_error_field_is_bounded_to_supported_fields_and_cleared_between_errors(self):
        state = ManagerState()
        state.handle_event({'type': 'error', 'field': 'backend_port'})
        self.assertEqual(state.error_field, 'backend_port')
        for field in (None, [], 'unknown', 'password'):
            with self.subTest(field=field):
                state.handle_event({'type': 'error', 'field': field})
                self.assertEqual(state.error_field, '')
        state.handle_event({'type': 'error', 'field': 'backend_port'})
        state.record_action('ensure', {})
        self.assertEqual(state.error_field, '')


class InlineErrorFlowTests(unittest.TestCase):
    setUp = fixtures.NativeWindowSmokeTests.setUp

    def test_missing_certificate_has_actionable_picker_and_preserves_other_fields(self):
        window = self.window
        window.variables['profile'].set('prod')
        window.variables['host'].set('192.0.2.10')
        window.variables['tls_key_file'].set('C:/private/server.key')
        window.update_tasks([{'id': 'server', 'action': 'ensure', 'profile': 'prod', 'status': 'failed',
                              'values': {'profile': 'prod'}}], selected_id='server')
        window.handle_event({'task_id': 'server', 'type': 'error', 'code': 'production_settings_required',
                             'message': 'TLS sertifikası eksik.', 'field': 'tls_cert_file'})
        self.root.update()
        self.assertEqual(window.error_remedy_var.get(), 'Sunucu sertifikanızın dosyasını seçin.')
        self.assertEqual(window.error_picker.cget('text'), 'Sertifikayı seç')
        with patch('scripts.manager.view.filedialog.askopenfilename', return_value='C:/private/server.pem'):
            window.error_picker.invoke()
        window.retry_button.invoke()
        self.assertEqual(self.actions[-1][1]['tls_cert_file'], 'C:/private/server.pem')
        self.assertEqual(self.actions[-1][1]['tls_key_file'], 'C:/private/server.key')
        self.assertEqual(self.actions[-1][1]['host'], '192.0.2.10')

    def test_unknown_error_support_copies_only_visible_operation_and_code(self):
        window = self.window
        window.update_tasks([
            {'id': 'server', 'action': 'ensure', 'profile': 'dev', 'status': 'failed', 'values': {}},
            {'id': 'other', 'action': 'doctor', 'profile': 'prod', 'status': 'done', 'values': {}},
        ], selected_id='other')
        window.handle_event({'task_id': 'server', 'type': 'error', 'code': 'operation_failed',
                             'message': 'Private C:/operator/file with token=fixture'})
        self.root.update()
        self.assertIn('Sistem yöneticinizden', window.error_remedy_var.get())
        with patch.object(self.root, 'clipboard_clear'), patch.object(self.root, 'clipboard_append') as copy:
            window.support_button.invoke()
        copy.assert_called_once_with('operation_failed\nAW Center açılırken işlem tamamlanamadı.')

    def test_offline_ca_error_reuses_the_picker_without_leaving_the_main_screen(self):
        window = self.window
        self.root.deiconify()
        window.variables['source_mode'].set('offline')
        window.update_tasks([
            {'id': 'server', 'action': 'ensure', 'profile': 'dev', 'status': 'failed', 'values': {}},
        ], selected_id='server')
        window.handle_event({'task_id': 'server', 'type': 'error', 'field': 'ca_file',
                             'message': 'Seçilen ek sertifikalar hazırlanamadı.'})
        self.root.update()
        self.assertTrue(window.error_picker.winfo_viewable())
        with patch('scripts.manager.view.filedialog.askopenfilename', return_value='C:/private/updated-ca.pem'):
            window.error_picker.invoke()
        window.retry_button.invoke()
        self.assertEqual(window.tabs.select(), str(window.run_tab))
        self.assertEqual(self.actions[-1][0], 'ensure')
        self.assertEqual(self.actions[-1][1]['ca_file'], 'C:/private/updated-ca.pem')

    def test_invalid_opening_field_is_corrected_and_retried_on_the_main_screen(self):
        window = self.window
        self.root.deiconify()
        window.variables['frontend_port'].set('invalid')
        window.action_buttons['start'].invoke()
        self.root.update()
        self.assertEqual(self.actions, [])
        self.assertEqual(window.tabs.select(), str(window.run_tab))
        self.assertFalse(window.advanced_var.get())
        self.assertTrue(window.error_entry.winfo_viewable())
        self.assertEqual(str(window.error_entry.cget('textvariable')), str(window.variables['frontend_port']))
        window.error_entry.delete(0, 'end')
        window.error_entry.insert(0, '15173')
        window.retry_button.invoke()
        self.assertEqual(self.actions[-1][0], 'ensure')
        self.assertEqual(self.actions[-1][1]['frontend_port'], '15173')

    def test_source_error_can_be_corrected_without_switching_tabs(self):
        window = self.window
        self.root.deiconify()
        window.update_tasks([
            {'id': 'server', 'action': 'ensure', 'profile': 'dev', 'status': 'failed', 'values': {}},
        ], selected_id='server')
        window.handle_event({'task_id': 'server', 'type': 'error', 'field': 'python_index_url',
                             'message': 'Paket adresi kullanılamıyor.', 'remedy': 'Paket adresini düzeltin.'})
        self.root.update()
        self.assertEqual(window.tabs.select(), str(window.run_tab))
        self.assertTrue(window.error_entry.winfo_viewable())
        self.assertEqual(window.error_remedy_var.get(), 'Paket adresini düzeltin.')
        window.error_entry.delete(0, 'end')
        window.error_entry.insert(0, 'https://packages.example/simple')
        window.retry_button.invoke()
        self.assertEqual(self.actions[-1][0], 'ensure')
        self.assertEqual(self.actions[-1][1]['python_index_url'], 'https://packages.example/simple')

    def test_background_error_does_not_navigate_or_reveal_unrelated_settings(self):
        window = self.window
        window.update_tasks([
            {'id': 'server', 'action': 'ensure', 'profile': 'dev', 'status': 'running', 'values': {}},
            {'id': 'prod', 'action': 'ensure', 'profile': 'prod', 'status': 'failed', 'values': {}},
        ], selected_id='server')
        window.handle_event({'task_id': 'prod', 'type': 'error', 'field': 'tls_cert_file',
                             'message': 'Sertifika eksik.'})
        self.root.update()
        self.assertEqual(window.tabs.select(), str(window.run_tab))
        self.assertFalse(window.advanced_var.get())
        self.assertFalse(window.error_frame.winfo_viewable())
