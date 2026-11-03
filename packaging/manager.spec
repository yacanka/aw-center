# -*- mode: python ; coding: utf-8 -*-
"""Windows-only standard-library GUI; supporting Python/Tk stays in _internal."""
import os
from pathlib import Path

source = Path(os.environ['AWCENTER_MANAGER_SOURCE'])
launcher = source / 'scripts' / 'launcher'
data_names = (
    'installation_catalog.json',
    'installation_python.sha256',
    'installation_python_startup.sha256',
    'installation_verify_python.py',
    'child_bootstrap.py',
)
datas = [(str(launcher / name), 'scripts/launcher') for name in data_names]
# Launcher uses lazy imports for optional installation phases. Freeze only its
# own modules; application dependencies run under the verified managed Python.
hiddenimports = ['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox']
for package in ('launcher', 'manager'):
    hiddenimports.extend(
        f'scripts.{package}.{path.stem}'
        for path in (source / 'scripts' / package).glob('*.py')
        if path.name != '__init__.py'
    )
a = Analysis(
    [str(source / 'AWCenterManager.pyw')],
    pathex=[str(source)],
    binaries=[], datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='AWCenterManager', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=True,
    contents_directory='_internal',
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AWCenterManager')
