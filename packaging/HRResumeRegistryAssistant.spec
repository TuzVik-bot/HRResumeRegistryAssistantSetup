# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all


hiddenimports = []
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastapi")
hiddenimports += collect_submodules("starlette")
hiddenimports += collect_submodules("numpy")
hiddenimports += collect_submodules("pandas")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "multipart",
    "numpy._core._exceptions",
    "numpy._core._multiarray_umath",
    "numpy._core.multiarray",
    "pandas._libs.tslibs.np_datetime",
    "pandas._libs.tslibs.nattype",
    "pandas._libs.tslibs.timedeltas",
]

numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
pandas_datas, pandas_binaries, pandas_hiddenimports = collect_all("pandas")
hiddenimports += numpy_hiddenimports
hiddenimports += pandas_hiddenimports

datas = [
    ("..\\templates", "templates"),
    ("..\\static", "static"),
]
datas += collect_data_files("fastapi")
datas += collect_data_files("starlette")
datas += numpy_datas
datas += pandas_datas

a = Analysis(
    ["..\\launcher.py"],
    pathex=[],
    binaries=numpy_binaries + pandas_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HRResumeRegistryAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
