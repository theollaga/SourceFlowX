# sourceflowx.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['gui_app.py'],
    pathex=['C:\\Users\\ROOT\\Desktop\\SourceFlowX\\sourceflowx'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'curl_cffi',
        'curl_cffi.requests',
        'amzpy',
        'bs4',
        'lxml',
        'pandas',
        'openai',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'config',
        'utils',
        'proxy_manager',
        'checkpoint_manager',
        'image_extractor',
        'scraper',
        'quality_checker',
        'price_adjuster',
        'shopify_exporter',
        'description_generator',
        'shopify_api',
        'gui_tabs',
        'gui_tabs.settings_tab',
        'gui_tabs.proxy_tab',
        'gui_tabs.run_tab',
        'gui_tabs.results_tab',
        'gui_tabs.description_tab',
        'gui_tabs.shopify_tab',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SourceFlowX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)


