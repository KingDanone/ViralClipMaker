# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ViralClipMaker.

Build:
    pyinstaller viralclip.spec

Notas:
- `collect_all('imageio-ffmpeg')` embute o binário do FFmpeg (sem ele o app
  não encontra FFmpeg na máquina do usuário final).
- `collect_all('mediapipe')` embute os modelos .tflite do face detection.
- scipy NÃO pode ser excluído: librosa depende dele.
"""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [
    ('core', 'core'),
    ('templates', 'templates'),
    ('static', 'static'),
    ('musicas_virais.json', '.'),
]
binaries = []
hiddenimports = [
    'fastapi',
    'uvicorn',
    'jinja2',
    'faster_whisper',
    'librosa',
    'soundfile',
    'textblob',
    'numpy',
    'yt_dlp',
    'PIL',
]

for pkg in ('imageio-ffmpeg', 'mediapipe'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
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
