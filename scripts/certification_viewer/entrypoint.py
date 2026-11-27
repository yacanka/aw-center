"""Frozen Windows entry point. The downloaded copy carries its own source hint."""

import os
from pathlib import Path
import sys
from tkinter import TclError, Tk, messagebox

from compliance.executable_config import embedded_configuration
from scripts.certification_viewer.desktop import run_desktop


def configure_packaged_tk(bundle):
    for variable, directory, startup_script in (
        ('TCL_LIBRARY', '_tcl_data', 'init.tcl'),
        ('TK_LIBRARY', '_tk_data', 'tk.tcl'),
    ):
        library = bundle / directory
        if not (library / startup_script).is_file():
            raise FileNotFoundError(f'Packaged Tcl/Tk file is missing: {directory}/{startup_script} under {bundle}')
        os.environ[variable] = library.as_posix()


def main():
    if sys.argv[1:] == ['--check-tk']:
        try:
            configure_packaged_tk(Path(sys._MEIPASS).resolve())
            Tk().destroy()
        except (OSError, TclError) as exc:
            report = Path(sys.executable).with_name('tk-startup-error.txt')
            with report.open('x', encoding='utf-8') as stream:
                stream.write(f'{type(exc).__name__}: {exc}\n')
            raise SystemExit(1) from None
        return

    bundle = Path(sys._MEIPASS).resolve()
    configure_packaged_tk(bundle)
    try:
        path, trusted = embedded_configuration(Path(sys.executable))
    except (ValueError, OSError):
        messagebox.showerror('Certification Dashboard', 'Dosya yapılandırılamadı. Dashboard ana ekranından yeniden indirin.')
        return
    run_desktop(bundle / 'viewer', path, trusted)


if __name__ == '__main__':
    main()
