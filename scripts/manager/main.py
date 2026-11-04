"""Desktop entrypoint: opening a window has no installation prerequisites."""
from __future__ import annotations

import argparse
from functools import partial
import json
import os
from pathlib import Path
import sys


def _dpi_awareness():
    if os.name != 'nt':
        return
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def _startup_error():
    message = 'AW Center penceresi açılamadı. ZIP paketinin tamamını yerel bir klasöre çıkarıp AWCenterManager.exe dosyasını yeniden açın.'
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'AW Center', 0x10)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def _preferences_warning(error):
    message = error.message('save')
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'AW Center — form ayarları', 0x30)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def _smoke_metadata(root=None):
    """Record runtime appearance inputs without operator paths or content."""
    metadata = {'schema': 'awcenter.manager.ui-smoke', 'version': 1,
                'client_size': None, 'tk_version': None, 'theme': None,
                'scaling': None, 'default_font': None}
    if root is None:
        return metadata
    from tkinter import font, ttk
    default_font = font.nametofont('TkDefaultFont', root=root).actual()
    metadata.update(client_size={'width': root.winfo_width(), 'height': root.winfo_height()},
                    tk_version=str(root.tk.call('package', 'provide', 'Tk')),
                    theme=ttk.Style(root).theme_use(), scaling=float(root.tk.call('tk', 'scaling')),
                    default_font={'family': default_font['family'], 'size': default_font['size']})
    return metadata


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if values[:1] == ['--manager-command-gate']:
        from .worker import _restore_private_streams
        from scripts.launcher.child_bootstrap import main as command_main
        _restore_private_streams()
        if os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        return command_main(pass_stdin=True, gate_handle=int(values[1]), arguments=values[2:])
    if '--manager-worker' in values:
        from .worker import main as worker_main
        values.remove('--manager-worker')
        return worker_main(values)
    parser = argparse.ArgumentParser(description='AW Center Windows yönetim arayüzü')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--smoke-test', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(values)
    root = None
    callback_error_count = 0
    smoke_ready = False
    smoke_metadata = _smoke_metadata()
    try:
        _dpi_awareness()
        import tkinter as tk
        from .controller import ManagerController
        from .paths import default_source_root, startup_values
        from .view import ManagerWindow
        from .preferences import PreferencesError, load_preferences, preferences_home, save_preferences
        initial_values = {}
        preferences_directory = None
        preferences_failed = None
        if not args.smoke_test:
            try:
                preferences_directory = preferences_home()
                initial_values = load_preferences(preferences_directory)
            except PreferencesError as error:
                preferences_failed = error
        root = tk.Tk()
        controller = None
        # Keep callback exceptions visible without a disappearing console or raw
        # traceback that could contain operator data.
        def callback_error(*_):
            nonlocal callback_error_count
            callback_error_count += 1
            if args.smoke_test:
                return
            if controller is not None:
                controller.view.handle_event({'type': 'error', 'code': 'ui_failed',
                    'message': 'Arayüz işlemi tamamlanamadı.', 'remedy': 'İşlemi yeniden deneyin. Devam eden görev varsa önce Durdur düğmesini kullanın.'})
        root.report_callback_exception = callback_error
        initial_values = startup_values(initial_values, args.root)
        source_root = Path(initial_values.get('source_root') or default_source_root())
        controller = ManagerController(root, partial(ManagerWindow, initial_values=initial_values), source_root)
        if preferences_failed:
            controller.view.handle_event({'type': 'status',
                'message': preferences_failed.message('load')})
        if args.smoke_test:
            def complete_smoke():
                nonlocal smoke_metadata, smoke_ready
                try:
                    root.update_idletasks()
                    smoke_metadata = _smoke_metadata(root)
                    smoke_ready = bool(root.winfo_viewable())
                finally:
                    root.destroy()
            root.after(300, complete_smoke)
        root.mainloop()
        if not args.smoke_test:
            try:
                save_preferences(preferences_directory or preferences_home(), controller.view.form_values())
            except PreferencesError as error:
                _preferences_warning(error)
        if args.smoke_test:
            smoke_ready = smoke_ready and callback_error_count == 0
            args.smoke_test.write_text(json.dumps({**smoke_metadata, 'ready': smoke_ready,
                'callback_error_count': callback_error_count}), encoding='utf-8')
        return int(bool(args.smoke_test) and not smoke_ready)
    except Exception:
        if root is not None:
            root.destroy()
        if args.smoke_test:
            args.smoke_test.write_text(json.dumps({**_smoke_metadata(), 'ready': False,
                'callback_error_count': callback_error_count}), encoding='utf-8')
        else:
            _startup_error()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
