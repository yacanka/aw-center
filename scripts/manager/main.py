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


def _startup_error():
    message = 'AW Center penceresi açılamadı. ZIP paketinin tamamını yerel bir klasöre çıkarıp AWCenterManager.exe dosyasını yeniden açın.'
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'AW Center', 0x10)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if '--manager-worker' in values:
        from .worker import main as worker_main
        values.remove('--manager-worker')
        return worker_main(values)
    parser = argparse.ArgumentParser(description='AW Center Windows yönetim arayüzü')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--smoke-test', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(values)
    root = None
    try:
        _dpi_awareness()
        import tkinter as tk
        from .controller import ManagerController
        from .paths import default_source_root
        from .view import ManagerWindow
        root = tk.Tk()
        controller = ManagerController(root, ManagerWindow, args.root or default_source_root())
        # Keep callback exceptions visible without a disappearing console or raw
        # traceback that could contain operator data.
        def callback_error(*_):
            controller.view.handle_event({'type': 'error', 'code': 'ui_failed',
                'message': 'Arayüz işlemi tamamlanamadı.', 'remedy': 'İşlemi yeniden deneyin. Devam eden görev varsa önce Durdur düğmesini kullanın.'})
        root.report_callback_exception = callback_error
        if args.smoke_test:
            def complete_smoke():
                root.update_idletasks()
                args.smoke_test.write_text(json.dumps({'ready': bool(root.winfo_viewable())}), encoding='utf-8')
                root.destroy()
            root.after(300, complete_smoke)
        root.mainloop()
        return 0
    except Exception:
        if root is not None:
            root.destroy()
        if args.smoke_test:
            args.smoke_test.write_text('{"ready": false}', encoding='utf-8')
        else:
            _startup_error()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
