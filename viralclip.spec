# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ViralClipMaker.

Build commands:
    Windows: pyinstaller viralclip.spec
    macOS:   pyinstaller viralclip.spec
    Linux:   pyinstaller viralclip.spec
"""

import os

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('core', 'core'),
        ('templates', 'templates'),
        ('static', 'static'),
        ('musicas_virais.json', '.'),
        ('requirements.txt', '.'),
    ],
    hiddenimports=[
        'flask',
        'fastapi',
        'uvicorn',
        'jinja2',
        'waitress',
        'faster_whisper',
        'librosa',
        'soundfile',
        'textblob',
        'numpy',
        'yt_dlp',
        'mediapipe',
        'PIL',
        'moviepy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ViralClipMaker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ViralClipMaker',
)
