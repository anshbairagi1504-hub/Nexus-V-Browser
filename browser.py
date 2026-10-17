import sys
import os
import json
import tempfile
import py_compile
import subprocess
import ctypes
import ctypes.wintypes
from pathlib import Path
from urllib.parse import quote_plus
import re
from datetime import datetime
import requests

from PyQt5.QtCore import QUrl, QThread, pyqtSignal, QSettings, Qt, QAbstractNativeEventFilter
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTabWidget, QProgressBar, QComboBox,
    QMessageBox, QDialog, QListWidget, QListWidgetItem, QLabel,
    QCheckBox, QFormLayout, QDialogButtonBox, QShortcut, QMenu,
    QFileDialog, QSizeGrip, QInputDialog, QSystemTrayIcon, QStyle, QColorDialog, QGroupBox
)
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QDesktopServices


# ================ CONFIGURATION ================
APP_NAME = "Nexus-V Advanced Browser"
CURRENT_VERSION = "1.1.7"

GITHUB_REPO = "anshbairagi1504-hub/Nexus-V-Browser"
GITHUB_BRANCH = "main"

VERSION_URL = (
    f"https://raw.githubusercontent.com/"
    f"{GITHUB_REPO}/{GITHUB_BRANCH}/version.txt"
)
RAW_SCRIPT_URL = (
    f"https://raw.githubusercontent.com/"
    f"{GITHUB_REPO}/{GITHUB_BRANCH}/browser.py"
)

DATA_DIR = Path.home() / ".nexus_v_browser"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"
BOOKMARKS_FILE = DATA_DIR / "bookmarks.json"


def is_private_view(view):
    return bool(getattr(view, "_nexus_private", False))


class UpdateWorker(QThread):
    update_signal = pyqtSignal(str)

    def run(self):
        try:
            response = requests.get(VERSION_URL, timeout=12)
            response.raise_for_status()
            version = response.text.strip()

            if version:
                self.update_signal.emit(version)

        except Exception as error:
            self.update_signal.emit(f"ERROR: {error}")


class UpdateInstallWorker(QThread):
    finished_signal = pyqtSignal(bool, str)

    def run(self):
        temp_path = None

        try:
            response = requests.get(RAW_SCRIPT_URL, timeout=30, allow_redirects=True)
            if not response.url.startswith("https://"):
                raise ValueError("Update source must use HTTPS.")
            response.raise_for_status()
            new_code = response.text

            if (
                not new_code.strip()
                or "class NexusVBrowser" not in new_code
            ):
                raise ValueError(
                    "Downloaded file valid browser.py nahi lagti."
                )

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                encoding="utf-8",
                delete=False
            ) as file:
                file.write(new_code)
                temp_path = file.name

            py_compile.compile(temp_path, doraise=True)

            current_path = Path(__file__).resolve()
            backup_path = current_path.with_suffix(".py.bak")
            new_path = current_path.with_suffix(".py.new")

            new_path.write_text(new_code, encoding="utf-8")

            if backup_path.exists():
                backup_path.unlink()

            current_path.replace(backup_path)

            try:
                new_path.replace(current_path)
            except Exception:
                backup_path.replace(current_path)
                raise

            self.finished_signal.emit(
                True, str(current_path)
            )

        except Exception as error:
            self.finished_signal.emit(
                False, f"Update fail hua: {error}"
            )

        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


