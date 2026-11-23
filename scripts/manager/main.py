"""Desktop entrypoint: opening a window has no installation prerequisites."""
from __future__ import annotations

import argparse
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


def _startup_error(message='AW Center penceresi açılamadı. ZIP paketinin tamamını yerel bir klasöre çıkarıp AWCenterManager.exe dosyasını yeniden açın.'):
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'AW Center', 0x10)
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
    parser.add_argument('--settings', action='store_true', help='Uygulamayı başlatmadan ayarları aç')
    parser.add_argument('--smoke-test', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(values)
    root = None
    owner = None
    callback_error_count = 0
    smoke_ready = False
    smoke_metadata = _smoke_metadata()
    try:
        if not args.smoke_test:
            from .desktop import acquire_instance
            try:
                owner = acquire_instance(settings=args.settings)
            except OSError:
                _startup_error('AW Center açık olan Manager penceresine bağlanamadı. Görev çubuğundaki '
                               'Manager’ı kullanın veya uygulamayı aynı Windows hesabıyla ve aynı izinlerle açın.')
                return 1
            if owner is None:
                return 0
        _dpi_awareness()
        import tkinter as tk
        from .paths import worker_directory
        from .profile_window import ProfileWindow
        root = tk.Tk()
        def callback_error(*_):
            nonlocal callback_error_count
            callback_error_count += 1
            if not args.smoke_test:
                _startup_error('Arayüz işlemi tamamlanamadı.')
        root.report_callback_exception = callback_error
        window = ProfileWindow(root, worker_directory())
        root.protocol('WM_DELETE_WINDOW', window.close)
        if owner is not None:
            def poll_activation():
                action = owner.poll()
                if action:
                    window.activate(settings=action == 'settings')
                root.after(100, poll_activation)
            root.after(100, poll_activation)
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
    finally:
        if owner is not None:
            owner.close()


if __name__ == '__main__':
    raise SystemExit(main())
