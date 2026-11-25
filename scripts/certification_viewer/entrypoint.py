"""Frozen Windows entry point. The downloaded copy carries its own source hint."""

from pathlib import Path
import sys
from tkinter import messagebox

from compliance.executable_config import embedded_configuration
from scripts.certification_viewer.desktop import run_desktop


def main():
    try:
        path, trusted = embedded_configuration(Path(sys.executable))
    except (ValueError, OSError):
        messagebox.showerror('Certification Dashboard', 'Dosya yapılandırılamadı. Dashboard ana ekranından yeniden indirin.')
        return
    run_desktop(Path(sys._MEIPASS) / 'viewer', path, trusted)


if __name__ == '__main__':
    main()
