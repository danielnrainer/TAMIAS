# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

# Collect all PyQt6 submodules to avoid missing plugin issues on some systems
hidden_pyqt6 = collect_submodules('PyQt6')
hidden_pil = collect_submodules('PIL')

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
    hiddenimports=hidden_pyqt6 + hidden_pil + [
        'PyQt6.QtCore', 
        'PyQt6.QtGui', 
        'PyQt6.QtWidgets',
        'core.image_processor',
        'core.crop_geometry',
        'core.overlay_renderer',
        'core.rod_image_reader',
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
        # Exclude unnecessary PyQt6 modules to reduce size
        'PyQt6.QtWebEngine',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtNetwork',
        'PyQt6.QtBluetooth',
        'PyQt6.QtDBus',
        'PyQt6.QtDesigner',
        'PyQt6.QtHelp',
        'PyQt6.QtLocation',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtNfc',
        'PyQt6.QtPositioning',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtQuickWidgets',
        'PyQt6.QtRemoteObjects',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtSql',  # SQL module - not needed
        'PyQt6.QtSvg',
        'PyQt6.QtSvgWidgets',
        'PyQt6.QtTest',
        'PyQt6.QtWebChannel',
        'PyQt6.QtWebSockets',
        'PyQt6.QtXml',
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
