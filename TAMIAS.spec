# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

# Importing qtpy exposes the active Qt backend. PyInstaller's Qt hooks collect
# the backend libraries and plugins required by the Qt modules TAMIAS uses.
import qtpy

qt_backend = qtpy.API_NAME
hidden_pil = collect_submodules('PIL')
# rodhypix ships a compiled ty6_cpp extension (.pyd) alongside the pure-Python backend;
# listing it in hiddenimports makes PyInstaller's graph analysis pick up the binary too
hidden_rodhypix = collect_submodules('rodhypix')

block_cipher = None


a = Analysis(
    ['TAMIAS.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include data files as (source, dest) tuples
        ('presets_defaults.json', '.'),
        ('settings_defaults.json', '.'),
        ('tamias.ico', '.'),
        ('tamias.png', '.'),
        # Include all module directories
        ('core', 'core'),
        ('gui', 'gui'),
        ('utils', 'utils'),
    ],
    hiddenimports=hidden_pil + hidden_rodhypix + [
        f'{qt_backend}.QtCore',
        f'{qt_backend}.QtGui',
        f'{qt_backend}.QtWidgets',
        'core.image_processor',
        'core.crop_geometry',
        'core.overlay_renderer',
        'rodhypix',
        'gui.app_state_manager',
        'gui.batch_processing_dialog',
        'gui.collapsible_box',
        'gui.crop_controller',
        'gui.crop_dialog',
        'gui.custom_widgets',
        'gui.measurement_interaction',
        'gui.theme_manager',
        'gui.ui_sections',
        'utils.app_settings_manager',
        'utils.imaging_mode_defaults',
        'utils.preset_manager',
        'utils.storage_paths',
        'numpy',
        'PIL',
        'PIL.Image',
        'PIL.ImageFile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary Qt modules to reduce size.
        *[
            f'{qt_backend}.{module}'
            for module in (
                'QtWebEngine', 'QtWebEngineWidgets', 'QtWebEngineCore',
                'QtNetwork', 'QtBluetooth', 'QtDBus', 'QtDesigner',
                'QtHelp', 'QtLocation', 'QtMultimedia', 'QtMultimediaWidgets',
                'QtNfc', 'QtPositioning', 'QtQml', 'QtQuick', 'QtQuickWidgets',
                'QtRemoteObjects', 'QtSensors', 'QtSerialPort', 'QtSql',
                'QtSvg', 'QtSvgWidgets', 'QtTest', 'QtWebChannel',
                'QtWebSockets', 'QtXml',
            )
        ],
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out SQL driver plugins that cause warnings
a.binaries = [x for x in a.binaries if not (
    'qsqlpsql' in x[0] or      # PostgreSQL driver
    'qsqlibase' in x[0] or     # Firebird driver
    'qsqlmimer' in x[0] or     # Mimer SQL driver
    'qsqloci' in x[0] or       # Oracle driver
    'qsqlodbc' in x[0] or      # ODBC driver (optional)
    'qsqltds' in x[0]          # TDS driver (optional)
)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TAMIAS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app (no console window)
    icon='tamias.ico',
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