class SettingsDialog(QDialog):
    """Settings window for browser appearance, homepage, and shortcuts."""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nexus-V Settings")
        self.setMinimumSize(560, 520)
        self.resize(620, 590)
        self.settings = settings
        self.setObjectName("settingsDialog")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        heading = QLabel("Browser Settings")
        heading.setObjectName("settingsHeading")
        subtitle = QLabel("Personalize your Nexus-V experience")
        subtitle.setObjectName("settingsSubtitle")
        root.addWidget(heading)
        root.addWidget(subtitle)

        homepage_group = QGroupBox("Homepage & Search")
        homepage_form = QFormLayout(homepage_group)
        homepage_form.setContentsMargins(16, 18, 16, 14)
        homepage_form.setSpacing(10)
        self.home = QLineEdit(settings.value("home_url", "https://duckduckgo.com"))
        self.home.setPlaceholderText("https://example.com")
        self.search = QLineEdit(settings.value("search_url", "https://duckduckgo.com/?q={query}"))
        self.search.setPlaceholderText("Search URL must include {query}")
        homepage_form.addRow("Home page URL", self.home)
        homepage_form.addRow("Search URL", self.search)
        root.addWidget(homepage_group)

        appearance_group = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance_group)
        appearance_form.setContentsMargins(16, 18, 16, 14)
        appearance_form.setSpacing(10)
        self.dark = QCheckBox("Use dark mode (turn off for light mode)")
        self.dark.setChecked(settings.value("dark_mode", "true") == "true")
        self.shortcuts = QCheckBox("Show quick shortcuts on the homepage")
        self.shortcuts.setChecked(settings.value("shortcuts", "true") == "true")

        self.wallpaper = QLineEdit(str(settings.value("wallpaper", "preset:solid-midnight")))
        self.wallpaper.setReadOnly(True)
        self.wallpaper.setPlaceholderText("Choose a solid colour")
        self.wallpaper_presets = QComboBox()
        solid_presets = [
            ("Midnight · #111827", "preset:solid-midnight"),
            ("Charcoal · #20242C", "preset:solid-charcoal"),
            ("Deep blue · #163A70", "preset:solid-blue"),
            ("Ocean teal · #075E63", "preset:solid-teal"),
            ("Royal purple · #563D8F", "preset:solid-purple"),
            ("Emerald · #176B4D", "preset:solid-green"),
            ("Burgundy · #782D45", "preset:solid-burgundy"),
            ("Slate · #536273", "preset:solid-slate"),
            ("Soft grey · #E7EAF0", "preset:solid-grey"),
            ("White · #FFFFFF", "preset:solid-white"),
            ("Custom solid colour…", "__custom_color__"),
        ]
        for label, value in solid_presets:
            self.wallpaper_presets.addItem(label, value)
        current_wallpaper = self.wallpaper.text()
        found = self.wallpaper_presets.findData(current_wallpaper)
        if found >= 0:
            self.wallpaper_presets.setCurrentIndex(found)
        elif current_wallpaper.startswith("solid:#"):
            self.wallpaper_presets.addItem("Custom colour · " + current_wallpaper[6:], current_wallpaper)
            self.wallpaper_presets.setCurrentIndex(self.wallpaper_presets.count() - 1)
        else:
            self.wallpaper.setText("preset:solid-midnight")
            self.wallpaper_presets.setCurrentIndex(0)

        self.wallpaper_presets.currentIndexChanged.connect(self.wallpaper_preset_changed)
        self.wallpaper_row = QWidget()
        wallpaper_layout = QHBoxLayout(self.wallpaper_row)
        wallpaper_layout.setContentsMargins(0, 0, 0, 0)
        wallpaper_layout.setSpacing(8)
        wallpaper_layout.addWidget(self.wallpaper_presets, 1)
        self.color_preview = QLabel(" ")
        self.color_preview.setFixedSize(30, 30)
        self.color_preview.setObjectName("wallpaperColorPreview")
        wallpaper_layout.addWidget(self.color_preview)
        appearance_form.addRow("New tab background", self.wallpaper_row)
        root.addWidget(appearance_group)
        root.addWidget(self.dark)
        root.addWidget(self.shortcuts)

        privacy_group = QGroupBox("Privacy & Keyboard Shortcut")
        privacy_layout = QFormLayout(privacy_group)
        privacy_layout.setContentsMargins(16, 18, 16, 14)
        privacy_layout.setSpacing(10)
        self.hide_enabled = QCheckBox("Enable minimize-to-system-tray shortcut")
        self.hide_enabled.setChecked(settings.value("hide_enabled", "false") == "true")
        self.hide_key = QLineEdit(settings.value("hide_key", "Alt+X"))
        self.hide_key.setPlaceholderText("For example: Alt+X")
        privacy_layout.addRow(self.hide_enabled)
        privacy_layout.addRow("Hide shortcut key", self.hide_key)
        root.addWidget(privacy_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Save settings")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.setStyleSheet("""
            QDialog#settingsDialog { background: #171a22; color: #edf0f7; }
            QLabel#settingsHeading { font-size: 20pt; font-weight: 700; color: #ffffff; }
            QLabel#settingsSubtitle { color: #a9b2c5; font-size: 10pt; }
            QGroupBox { border: 1px solid #343b4b; border-radius: 12px; margin-top: 10px; padding-top: 10px; font-weight: 600; color: #cbd4ff; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QLineEdit, QComboBox { background: #222735; color: #f6f7fb; border: 1px solid #3b4355; border-radius: 7px; padding: 8px; min-height: 20px; }
            QLineEdit:focus, QComboBox:focus { border-color: #8290ff; }
            QCheckBox { spacing: 9px; padding: 3px; }
            QPushButton { background: #2b3243; color: #ffffff; border: 1px solid #424b61; border-radius: 8px; padding: 9px 14px; }
            QPushButton:hover { background: #3a4561; border-color: #8794ff; }
            QDialogButtonBox QPushButton { min-width: 95px; }
            QLabel#wallpaperColorPreview { border: 1px solid #7f8798; border-radius: 6px; }
        """)
        self.update_color_preview()

    def wallpaper_preset_changed(self, _index):
        value = self.wallpaper_presets.currentData()
        if value == "__custom_color__":
            from PyQt5.QtGui import QColor
            chosen = QColorDialog.getColor(parent=self, title="Choose a solid homepage colour")
            if chosen.isValid():
                value = "solid:" + chosen.name()
                existing = self.wallpaper_presets.findData(value)
                if existing < 0:
                    self.wallpaper_presets.insertItem(self.wallpaper_presets.count() - 1, "Custom colour · " + chosen.name(), value)
                    existing = self.wallpaper_presets.findData(value)
                self.wallpaper_presets.setCurrentIndex(existing)
            else:
                old = self.wallpaper_presets.findData(self.wallpaper.text())
                if old >= 0:
                    self.wallpaper_presets.blockSignals(True)
                    self.wallpaper_presets.setCurrentIndex(old)
                    self.wallpaper_presets.blockSignals(False)
                return
        self.wallpaper.setText(str(value))
        self.update_color_preview()

    def update_color_preview(self):
        value = self.wallpaper.text()
        colors = {
            "preset:solid-midnight": "#111827", "preset:solid-charcoal": "#20242C",
            "preset:solid-blue": "#163A70", "preset:solid-teal": "#075E63",
            "preset:solid-purple": "#563D8F", "preset:solid-green": "#176B4D",
            "preset:solid-burgundy": "#782D45", "preset:solid-slate": "#536273",
            "preset:solid-grey": "#E7EAF0", "preset:solid-white": "#FFFFFF",
        }
        color = value[6:] if value.startswith("solid:#") else colors.get(value, "#111827")
        self.color_preview.setStyleSheet(f"background-color: {color}; border: 1px solid #7f8798; border-radius: 6px;")

    def save_settings(self):
        home_url = self.home.text().strip() or "https://duckduckgo.com"
        search_url = self.search.text().strip() or "https://duckduckgo.com/?q={query}"
        if "{query}" not in search_url:
            search_url += ("&" if "?" in search_url else "?") + "q={query}"
        self.settings.setValue("home_url", home_url)
        self.settings.setValue("search_url", search_url)
        self.settings.setValue("dark_mode", "true" if self.dark.isChecked() else "false")
        self.settings.setValue("shortcuts", "true" if self.shortcuts.isChecked() else "false")
        self.settings.setValue("wallpaper", self.wallpaper.text().strip() or "preset:solid-midnight")
        self.settings.setValue("hide_enabled", "true" if self.hide_enabled.isChecked() else "false")
        self.settings.setValue("hide_key", self.hide_key.text().strip() or "Alt+X")



class WallpaperDialog(QDialog):
    """Small Customize dialog dedicated only to the new-tab wallpaper."""
    PRESETS = [
        ("Follow Light/Dark Theme", "preset:theme-default"),
        ("Midnight", "preset:solid-midnight"),
        ("Charcoal", "preset:solid-charcoal"),
        ("Deep blue", "preset:solid-blue"),
        ("Ocean teal", "preset:solid-teal"),
        ("Royal purple", "preset:solid-purple"),
        ("Emerald", "preset:solid-green"),
        ("Burgundy", "preset:solid-burgundy"),
        ("Slate", "preset:solid-slate"),
        ("Soft grey", "preset:solid-grey"),
        ("White", "preset:solid-white"),
        ("Choose a solid colour…", "__custom_color__"),
        ("Choose a wallpaper image/video…", "__custom_file__"),
    ]

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Customize · Wallpaper")
        self.setMinimumWidth(390)
        self.setStyleSheet("""
            QDialog { background: #171a22; color: #edf0f7; }
            QLabel { color: #edf0f7; }
            QComboBox { background: #252a38; color: #fff; border: 1px solid #424b61; border-radius: 8px; padding: 9px; }
            QPushButton { background: #30384b; color: white; border: 1px solid #485473; border-radius: 8px; padding: 9px 14px; }
            QPushButton:hover { background: #414d6b; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel("New tab wallpaper")
        title.setStyleSheet("font-size: 17pt; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Choose a solid colour or add your own wallpaper image/video."))
        self.combo = QComboBox()
        for label, value in self.PRESETS:
            self.combo.addItem(label, value)
        current = str(settings.value("wallpaper", "preset:theme-default"))
        if current == "preset:solid-midnight":
            # Keep the old default feeling theme-aware unless the user chose a different colour.
            current = "preset:theme-default"
        idx = self.combo.findData(current)
        if idx < 0 and current.startswith("solid:#"):
            self.combo.addItem("Custom colour · " + current[6:], current)
            idx = self.combo.count() - 1
        self.combo.setCurrentIndex(max(idx, 0))
        self.combo.currentIndexChanged.connect(self._choose_custom_colour)
        layout.addWidget(self.combo)
        row = QHBoxLayout()
        save = QPushButton("Apply wallpaper")
        cancel = QPushButton("Cancel")
        save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)

    def _choose_custom_colour(self, _index):
        selected = self.combo.currentData()
        if selected == "__custom_color__":
            color = QColorDialog.getColor(parent=self, title="Choose a solid wallpaper colour")
            if color.isValid():
                value = "solid:" + color.name()
                idx = self.combo.findData(value)
                if idx < 0:
                    self.combo.insertItem(self.combo.count() - 1, "Custom colour · " + color.name(), value)
                    idx = self.combo.findData(value)
                self.combo.setCurrentIndex(idx)
            else:
                old = self.combo.findData(str(self.settings.value("wallpaper", "preset:theme-default")))
                self.combo.setCurrentIndex(max(old, 0))
        elif selected == "__custom_file__":
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose wallpaper image or video", "",
                "Wallpaper files (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.mp4 *.webm *.m4v);;Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;Videos (*.mp4 *.webm *.m4v)"
            )
            if path:
                idx = self.combo.findData(path)
                if idx < 0:
                    self.combo.insertItem(self.combo.count() - 1, "Custom file · " + Path(path).name, path)
                    idx = self.combo.findData(path)
                self.combo.setCurrentIndex(idx)
            else:
                old = self.combo.findData(str(self.settings.value("wallpaper", "preset:theme-default")))
                self.combo.setCurrentIndex(max(old, 0))

    def selected_wallpaper(self):
        value = self.combo.currentData()
        return "preset:theme-default" if value in ("__custom_color__", "__custom_file__") else str(value)


class GlobalHideHotkeyFilter(QAbstractNativeEventFilter):
    """Receives a registered Windows hotkey even while the browser is hidden."""
    WM_HOTKEY = 0x0312
    HOTKEY_ID = 0x4E5658

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                    self.callback()
                    return True, 0
            except (TypeError, ValueError, OSError):
                pass
        return False, 0


class NexusVBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("nexus_logo.png"))
        # Frameless shell lets the browser controls sit beside the tab strip.
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("Nexus-V")

        self.settings = QSettings("NexusV", "AdvancedBrowser")
        self.resize(1320, 900)
        self.setMinimumSize(900, 600)

        self.bookmarks = self.load_bookmarks()
        self.history = self.load_history()
        self.private_profiles = []
        self._update_silent = False
        self._drag_pos = None
        self._resize_edges = Qt.Edges()
        self._resize_origin = None
        self._resize_geometry = None
        self._edge_margin = 7
        self._size_grip = QSizeGrip(self)
        self._size_grip.resize(16, 16)
        self._size_grip.raise_()

        central = QWidget()
        self.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Minimal title strip: no permanent logo/version text; About is in ⋮.
        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(8, 3, 5, 3)
        title_layout.setSpacing(4)
        title_layout.addStretch(1)
        self.main_layout.addWidget(self.title_bar)

        self.top_bar = QWidget()
        bar = QHBoxLayout(self.top_bar)
        bar.setContentsMargins(10, 9, 10, 9)
        bar.setSpacing(7)

        self.back_btn = self.make_button("←", "Go back")
        self.back_btn.clicked.connect(self.go_back)
        bar.addWidget(self.back_btn)

        self.forward_btn = self.make_button(
            "→", "Go forward"
        )
        self.forward_btn.clicked.connect(self.go_forward)
        bar.addWidget(self.forward_btn)

        self.reload_btn = self.make_button(
            "⟳", "Reload page"
        )
        self.reload_btn.clicked.connect(self.reload_page)
        bar.addWidget(self.reload_btn)

        self.home_btn = self.make_button("⌂", "Home")
        self.home_btn.clicked.connect(self.go_home)
        bar.addWidget(self.home_btn)

        self.add_tab_btn = self.make_button(
            "+", "New tab (Ctrl+T)"
        )
        self.add_tab_btn.clicked.connect(
            self.add_new_blank_tab
        )
        bar.addWidget(self.add_tab_btn)

        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("urlBar")
        self.url_bar.setPlaceholderText("Type to search and your URL")
        self.url_bar.returnPressed.connect(
            self.navigate_to_url
        )
        bar.addWidget(self.url_bar, 1)
        self.overflow_btn = self.make_button("⋮", "More options")
        self.overflow_btn.setObjectName("overflowButton")
        self.overflow_btn.clicked.connect(self.show_overflow_menu)
        bar.addWidget(self.overflow_btn)

        # History, bookmarks, downloads, settings and update live in ⋮ menu.
        self.update_btn = self.make_button("Update", "Check GitHub for updates")
        self.update_btn.setVisible(False)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("browserTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)

        # Keep the real tab strip above the navigation/search toolbar,
        # with a dedicated + button immediately after the tabs.
        self.tab_row = QWidget()
        self.tab_row.setObjectName("tabRow")
        tab_row_layout = QHBoxLayout(self.tab_row)
        tab_row_layout.setContentsMargins(8, 3, 8, 3)
        tab_row_layout.setSpacing(6)
        self.tab_strip = self.tabs.tabBar()
        self.tab_strip.setParent(self.tab_row)
        tab_row_layout.addWidget(self.tab_strip, 1)
        self.tab_plus_btn = self.make_button("+", "Open a new tab")
        self.tab_plus_btn.setObjectName("tabPlusButton")
        self.tab_plus_btn.setFixedSize(30, 28)
        self.tab_plus_btn.clicked.connect(self.add_new_blank_tab)
        tab_row_layout.addWidget(self.tab_plus_btn)
        self.tab_overflow_btn = self.make_button("▾", "Show tabs after the first 20")
        self.tab_overflow_btn.setFixedSize(30, 28)
        self.tab_overflow_btn.setVisible(False)
        self.tab_overflow_btn.clicked.connect(self.show_tab_overflow_menu)
        tab_row_layout.addWidget(self.tab_overflow_btn)
        self.min_btn = self.make_button("—", "Minimize")
        self.min_btn.clicked.connect(self.showMinimized)
        tab_row_layout.addWidget(self.min_btn)
        self.max_btn = self.make_button("□", "Maximize / restore")
        self.max_btn.clicked.connect(self.toggle_maximize)
        tab_row_layout.addWidget(self.max_btn)
        self.close_btn = self.make_button("×", "Close browser")
        self.close_btn.setObjectName("windowCloseButton")
        self.close_btn.clicked.connect(self.close)
        tab_row_layout.addWidget(self.close_btn)

        self.main_layout.addWidget(self.tab_row)
        self.main_layout.addWidget(self.top_bar)
        self.main_layout.addWidget(self.tabs, 1)

        # Browser customization lives at the bottom-left, away from window controls.
        self.bottom_bar = QWidget()
        self.bottom_bar.setObjectName("bottomBar")
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(12, 6, 12, 8)
        bottom_layout.setSpacing(8)
        self.customize_btn = self.make_button("🎨  Customize wallpaper", "Change only the new-tab wallpaper")
        self.customize_btn.setObjectName("customizeButton")
        self.customize_btn.setMinimumHeight(34)
        self.customize_btn.clicked.connect(self.open_wallpaper_customizer)
        bottom_layout.addWidget(self.customize_btn)
        bottom_layout.addStretch(1)
        self.main_layout.addWidget(self.bottom_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.main_layout.addWidget(self.progress_bar)

        self.apply_theme()
        self.add_new_tab(QUrl("about:blank"), "New tab")
        self.setup_shortcuts()
        self.setup_tray_and_hide_shortcut()
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().currentChanged.connect(lambda _index: self.refresh_tab_overflow())
        QWebEngineProfile.defaultProfile().downloadRequested.connect(self.handle_download)
        if self.settings.value("auto_update", "true") == "true":
            self.check_for_updates(silent=True)

    def show_overflow_menu(self):
        menu = QMenu(self)
        menu.addAction("History", self.show_history)
        menu.addAction("Bookmarks", self.show_bookmarks)
        menu.addAction("Bookmark this page", self.add_current_bookmark)
        menu.addAction("Downloads", self.show_downloads)
        menu.addSeparator()
        menu.addAction("Incognito tab", self.open_private_tab)
        menu.addAction("Shortcuts · Add / Edit / Remove…", self.manage_home_shortcuts)
        menu.addAction("Settings", self.open_settings)

        dark_now = self.settings.value("dark_mode", "true") == "true"
        theme_action = menu.addAction("Switch to Light Mode" if dark_now else "Switch to Dark Mode")
        theme_action.triggered.connect(self.toggle_theme)

        menu.addSeparator()
        auto_update_action = menu.addAction("Automatic update checks")
        auto_update_action.setCheckable(True)
        auto_update_action.setChecked(self.settings.value("auto_update", "true") == "true")
        auto_update_action.toggled.connect(self.set_auto_update)
        menu.addAction("Check for updates now", self.check_for_updates)
        menu.addAction("About", self.show_about)
        menu.exec_(self.overflow_btn.mapToGlobal(self.overflow_btn.rect().bottomLeft()))

    def set_auto_update(self, enabled):
        self.settings.setValue("auto_update", "true" if enabled else "false")
        QMessageBox.information(
            self,
            "Automatic Updates",
            "Automatic update checks are now ON." if enabled else
            "Automatic update checks are now OFF. You can still use ⋮ → Check for updates now."
        )

    def show_about(self):
        QMessageBox.about(
            self, "About Nexus-V",
            f"<h3>{APP_NAME}</h3><p>Version: {CURRENT_VERSION}</p>"
            "<p>A PyQt5-based web browser.</p>"
        )

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("□")
        else:
            self.showMaximized()
            self.max_btn.setText("❐")

    def _edges_at(self, pos):
        edges = Qt.Edges()
        if pos.x() <= self._edge_margin:
            edges |= Qt.LeftEdge
        elif pos.x() >= self.width() - self._edge_margin:
            edges |= Qt.RightEdge
        if pos.y() <= self._edge_margin:
            edges |= Qt.TopEdge
        elif pos.y() >= self.height() - self._edge_margin:
            edges |= Qt.BottomEdge
        return edges

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.isMaximized():
            edges = self._edges_at(event.pos())
            if edges:
                self._resize_edges = edges
                self._resize_origin = event.globalPos()
                self._resize_geometry = self.geometry()
                event.accept()
                return
            if event.pos().y() <= self.title_bar.height():
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edges and event.buttons() & Qt.LeftButton and self._resize_geometry is not None:
            delta = event.globalPos() - self._resize_origin
            rect = self._resize_geometry
            left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
            if self._resize_edges & Qt.LeftEdge:
                left = min(left + delta.x(), right - self.minimumWidth())
            if self._resize_edges & Qt.RightEdge:
                right = max(right + delta.x(), left + self.minimumWidth())
            if self._resize_edges & Qt.TopEdge:
                top = min(top + delta.y(), bottom - self.minimumHeight())
            if self._resize_edges & Qt.BottomEdge:
                bottom = max(bottom + delta.y(), top + self.minimumHeight())
            self.setGeometry(left, top, right - left + 1, bottom - top + 1)
            event.accept()
            return
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton and not self.isMaximized():
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
            return
        if not self.isMaximized():
            edges = self._edges_at(event.pos())
            cursors = {
                Qt.LeftEdge | Qt.TopEdge: Qt.SizeFDiagCursor,
                Qt.RightEdge | Qt.BottomEdge: Qt.SizeFDiagCursor,
                Qt.RightEdge | Qt.TopEdge: Qt.SizeBDiagCursor,
                Qt.LeftEdge | Qt.BottomEdge: Qt.SizeBDiagCursor,
                Qt.LeftEdge: Qt.SizeHorCursor,
                Qt.RightEdge: Qt.SizeHorCursor,
                Qt.TopEdge: Qt.SizeVerCursor,
                Qt.BottomEdge: Qt.SizeVerCursor,
            }
            self.setCursor(cursors.get(edges, Qt.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edges = Qt.Edges()
        self._resize_origin = None
        self._resize_geometry = None
        super().mouseReleaseEvent(event)

    def load_bookmarks(self):
        try:
            if BOOKMARKS_FILE.exists():
                data = json.loads(BOOKMARKS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict) and item.get("url")]
        except (OSError, json.JSONDecodeError) as error:
            print("Bookmark load error:", error)
        return []

    def save_bookmarks(self):
        try:
            BOOKMARKS_FILE.write_text(
                json.dumps(self.bookmarks, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as error:
            QMessageBox.warning(self, "Bookmarks", f"Could not save bookmarks: {error}")

    def show_bookmarks(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Bookmarks")
        dialog.resize(680, 440)
        layout = QVBoxLayout(dialog)
        listing = QListWidget()

        def refresh():
            listing.clear()
            for item in self.bookmarks:
                row = QListWidgetItem(f"{item.get('title', item['url'])}\n{item['url']}")
                row.setData(Qt.UserRole, item.get("url", ""))
                listing.addItem(row)

        def open_selected():
            item = listing.currentItem()
            if item and item.data(Qt.UserRole):
                view = self.current_view()
                if view:
                    view.setUrl(QUrl(item.data(Qt.UserRole)))
                dialog.accept()

        def remove_selected():
            item = listing.currentItem()
            if not item:
                return
            url = item.data(Qt.UserRole)
            self.bookmarks = [b for b in self.bookmarks if b.get("url") != url]
            self.save_bookmarks()
            refresh()

        layout.addWidget(listing)
        buttons = QHBoxLayout()
        open_btn = QPushButton("Open")
        remove_btn = QPushButton("Remove")
        close_btn = QPushButton("Close")
        open_btn.clicked.connect(open_selected)
        remove_btn.clicked.connect(remove_selected)
        close_btn.clicked.connect(dialog.accept)
        buttons.addWidget(open_btn)
        buttons.addWidget(remove_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        listing.itemDoubleClicked.connect(lambda _item: open_selected())
        refresh()
        dialog.exec_()

    def handle_download(self, download):
        suggested = download.suggestedFileName() or "download"
        target, _ = QFileDialog.getSaveFileName(
            self, "Save download", str(Path.home() / "Downloads" / suggested)
        )
        if not target:
            download.cancel()
            return
        download.setPath(target)
        download.accept()

    def make_button(self, text, tooltip=""):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def setup_shortcuts(self):
        QShortcut(
            QKeySequence("Ctrl+T"), self,
            activated=self.add_new_blank_tab
        )
        QShortcut(
            QKeySequence("Ctrl+W"), self,
            activated=self.close_current_tab
        )
        QShortcut(
            QKeySequence("Ctrl+L"), self,
            activated=self.focus_address_bar
        )
        QShortcut(
            QKeySequence("Ctrl+H"), self,
            activated=self.show_history
        )
        QShortcut(
            QKeySequence("Ctrl+J"), self,
            activated=self.show_downloads
        )
        QShortcut(
            QKeySequence("Ctrl+Shift+N"), self,
            activated=self.open_private_tab
        )
        QShortcut(
            QKeySequence("Alt+Left"), self,
            activated=self.go_back
        )
        QShortcut(
            QKeySequence("Alt+Right"), self,
            activated=self.go_forward
        )

    # ================ THEMES ================
    def toggle_theme(self):
        dark = self.settings.value("dark_mode", "true") == "true"
        self.settings.setValue("dark_mode", "false" if dark else "true")
        self.apply_theme()

        # Refresh the built-in home page so its colors match the selected theme.
        view = self.current_view()
        if view:
            current_url = view.url().toString()
            if current_url in ("about:blank", "") or current_url.startswith("data:text/html"):
                self.go_home()

    def apply_theme(self):
        dark = (
            self.settings.value("dark_mode", "true")
            == "true"
        )

        if dark:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background: #111318;
                    color: #e8eaf0;
                    font-family: Segoe UI;
                    font-size: 10pt;
                }
                QWidget#urlBar {
                    background: #20232b;
                    color: #ffffff;
                    border: 1px solid #363b48;
                    border-radius: 10px;
                    padding: 10px;
                    selection-background-color: #5667f5;
                }
                QLineEdit {
                    background: #20232b;
                    color: #ffffff;
                    border: 1px solid #363b48;
                    border-radius: 8px;
                    padding: 8px;
                }
                QPushButton {
                    background: #252933;
                    color: #f3f4f6;
                    border: 1px solid #363b48;
                    border-radius: 8px;
                    padding: 8px 11px;
                }
                QPushButton:hover {
                    background: #39405a;
                    border-color: #6574f5;
                }
                QTabWidget::pane {
                    border: 0;
                    background: #111318;
                }
                QTabBar::tab {
                    background: #20232b;
                    color: #b9bdc9;
                    padding: 10px 18px;
                    margin-right: 3px;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                }
                QTabBar::tab:selected {
                    background: #363c4b;
                    color: #ffffff;
                    border-bottom: 2px solid #7584ff;
                }
                QComboBox, QListWidget {
                    background: #20232b;
                    color: #ffffff;
                    border: 1px solid #363b48;
                    border-radius: 7px;
                    padding: 6px;
                }
                QProgressBar {
                    background: #20232b;
                    border: none;
                }
                QProgressBar::chunk {
                    background: #7584ff;
                }
                QCheckBox { spacing: 8px; }
                QWidget#titleBar { background: #111318; }
                QPushButton#overflowButton { font-size: 16pt; padding: 2px 10px; border: none; }
                QPushButton#customizeButton { background: #30384b; border: 1px solid #485473; border-radius: 10px; padding: 8px 16px; font-weight: 600; }
                QPushButton#customizeButton:hover { background: #414d6b; border-color: #8794ff; }
                QPushButton#windowCloseButton:hover { background: #d93025; color: white; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background: #f4f6fb;
                    color: #202333;
                    font-family: Segoe UI;
                    font-size: 10pt;
                }
                QWidget#urlBar, QLineEdit {
                    background: #ffffff;
                    color: #202333;
                    border: 1px solid #d7dce8;
                    border-radius: 9px;
                    padding: 9px;
                }
                QPushButton {
                    background: #ffffff;
                    color: #202333;
                    border: 1px solid #d7dce8;
                    border-radius: 8px;
                    padding: 8px 11px;
                }
                QPushButton:hover {
                    background: #e6ebff;
                    border-color: #7180f5;
                }
                QTabWidget::pane {
                    border: 0;
                    background: #ffffff;
                }
                QTabBar::tab {
                    background: #e7eaf2;
                    color: #555b6b;
                    padding: 10px 18px;
                    margin-right: 3px;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                }
                QTabBar::tab:selected {
                    background: #ffffff;
                    color: #22263a;
                    border-bottom: 2px solid #5667f5;
                }
                QComboBox, QListWidget {
                    background: #ffffff;
                    color: #202333;
                    border: 1px solid #d7dce8;
                    border-radius: 7px;
                    padding: 6px;
                }
                QProgressBar {
                    background: #e7eaf2;
                    border: none;
                }
                QProgressBar::chunk { background: #5667f5; }
                QWidget#titleBar { background: #f4f6fb; }
                QPushButton#overflowButton { font-size: 16pt; padding: 2px 10px; border: none; }
                QPushButton#customizeButton { background: #e7ebff; border: 1px solid #c7d0fa; border-radius: 10px; padding: 8px 16px; font-weight: 600; }
                QPushButton#customizeButton:hover { background: #d7defe; border-color: #7180f5; }
                QPushButton#windowCloseButton:hover { background: #d93025; color: white; }
            """)


    # ================ HOME PAGE ================
    def home_html(self):
        show_shortcuts = (
            self.settings.value("shortcuts", "true")
            == "true"
        )

        dark = self.settings.value("dark_mode", "true") == "true"
        page_bg = (
            "radial-gradient(circle at 50% 20%, #29345c 0, #151923 45%, #101217 100%)"
            if dark else
            "radial-gradient(circle at 50% 20%, #ffffff 0, #f1f4fc 55%, #e8edf8 100%)"
        )
        wallpaper = str(self.settings.value("wallpaper", "preset:theme-default"))
        if wallpaper in ("preset:theme-default", "preset:solid-midnight"):
            wallpaper_css = ("radial-gradient(circle at 50% 20%, #29345c 0, #151923 45%, #101217 100%)"
                             if dark else
                             "radial-gradient(circle at 50% 20%, #ffffff 0, #f1f4fc 55%, #e8edf8 100%)")
        else:
            wallpaper_css = self.wallpaper_css(wallpaper, dark)
        page_text = "#f5f6ff" if dark else "#202333"
        subtitle = "#aeb6d0" if dark else "#626b80"
        search_bg = "#202536" if dark else "#ffffff"
        search_text = "#ffffff" if dark else "#202333"
        search_border = "#444c68" if dark else "#d7dce8"
        card_bg = "#ffffff0b" if dark else "#ffffffcc"
        card_border = "#ffffff16" if dark else "#d7dce8"
        card_text = "#e8ebff" if dark else "#30384d"
        footer_text = "#7f89a7" if dark else "#737d91"
        cards = ""
        if show_shortcuts:
            default_shortcuts = [
                {"name": "Google", "url": "https://www.google.com"},
                {"name": "YouTube", "url": "https://www.youtube.com"},
                {"name": "GitHub", "url": "https://github.com"},
                {"name": "Wikipedia", "url": "https://www.wikipedia.org"},
                {"name": "DuckDuckGo", "url": "https://duckduckgo.com"},
                {"name": "ChatGPT", "url": "https://chatgpt.com"},
            ]
            try:
                shortcuts = json.loads(self.settings.value("custom_shortcuts", ""))
                if not isinstance(shortcuts, list):
                    shortcuts = default_shortcuts
            except (TypeError, json.JSONDecodeError):
                shortcuts = default_shortcuts
            import html
            for item in shortcuts:
                if not isinstance(item, dict) or not item.get("url"):
                    continue
                title = html.escape(str(item.get("name") or item["url"]))
                url = html.escape(str(item["url"]), quote=True)
                cards += f"""
                    <a class="card" href="{url}">
                        <span class="icon">✦</span>
                        <span>{title}</span>
                    </a>
                """

        wallpaper_value = str(self.settings.value("wallpaper", "preset:solid-midnight"))
        video_markup = ""
        if Path(wallpaper_value).is_file() and Path(wallpaper_value).suffix.lower() in (".mp4", ".webm", ".m4v"):
            video_uri = QUrl.fromLocalFile(str(Path(wallpaper_value).resolve())).toString()
            video_markup = f'<video autoplay muted loop playsinline style="position:fixed;inset:0;width:100%;height:100%;object-fit:cover;z-index:-1"><source src="{video_uri}"></video>'
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1">
        <style>
            body {{
                margin: 0;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: Segoe UI, Arial, sans-serif;
                background: {wallpaper_css};
                color: {page_text};
            }}
            .wrap {{
                width: min(850px, 90%);
                text-align: center;
                padding: 45px 0;
            }}
            .owner-logo {{
                font-size: 34px;
                font-weight: 800;
                letter-spacing: -1.5px;
                margin-bottom: 0;
                color: {page_text};
            }}
            .logo {{
                font-size: 58px;
                font-weight: 800;
                letter-spacing: -3px;
                margin-top: 0;
                margin-bottom: 8px;
            }}
            .logo span, .owner-logo span {{
                color: #91a0ff;
            }}
            .sub {{
                color: {subtitle};
                margin-bottom: 35px;
            }}
            .search {{
                display: block;
                box-sizing: border-box;
                width: 100%;
                padding: 19px 22px;
                border-radius: 18px;
                border: 1px solid {search_border};
                background: {search_bg};
                color: {search_text};
                font-size: 17px;
                outline: none;
                box-shadow: 0 15px 55px #0004;
            }}
            .search:focus {{
                border-color: #91a0ff;
            }}
            .grid {{
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(130px, 1fr));
                gap: 13px;
                margin-top: 28px;
            }}
            .card {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 18px 15px;
                border-radius: 14px;
                background: {card_bg};
                border: 1px solid {card_border};
                color: {card_text};
                text-decoration: none;
                transition: 0.2s;
            }}
            .card:hover {{
                background: #7584ff25;
                border-color: #7584ff;
                transform: translateY(-2px);
            }}
            .icon {{
                display: inline-flex;
                width: 32px;
                height: 32px;
                align-items: center;
                justify-content: center;
                border-radius: 10px;
                background: #7584ff30;
                color: #aeb8ff;
            }}
            .footer {{
                color: {footer_text};
                margin-top: 35px;
                font-size: 12px;
            }}
        </style>
        </head>
        <body>
            {video_markup}
            <div class="wrap">
                <div class="owner-logo">ANSH <span>SWAMI</span></div>
                <div class="logo">NEXUS<span>-V</span></div>
                <div class="sub">
                    Your space. Your web. Your browser.
                </div>
                <form action="https://www.google.com/search"
                      method="get">
                    <input class="search" type="search"
                           name="q"
                          placeholder="Type to search and your URL"

                           autofocus>
                </form>
                <div class="grid">{cards}</div>
                <div class="footer">
                    Nexus-V Advanced Browser · v{CURRENT_VERSION}
                </div>
            </div>
        </body>
        </html>
        """

    # ================ TABS ================
    def refresh_tab_overflow(self):
        self.tab_overflow_btn.setVisible(self.tabs.count() > 20)

    def show_tab_overflow_menu(self):
        menu = QMenu(self)
        for index in range(20, self.tabs.count()):
            title = self.tabs.tabText(index) or f"Tab {index + 1}"
            action = menu.addAction(f"{index + 1}. {title}")
            action.triggered.connect(lambda checked=False, i=index: self.tabs.setCurrentIndex(i))
        if menu.isEmpty():
            menu.addAction("No additional tabs").setEnabled(False)
        menu.exec_(self.tab_overflow_btn.mapToGlobal(self.tab_overflow_btn.rect().bottomLeft()))

    def wallpaper_css(self, value, dark=True):
        value = str(value or "preset:solid-midnight")
        presets = {
            "preset:theme-default": ("#111827" if dark else "#f1f4fc"),
            "preset:solid-midnight": "#111827",
            "preset:solid-charcoal": "#20242C",
            "preset:solid-blue": "#163A70",
            "preset:solid-teal": "#075E63",
            "preset:solid-purple": "#563D8F",
            "preset:solid-green": "#176B4D",
            "preset:solid-burgundy": "#782D45",
            "preset:solid-slate": "#536273",
            "preset:solid-grey": "#E7EAF0",
            "preset:solid-white": "#FFFFFF",
            # Backwards-compatible aliases for previously saved choices.
            "preset:solid-black": "#111318",
        }
        if value.startswith("solid:#") and re.fullmatch(r"solid:#[0-9a-fA-F]{6}", value):
            return value[6:]
        if value in presets:
            return presets[value]
        path = Path(value)
        if path.is_file():
            from urllib.parse import quote
            uri = QUrl.fromLocalFile(str(path.resolve())).toString()
            if path.suffix.lower() in (".mp4", ".webm", ".m4v"):
                return f"#111318; background-image: url('');"
            return f"center / cover no-repeat fixed url('{uri}')"
        return "radial-gradient(circle at 50% 20%, #29345c 0, #151923 45%, #101217 100%)" if dark else "radial-gradient(circle at 50% 20%, #ffffff 0, #f1f4fc 55%, #e8edf8 100%)"

    def manage_home_shortcuts(self):
        defaults = [
            {"name": "Google", "url": "https://www.google.com"},
            {"name": "YouTube", "url": "https://www.youtube.com"},
            {"name": "GitHub", "url": "https://github.com"},
            {"name": "Wikipedia", "url": "https://www.wikipedia.org"},
            {"name": "DuckDuckGo", "url": "https://duckduckgo.com"},
            {"name": "ChatGPT", "url": "https://chatgpt.com"},
        ]
        try:
            shortcuts = json.loads(self.settings.value("custom_shortcuts", ""))
            if not isinstance(shortcuts, list): shortcuts = defaults[:]
        except (TypeError, json.JSONDecodeError):
            shortcuts = defaults[:]
        dialog = QDialog(self); dialog.setWindowTitle("Manage homepage shortcuts"); dialog.resize(560, 420)
        layout = QVBoxLayout(dialog); listing = QListWidget(); layout.addWidget(listing)
        def refresh():
            listing.clear()
            for item in shortcuts: listing.addItem(f"{item.get('name','')} — {item.get('url','')}")
        def add_or_edit(edit=False):
            idx = listing.currentRow() if edit else -1
            old = shortcuts[idx] if 0 <= idx < len(shortcuts) else {"name":"", "url":"https://"}
            name, ok = QInputDialog.getText(dialog, "Shortcut name", "Name:", text=old.get("name", ""))
            if not ok or not name.strip(): return
            url, ok = QInputDialog.getText(dialog, "Shortcut URL", "URL:", text=old.get("url", "https://"))
            if not ok or not url.strip(): return
            url = url.strip()
            if not re.match(r"^https?://", url, re.I): url = "https://" + url
            item = {"name": name.strip(), "url": url}
            if edit and idx >= 0: shortcuts[idx] = item
            else: shortcuts.append(item)
            refresh()
        def remove():
            idx = listing.currentRow()
            if idx >= 0: shortcuts.pop(idx); refresh()
        row = QHBoxLayout(); add = QPushButton("+ New shortcut"); edit = QPushButton("Edit"); delete = QPushButton("Remove"); save = QPushButton("Save"); close = QPushButton("Close")
        add.clicked.connect(lambda: add_or_edit(False)); edit.clicked.connect(lambda: add_or_edit(True)); delete.clicked.connect(remove)
        def save_and_close():
            self.settings.setValue("custom_shortcuts", json.dumps(shortcuts, ensure_ascii=False)); dialog.accept()
            view = self.current_view()
            if view and getattr(view, "_nexus_home", False): self.go_home()
        save.clicked.connect(save_and_close); close.clicked.connect(dialog.reject)
        for btn in (add, edit, delete, save, close): row.addWidget(btn)
        layout.addLayout(row); refresh(); dialog.exec_()

    def setup_tray_and_hide_shortcut(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        tray_menu = QMenu(self)
        tray_menu.addAction("Show / Hide Nexus-V", self.toggle_visibility_from_hotkey)
        tray_menu.addAction("Exit", self.close)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(
            lambda reason: self.restore_from_tray()
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None
        )
        self.hide_shortcut = None
        self._global_hotkey_registered = False
        self._native_hotkey_filter = GlobalHideHotkeyFilter(self.toggle_visibility_from_hotkey)
        QApplication.instance().installNativeEventFilter(self._native_hotkey_filter)
        self.update_hide_shortcut()

    def _register_global_hide_hotkey(self):
        """Register the configured shortcut globally on Windows (works while hidden)."""
        if sys.platform != "win32":
            return False
        user32 = ctypes.windll.user32
        if self._global_hotkey_registered:
            user32.UnregisterHotKey(None, GlobalHideHotkeyFilter.HOTKEY_ID)
            self._global_hotkey_registered = False

        if self.settings.value("hide_enabled", "false") != "true":
            return False

        sequence = self.settings.value("hide_key", "Alt+X")
        parts = [part.strip().lower() for part in str(sequence).split("+") if part.strip()]
        modifiers = 0
        key_name = ""
        for part in parts:
            if part in ("ctrl", "control"):
                modifiers |= 0x0002
            elif part == "alt":
                modifiers |= 0x0001
            elif part == "shift":
                modifiers |= 0x0004
            elif part in ("win", "meta", "windows"):
                modifiers |= 0x0008
            else:
                key_name = part
        key_codes = {"space": 0x20, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
                     "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
                     "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
                     "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B}
        if len(key_name) == 1:
            vk = ord(key_name.upper())
        else:
            vk = key_codes.get(key_name, 0)
        if not modifiers or not vk:
            return False
        ok = bool(user32.RegisterHotKey(None, GlobalHideHotkeyFilter.HOTKEY_ID, modifiers, vk))
        self._global_hotkey_registered = ok
        return ok

    def update_hide_shortcut(self):
        if self.hide_shortcut:
            self.hide_shortcut.setEnabled(False)
            self.hide_shortcut.deleteLater()
            self.hide_shortcut = None

        if sys.platform == "win32":
            registered = self._register_global_hide_hotkey()
            if not registered and self.settings.value("hide_enabled", "false") == "true":
                # Fallback works while the window is visible if Windows rejects the global key.
                key = self.settings.value("hide_key", "Alt+X")
                try:
                    self.hide_shortcut = QShortcut(QKeySequence(key), self)
                    self.hide_shortcut.activated.connect(self.toggle_visibility_from_hotkey)
                except Exception:
                    pass
        elif self.settings.value("hide_enabled", "false") == "true":
            key = self.settings.value("hide_key", "Alt+X")
            try:
                self.hide_shortcut = QShortcut(QKeySequence(key), self)
                self.hide_shortcut.activated.connect(self.toggle_visibility_from_hotkey)
            except Exception:
                pass

    def toggle_visibility_from_hotkey(self):
        """Same shortcut hides the window and shows it again when pressed later."""
        if self.isVisible() and not self.isMinimized():
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray_icon.show()
                self.hide()
            else:
                self.showMinimized()
        else:
            self.restore_from_tray()

    def minimize_to_tray(self):
        self.toggle_visibility_from_hotkey()

    def restore_from_tray(self):
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def add_new_blank_tab(self):
        self.add_new_tab(QUrl("about:blank"), "New tab")

    def add_new_tab(self, url=None, label="New Tab",
                    private=False):
        if private:
            profile = QWebEngineProfile(self)
            profile.setHttpCacheType(
                QWebEngineProfile.MemoryHttpCache
            )
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.NoPersistentCookies
            )
            self.private_profiles.append(profile)
        else:
            profile = QWebEngineProfile.defaultProfile()

        page = QWebEnginePage(profile, self)
        view = QWebEngineView()
        view.setPage(page)
        view._nexus_private = private
        view._nexus_home = False

        view.titleChanged.connect(
            lambda title, v=view: self.update_tab_title(
                v, title
            )
        )
        view.urlChanged.connect(
            lambda qurl, v=view: self.update_address(v, qurl)
        )
        view.loadProgress.connect(
            self.progress_bar.setValue
        )
        view.loadFinished.connect(
            lambda ok, v=view: self.page_loaded(v, ok)
        )

        index = self.tabs.addTab(view, label)
        self.tabs.setCurrentIndex(index)
        self.refresh_tab_overflow()

        if url and url.toString() != "about:blank":
            view.setUrl(url)
        elif not private:
            view._nexus_home = True
            self.tabs.setTabText(index, "New tab")
            view.setHtml(self.home_html())

        return view

    def update_tab_title(self, view, title):
        index = self.tabs.indexOf(view)
        if index >= 0:
            if getattr(view, "_nexus_home", False):
                title = "New tab"
            else:
                title = title.strip() or "New tab"
            if len(title) > 24:
                title = title[:21] + "..."
            if is_private_view(view):
                title = "🔒 " + title
            self.tabs.setTabText(index, title)

    def address_text_for_view(self, view):
        """Return a human-friendly address, hiding the internal HTML home URL."""
        address = view.url().toString().strip()
        if not address or address == "about:blank" or address.lower().startswith("data:text/html"):
            return ""
        return address

    def update_address(self, view, url):
        address = url.toString().strip()
        is_internal_home = (
            not address
            or address == "about:blank"
            or address.lower().startswith("data:text/html")
        )
        if is_internal_home:
            if not is_private_view(view):
                view._nexus_home = True
                self.update_tab_title(view, "New tab")
        else:
            view._nexus_home = False
        if view == self.current_view():
            if is_internal_home:
                self.url_bar.clear()
            else:
                self.url_bar.setText(address)

    def page_loaded(self, view, ok):
        if view == self.current_view():
            self.progress_bar.setValue(100)
        if ok and not is_private_view(view):
            url = view.url().toString()
            if url and not url.startswith("about:") and not url.lower().startswith("data:text/html"):
                self.add_history(
                    view.title() or url, url
                )

    def tab_changed(self, index):
        view = self.current_view()
        if view:
            self.url_bar.setText(self.address_text_for_view(view))
            self.progress_bar.setValue(0)

    def current_view(self):
        widget = self.tabs.currentWidget()
        if isinstance(widget, QWebEngineView):
            return widget
        return None

    def close_tab(self, index):
        if self.tabs.count() <= 1:
            view = self.tabs.widget(index)
            if view:
                view._nexus_home = True
                view.setHtml(self.home_html())
            self.tabs.setTabText(index, "New tab")
            return

        view = self.tabs.widget(index)
        private = is_private_view(view)

        self.tabs.removeTab(index)
        self.refresh_tab_overflow()
        if private:
            profile = view.page().profile()
            view.deleteLater()
            if profile in self.private_profiles:
                self.private_profiles.remove(profile)
            profile.deleteLater()
        else:
            view.deleteLater()

    def close_current_tab(self):
        self.close_tab(self.tabs.currentIndex())

    # ================ NAVIGATION ================
    def navigate_to_url(self):
        text = self.url_bar.text().strip()
        if not text:
            return

        explicit_scheme = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", text)
        looks_like_host = bool(
            re.match(r"^(localhost|\d{1,3}(?:\.\d{1,3}){3})(:\d+)?(/.*)?$", text)
            or re.match(r"^[\w-]+(?:\.[\w-]+)+(?:[:/]\S*)?$", text)
        )
        if explicit_scheme or looks_like_host:
            if not explicit_scheme:
                text = "https://" + text
            url = text
        else:
            template = self.settings.value(
                "search_url", "https://www.google.com/search?q={query}"
            )
            encoded = quote_plus(text)
            url = template.replace("{query}", encoded)
            if "{query}" not in template and encoded not in url:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}q={encoded}"

        view = self.current_view()
        if view:
            view._nexus_home = False
            view.setUrl(QUrl(url))

    def go_back(self):
        view = self.current_view()
        if view:
            view.back()

    def go_forward(self):
        view = self.current_view()
        if view:
            view.forward()

    def reload_page(self):
        view = self.current_view()
        if view:
            view.reload()

    def go_home(self):
        view = self.current_view()
        if view:
            if is_private_view(view):
                view.setUrl(QUrl("about:blank"))
            else:
                view._nexus_home = True
                index = self.tabs.indexOf(view)
                if index >= 0:
                    self.tabs.setTabText(index, "New tab")
                self.url_bar.clear()
                view.setHtml(self.home_html())

    def focus_address_bar(self):
        self.url_bar.setFocus()
        self.url_bar.selectAll()

    # ================ HISTORY ================
    def load_history(self):
        try:
            if HISTORY_FILE.exists():
                data = json.loads(
                    HISTORY_FILE.read_text(
                        encoding="utf-8"
                    )
                )
                return data if isinstance(data, list) else []
        except Exception as error:
            print("History load error:", error)
        return []

    def save_history(self):
        try:
            HISTORY_FILE.write_text(
                json.dumps(
                    self.history[-2000:],
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )
        except Exception as error:
            print("History save error:", error)

    def add_history(self, title, url):
        if not url or url.startswith("about:"):
            return

        self.history.append({
            "title": title or url,
            "url": url,
            "time": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        })
        self.history = self.history[-2000:]
        self.save_history()

    def show_history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Browsing History")
        dialog.resize(720, 500)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Recently visited pages"))

        listing = QListWidget()
        for entry in reversed(self.history):
            listing.addItem(
                f"{entry.get('time', '')}  |  "
                f"{entry.get('title', '')}\n"
                f"{entry.get('url', '')}"
            )

        layout.addWidget(listing)

        row = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        clear_btn = QPushButton("Clear History")
        close_btn = QPushButton("Close")

        row.addWidget(open_btn)
        row.addWidget(clear_btn)
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

        def open_selected():
            item = listing.currentItem()
            if not item:
                return

            url = item.text().split("\n")[-1].strip()
            if url:
                view = self.current_view()
                if view:
                    view.setUrl(QUrl(url))
                dialog.accept()

        def clear_history():
            answer = QMessageBox.question(
                dialog,
                "Clear History",
                "Delete all saved browsing history?",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                self.history.clear()
                self.save_history()
                listing.clear()

        open_btn.clicked.connect(open_selected)
        clear_btn.clicked.connect(clear_history)
        close_btn.clicked.connect(dialog.accept)

        dialog.exec_()

    # ================ BOOKMARKS ================
    def add_current_bookmark(self):
        view = self.current_view()
        if not view:
            return

        if is_private_view(view):
            QMessageBox.information(
                self,
                "Private Tab",
                "Private tabs are not added to bookmarks."
            )
            return

        url = view.url().toString()
        title = view.title() or url

        if not url or url.startswith("about:"):
            return

        if any(item["url"] == url for item in self.bookmarks):
            QMessageBox.information(
                self, "Bookmark", "Already bookmarked."
            )
            return

        self.bookmarks.append({"title": title, "url": url})
        self.save_bookmarks()

        QMessageBox.information(
            self, "Bookmark", "Page bookmarked!"
        )

    # ================ DOWNLOADS ================
    def show_downloads(self):
        download_dir = Path.home() / "Downloads"
        download_dir.mkdir(parents=True, exist_ok=True)

        dialog = QDialog(self)
        dialog.setWindowTitle("Downloads")
        dialog.resize(700, 450)

        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(f"Download folder: {download_dir}")
        )

        listing = QListWidget()
        layout.addWidget(listing)

        def refresh_list():
            listing.clear()
            try:
                files = sorted(
                    download_dir.iterdir(),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True
                )
                for path in files:
                    if path.is_file():
                        size = path.stat().st_size
                        if size >= 1024 * 1024:
                            size_text = f"{size / 1048576:.1f} MB"
                        elif size >= 1024:
                            size_text = f"{size / 1024:.1f} KB"
                        else:
                            size_text = f"{size} B"

                        item = QListWidgetItem(
                            f"{path.name}  ({size_text})"
                        )
                        item.setData(Qt.UserRole, str(path))
                        listing.addItem(item)
            except Exception as error:
                listing.addItem(str(error))

        def open_selected():
            item = listing.currentItem()
            if not item:
                return
            path = item.data(Qt.UserRole)
            if path:
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(path)
                )

        def open_folder():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(download_dir))
            )

        row = QHBoxLayout()
        open_btn = QPushButton("Open Selected File")
        folder_btn = QPushButton("Open Folder")
        refresh_btn = QPushButton("Refresh")
        close_btn = QPushButton("Close")

        row.addWidget(open_btn)
        row.addWidget(folder_btn)
        row.addWidget(refresh_btn)
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

        open_btn.clicked.connect(open_selected)
        folder_btn.clicked.connect(open_folder)
        refresh_btn.clicked.connect(refresh_list)
        close_btn.clicked.connect(dialog.accept)

        listing.itemDoubleClicked.connect(
            lambda item: open_selected()
        )

        refresh_list()
        dialog.exec_()

    # ================ PRIVATE BROWSING ================
    def open_private_tab(self):
        self.add_new_tab(
            QUrl("about:blank"),
            "Private",
            private=True
        )

        QMessageBox.information(
            self,
            "Private Tab",
            "Private tab opened.\n\n"
            "This tab uses an in-memory browser profile "
            "and is excluded from saved history.\n\n"
            "Downloads and files you save are still kept "
            "on your computer. Private mode does not make "
            "you anonymous to websites or your network."
        )

    # ================ SETTINGS ================
    def open_wallpaper_customizer(self):
        dialog = WallpaperDialog(self.settings, self)
        if dialog.exec_() == QDialog.Accepted:
            self.settings.setValue("wallpaper", dialog.selected_wallpaper())
            view = self.current_view()
            if view and (getattr(view, "_nexus_home", False) or view.url().toString() in ("about:blank", "")):
                self.go_home()

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)

        if dialog.exec_() == QDialog.Accepted:
            dialog.save_settings()
            self.apply_theme()
            self.update_hide_shortcut()

            view = self.current_view()
            if view and (view.url().toString() in ("about:blank", "")
                         or view.url().toString().startswith("data:text/html")
                         or getattr(view, "_nexus_home", False)):
                self.go_home()

            QMessageBox.information(
                self,
                "Settings",
                "Settings saved successfully."
            )

    # ================ GITHUB UPDATER ================
    def check_for_updates(self, silent=False):
        self._update_silent = silent
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking...")

        self.update_worker = UpdateWorker()
        self.update_worker.update_signal.connect(
            self.handle_update_result
        )
        self.update_worker.finished.connect(
            lambda: self.update_btn.setEnabled(True)
        )
        self.update_worker.finished.connect(
            lambda: self.update_btn.setText("Update")
        )
        self.update_worker.start()

    def handle_update_result(self, latest_version):
        latest_version = (latest_version or "").strip()
        if latest_version.startswith("ERROR:") or not latest_version:
            if not self._update_silent:
                detail = latest_version.removeprefix("ERROR:").strip() or "GitHub returned an empty version.txt file."
                QMessageBox.warning(
                    self,
                    "Update Check Failed",
                    "Could not check for updates. Check your internet connection and try again.\n\n"
                    + detail,
                )
            return

        def version_tuple(value):
            # Accept numeric dotted versions such as 1.2.3 or 1.2.3.4.
            if not re.fullmatch(r"\d+(?:\.\d+)*", value):
                raise ValueError("Version must contain only numbers separated by dots.")
            return tuple(int(part) for part in value.split("."))

        try:
            latest_parts = version_tuple(latest_version)
            current_parts = version_tuple(CURRENT_VERSION)
        except ValueError as error:
            if not self._update_silent:
                QMessageBox.warning(
                    self, "Update Check Failed",
                    f"GitHub version information is invalid: {error}\n\n"
                    f"Received: {latest_version}",
                )
            return

        # Compare versions consistently even when component counts differ.
        width = max(len(latest_parts), len(current_parts))
        latest_parts += (0,) * (width - len(latest_parts))
        current_parts += (0,) * (width - len(current_parts))

        if latest_parts == current_parts:
            if not self._update_silent:
                QMessageBox.information(
                    self,
                    "Nexus-V Update",
                    "You already have the latest version.",
                )
            return

        if latest_parts < current_parts:
            if not self._update_silent:
                QMessageBox.information(
                    self,
                    "Nexus-V Update",
                    f"Local version: {CURRENT_VERSION}\n"
                    f"GitHub version: {latest_version}\n\n"
                    "The GitHub version is not newer than this version.",
                )
            return

        answer = QMessageBox.question(
            self,
            "Update Available",
            f"New version {latest_version} is available.\n"
            f"Installed version: {CURRENT_VERSION}\n\n"
            "Download and install it now?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if answer == QMessageBox.Yes:
            self.install_update()

    def install_update(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Updating...")

        self.install_worker = UpdateInstallWorker()
        self.install_worker.finished_signal.connect(
            self.finish_install_update
        )
        self.install_worker.start()

    def finish_install_update(self, success, message):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Update")

        if not success:
            QMessageBox.warning(
                self, "Update Failed", message
            )
            return

        QMessageBox.information(
            self,
            "Update Ready",
            "Update file installed.\n\n"
            "Please close the browser and launch it again "
            "to load the new version.\n\n"
            "A backup of the previous script was saved."
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_size_grip"):
            self._size_grip.move(
                self.width() - self._size_grip.width(),
                self.height() - self._size_grip.height()
            )

    # ================ CLOSE EVENT ================
    def closeEvent(self, event):
        if sys.platform == "win32" and getattr(self, "_global_hotkey_registered", False):
            try:
                ctypes.windll.user32.UnregisterHotKey(None, GlobalHideHotkeyFilter.HOTKEY_ID)
            except Exception:
                pass
            self._global_hotkey_registered = False
        try:
            QApplication.instance().removeNativeEventFilter(self._native_hotkey_filter)
        except Exception:
            pass
        self.save_history()
        self.save_bookmarks()
        event.accept()


# ================ START APPLICATION ================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))

    browser = NexusVBrowser()
    browser.show()

    sys.exit(app.exec_())
