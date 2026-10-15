import sys
import os
import json
import tempfile
import py_compile
import re
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime

import requests
from PyQt5.QtCore import QUrl, QThread, pyqtSignal, QSettings, Qt
from PyQt5.QtGui import QFont, QKeySequence, QIcon, QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTabWidget, QProgressBar, QComboBox,
    QMessageBox, QDialog, QListWidget, QListWidgetItem, QLabel,
    QCheckBox, QFormLayout, QDialogButtonBox, QShortcut, QMenu, QSplitter
)
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEnginePage, QWebEngineView
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor

# ================ CONFIGURATION ================
APP_NAME = "Nexus-V Advanced Browser"
CURRENT_VERSION = "1.0.9"
GITHUB_REPO = "anshbairagi1504-hub/Nexus-V-Browser"
GITHUB_BRANCH = "main"

VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/version.txt"
RAW_SCRIPT_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/browser.py"

DATA_DIR = Path.home() / ".nexus_v_browser"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"
BOOKMARKS_FILE = DATA_DIR / "bookmarks.json"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

def is_private_view(view):
    return bool(getattr(view, "_nexus_private", False))


def version_key(value):
    """Compare numeric dotted versions safely."""
    parts = re.findall(r"\\d+", str(value or ""))
    return tuple(int(part) for part in parts) if parts else (0,)


class BasicAdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    """Lightweight tracker/ad domain blocker, not a full filter-list engine."""
    BLOCKED_HOSTS = {
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "adservice.google.com", "adnxs.com", "taboola.com", "outbrain.com",
        "scorecardresearch.com", "quantserve.com", "hotjar.com",
        "connect.facebook.net", "analytics.tiktok.com"
    }

    def interceptRequest(self, info):
        try:
            host = info.requestUrl().host().lower().strip(".")
            if any(host == domain or host.endswith("." + domain) for domain in self.BLOCKED_HOSTS):
                info.block(True)
        except Exception:
            pass

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
            print("Update check failed:", error)

class UpdateInstallWorker(QThread):
    finished_signal = pyqtSignal(bool, str)
    def run(self):
        temp_path = None
        try:
            response = requests.get(RAW_SCRIPT_URL, timeout=30)
            response.raise_for_status()
            new_code = response.text
            if not new_code.strip() or "class NexusVBrowser" not in new_code:
                raise ValueError("Downloaded file valid browser.py nahi lagti.")

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", encoding="utf-8", delete=False) as file:
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
            self.finished_signal.emit(True, str(current_path))
        except Exception as error:
            self.finished_signal.emit(False, f"Update fail hua: {error}")
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nexus-V Settings")
        self.setMinimumWidth(420)
        self.settings = settings

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.home = QLineEdit(settings.value("home_url", "https://duckduckgo.com"))
        self.search = QLineEdit(settings.value("search_url", "https://duckduckgo.com/?q={query}"))
        self.dark = QCheckBox("Use modern dark theme")
        self.dark.setChecked(settings.value("dark_mode", "true") == "true")

        self.shortcuts = QCheckBox("Show quick shortcuts on the home page")
        self.shortcuts.setChecked(settings.value("shortcuts", "true") == "true")
        self.adblock = QCheckBox("Block common ads and tracking domains (basic)")
        self.adblock.setChecked(settings.value("adblock", "true") == "true")
        self.restore_tabs = QCheckBox("Restore tabs next time")
        self.restore_tabs.setChecked(settings.value("restore_tabs", "false") == "true")

        form.addRow("Home page URL:", self.home)
        form.addRow("Search URL ({query}):", self.search)
        layout.addLayout(form)
        layout.addWidget(self.dark)
        layout.addWidget(self.shortcuts)
        layout.addWidget(self.adblock)
        layout.addWidget(self.restore_tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_settings(self):
        self.settings.setValue("home_url", self.home.text().strip() or "https://duckduckgo.com")
        self.settings.setValue("search_url", self.search.text().strip() or "https://duckduckgo.com/?q={query}")
        self.settings.setValue("dark_mode", "true" if self.dark.isChecked() else "false")
        self.settings.setValue("shortcuts", "true" if self.shortcuts.isChecked() else "false")
        self.settings.setValue("adblock", "true" if self.adblock.isChecked() else "false")
        self.settings.setValue("restore_tabs", "true" if self.restore_tabs.isChecked() else "false")

class NexusVBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("nexus_logo.png"))
        
        # Native window frame hata kar clean custom look setup karne ke liye
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.settings = QSettings("NexusV", "AdvancedBrowser")
        self.setWindowTitle(f"{APP_NAME} - v{CURRENT_VERSION}")
        self.resize(1320, 900)
        self.setMinimumSize(900, 600)

        self.bookmarks = self.load_bookmarks()
        self.history = self.load_history()
        self.private_profiles = []
        self._update_silent = False
        self.adblock_interceptor = BasicAdBlockInterceptor()
        default_profile = QWebEngineProfile.defaultProfile()
        if self.settings.value("adblock", "true") == "true":
            default_profile.setUrlRequestInterceptor(self.adblock_interceptor)
        default_profile.downloadRequested.connect(self.handle_download_requested)

        # Central Root Widget Container
        central = QWidget()
        self.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ================ 1. FIREFOX STYLE TOP TABS STRIP ================
        self.title_tabs_container = QWidget()
        self.title_tabs_container.setObjectName("titleTabsBar")
        title_tabs_layout = QHBoxLayout(self.title_tabs_container)
        title_tabs_layout.setContentsMargins(6, 4, 6, 0)
        title_tabs_layout.setSpacing(6)

        # Tabs Layout Integration
        self.tabs = QTabWidget()
        self.tabs.setObjectName("browserTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)
        title_tabs_layout.addWidget(self.tabs, 1)

        # Inline Plus Button for New Tab
        self.add_tab_btn = self.make_button("+", "New tab (Ctrl+T)")
        self.add_tab_btn.setObjectName("addTabBtn")
        self.add_tab_btn.clicked.connect(self.add_new_blank_tab)
        title_tabs_layout.addWidget(self.add_tab_btn)

        title_tabs_layout.addStretch()

        # Sleek Window Action Controls (Minimize, Maximize, Close)
        control_btn_style = "QPushButton { background: transparent; border: none; color: #1c1b1f; font-size: 11pt; padding: 4px 10px; } QPushButton:hover { background-color: rgba(0,0,0,0.08); }"
        
        min_btn = QPushButton("–")
        min_btn.setStyleSheet(control_btn_style)
        min_btn.clicked.connect(self.showMinimized)
        title_tabs_layout.addWidget(min_btn)

        self.max_btn = QPushButton("⬜")
        self.max_btn.setStyleSheet(control_btn_style)
        self.max_btn.clicked.connect(self.toggle_maximize)
        title_tabs_layout.addWidget(self.max_btn)

        close_btn = QPushButton("✕")
        close_btn.setStyleSheet("QPushButton { background: transparent; border: none; color: #1c1b1f; font-size: 10pt; padding: 4px 12px; } QPushButton:hover { background-color: #e81123; color: white; }")
        close_btn.clicked.connect(self.close)
        title_tabs_layout.addWidget(close_btn)

        self.main_layout.addWidget(self.title_tabs_container)

        # ================ 2. NAVIGATION BAR ================
        self.top_bar = QWidget()
        self.top_bar.setObjectName("navigationBar")
        bar = QHBoxLayout(self.top_bar)
        bar.setContentsMargins(10, 6, 10, 6)
        bar.setSpacing(8)

        self.back_btn = self.make_button("←", "Go back")
        self.back_btn.clicked.connect(self.go_back)
        bar.addWidget(self.back_btn)

        self.forward_btn = self.make_button("→", "Go forward")
        self.forward_btn.clicked.connect(self.go_forward)
        bar.addWidget(self.forward_btn)

        self.reload_btn = self.make_button("⟳", "Reload page")
        self.reload_btn.clicked.connect(self.reload_page)
        bar.addWidget(self.reload_btn)

        self.home_btn = self.make_button("⌂", "Home")
        self.home_btn.clicked.connect(self.go_home)
        bar.addWidget(self.home_btn)

        # Firefox Curved Oval Address bar
        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("urlBar")
        self.url_bar.setPlaceholderText("Search with Google or enter address")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        bar.addWidget(self.url_bar, 1)

        self.bookmark_btn = self.make_button("☆", "Bookmark this page")
        self.bookmark_btn.clicked.connect(self.add_current_bookmark)
        bar.addWidget(self.bookmark_btn)

        self.bookmark_menu = QComboBox()
        self.bookmark_menu.setMinimumWidth(125)
        self.bookmark_menu.addItem("Bookmarks")
        self.bookmark_menu.activated.connect(self.open_bookmark)
        bar.addWidget(self.bookmark_menu)
        self.refresh_bookmark_menu()

        self.download_btn = self.make_button("↓", "Downloads")
        self.download_btn.clicked.connect(self.show_downloads)
        bar.addWidget(self.download_btn)

        self.history_btn = self.make_button("◷", "Browsing history")
        self.history_btn.clicked.connect(self.show_history)
        bar.addWidget(self.history_btn)

        self.private_btn = self.make_button("Incognito", "Open a private tab")
        self.private_btn.clicked.connect(self.open_private_tab)
        bar.addWidget(self.private_btn)

        self.settings_btn = self.make_button("⚙", "Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        bar.addWidget(self.settings_btn)

        self.update_btn = self.make_button("Update", "Check GitHub for updates")
        self.update_btn.clicked.connect(self.check_for_updates)
        bar.addWidget(self.update_btn)

        self.more_btn = self.make_button("⋮", "More browser options")
        self.more_menu = QMenu(self)
        self.more_menu.addAction("History", self.show_history)
        self.more_menu.addAction("Bookmarks", self.show_bookmarks)
        self.more_menu.addAction("Split view", self.open_split_view)
        self.more_menu.addSeparator()
        self.more_menu.addAction("Downloads", self.show_downloads)
        self.more_menu.addAction("Private tab", self.open_private_tab)
        self.more_menu.addAction("Settings", self.open_settings)
        self.more_menu.addAction("Check for updates", self.check_for_updates)
        self.more_btn.clicked.connect(lambda: self.more_menu.exec_(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft())))
        bar.addWidget(self.more_btn)

        self.main_layout.addWidget(self.top_bar)

        # ================ 3. PROGRESS INFRASTRUCTURE ================
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.main_layout.addWidget(self.progress_bar)

        self.apply_theme()
        self.setup_shortcuts()
        saved_tabs = self.settings.value("open_tabs", [])
        if isinstance(saved_tabs, str):
            try:
                saved_tabs = json.loads(saved_tabs)
            except Exception:
                saved_tabs = []
        opened = False
        if self.settings.value("restore_tabs", "false") == "true" and isinstance(saved_tabs, list):
            for saved_url in saved_tabs:
                if isinstance(saved_url, str) and saved_url.startswith(("http://", "https://")):
                    self.add_new_tab(QUrl(saved_url), saved_url)
                    opened = True
        if not opened:
            self.add_new_tab(QUrl("about:blank"), "New Tab")
        self.check_for_updates(silent=True)

    def make_button(self, text, tooltip=""):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.add_new_blank_tab)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close_current_tab)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.focus_address_bar)
        QShortcut(QKeySequence("Ctrl+H"), self, activated=self.show_history)
        QShortcut(QKeySequence("Ctrl+J"), self, activated=self.show_downloads)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, activated=self.open_private_tab)
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.go_back)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self.go_forward)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self.open_split_view)

    # ================ STYLING MATRIX ================
    def apply_theme(self):
        dark = self.settings.value("dark_mode", "true") == "true"
        bg = "#171923" if dark else "#ffffff"
        text = "#f2f3f8" if dark else "#1c1b1f"
        panel = "#222635" if dark else "#f2ebf0"
        field = "#252a39" if dark else "#f0f0f4"
        border = "#3a4053" if dark else "#e0e0e6"
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {bg};
                color: {text};
                font-family: 'Segoe UI', Arial;
                font-size: 10pt;
            }}
            QWidget#titleTabsBar {{ background-color: {panel}; border: none; }}
            QWidget#navigationBar {{ background-color: {bg}; border-bottom: 1px solid {border}; }}
            QTabWidget::pane {{ border: 0; background: {bg}; }}
            QTabBar {{ background: transparent; }}
            QTabBar::tab {{
                background: transparent; color: {text}; padding: 7px 18px;
                margin-top: 5px; margin-bottom: 3px; margin-left: 4px;
                border-radius: 12px; font-weight: 500;
            }}
            QTabBar::tab:hover {{ background: rgba(127,147,255,0.12); }}
            QTabBar::tab:selected {{ background: {field}; color: {text}; }}
            QLineEdit#urlBar {{
                background: {field}; color: {text}; border: 1px solid {border};
                border-radius: 18px; padding: 6px 16px;
            }}
            QLineEdit#urlBar:focus {{ border: 2px solid #0a84ff; }}
            QPushButton {{
                background: transparent; border: none; border-radius: 6px;
                padding: 6px 10px; color: {text};
            }}
            QPushButton:hover {{ background: rgba(127,147,255,0.14); }}
            QPushButton#addTabBtn {{ font-size: 13pt; padding: 2px 8px; margin-top: 4px; }}
            QComboBox, QListWidget {{
                background: {field}; color: {text}; border: 1px solid {border};
                border-radius: 8px; padding: 4px;
            }}
            QProgressBar {{ background: {field}; border: none; }}
            QProgressBar::chunk {{ background: #0a84ff; }}
            QMenu {{ background: {field}; color: {text}; border: 1px solid {border}; }}
            QMenu::item:selected {{ background: #0a84ff; color: white; }}
        """)

    # ================ ENGINE CORE LOGIC ================
    def home_html(self):
        show_shortcuts = (self.settings.value("shortcuts", "true") == "true")
        cards = ""
        if show_shortcuts:
            shortcuts = [
                ("Google", "https://www.google.com"),
                ("YouTube", "https://www.youtube.com"),
                ("GitHub", "https://github.com"),
                ("Wikipedia", "https://www.wikipedia.org"),
                ("DuckDuckGo", "https://duckduckgo.com"),
                ("ChatGPT", "https://chatgpt.com"),
            ]
            for title, url in shortcuts:
                cards += f'<a class="card" href="{url}"><span class="icon">✦</span><span>{title}</span></a>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{{{
                margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
                font-family: 'Segoe UI', system-ui; background: radial-gradient(circle at 50% 20%, #1e2230 0%, #0f111a 60%); color: #f5f6ff;
            }}}}
            .wrap {{{{ width: min(800px, 90%); text-align: center; }}}}
            .logo {{{{ font-size: 64px; font-weight: 800; letter-spacing: -2px; margin-bottom: 5px; }}}}
            .logo span {{{{ color: #7f93ff; }}}}
            .sub {{{{ color: #9aa2bc; margin-bottom: 40px; font-size: 16px; }}}}
            .search {{{{
                display: block; box-sizing: border-box; width: 100%; padding: 18px 24px; border-radius: 24px;
                border: 1px solid #3c445c; background: #1a1e2e; color: white; font-size: 16px; outline: none;
            }}}}
            .search:focus {{{{ border-color: #7f93ff; }}}}
            .grid {{{{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 15px; margin-top: 35px; }}}}
            .card {{{{
                display: flex; align-items: center; gap: 10px; padding: 16px; border-radius: 16px;
                background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); color: #e8ebff; text-decoration: none; transition: 0.2s;
            }}}}
            .card:hover {{{{ background: rgba(127,147,255,0.15); border-color: #7f93ff; transform: translateY(-2px); }}}}
            .icon {{{{ display: inline-flex; width: 28px; height: 28px; align-items: center; justify-content: center; border-radius: 8px; background: rgba(127,147,255,0.2); color: #aeb8ff; }}}}
            .footer {{{{ color: #626b86; margin-top: 50px; font-size: 12px; }}}}
        </style>
        </head>
        <body>
            <div class="wrap">
                <div class="logo">NEXUS<span>-V</span></div>
                <div class="sub">Your space. Your web. Your browser.</div>
                <form action="https://duckduckgo.com/" method="get">
                    <input class="search" type="search" name="q" placeholder="Search with Google or type address" autofocus>
                </form>
                <div class="grid">{cards}</div>
                <div class="footer">Nexus-V Advanced Browser · v{CURRENT_VERSION}</div>
            </div>
        </body>
        </html>
        """

    def add_new_blank_tab(self):
        self.add_new_tab(QUrl("about:blank"), "New Tab")

    def add_new_tab(self, url=None, label="New Tab", private=False):
        if private:
            profile = QWebEngineProfile(self)
            profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
            self.private_profiles.append(profile)
        else:
            profile = QWebEngineProfile.defaultProfile()

        page = QWebEnginePage(profile, self)
        view = QWebEngineView()
        view.setPage(page)
        view._nexus_private = private

        view.titleChanged.connect(lambda title, v=view: self.update_tab_title(v, title))
        view.urlChanged.connect(lambda qurl, v=view: self.update_address(v, qurl))
        view.loadProgress.connect(self.progress_bar.setValue)
        view.loadFinished.connect(lambda ok, v=view: self.page_loaded(v, ok))

        index = self.tabs.addTab(view, label)
        self.tabs.setCurrentIndex(index)

        if url and url.toString() != "about:blank":
            view.setUrl(url)
        else:
            view.setHtml(self.home_html())
        return view

    def update_tab_title(self, view, title):
        index = self.tabs.indexOf(view)
        if index >= 0:
            title = title.strip() or "New Tab"
            if len(title) > 20:
                title = title[:18] + "..."
            if is_private_view(view):
                title = "🔒 " + title
            self.tabs.setTabText(index, title)

    def update_address(self, view, url):
        if view == self.current_view():
            self.url_bar.setText(url.toString())

    def page_loaded(self, view, ok):
        if view == self.current_view():
            self.progress_bar.setValue(100)
        if ok and not is_private_view(view):
            url = view.url().toString()
            if url and not url.startswith("about:"):
                self.add_history(view.title() or url, url)

    def tab_changed(self, index):
        view = self.current_view()
        if view:
            self.url_bar.setText(view.url().toString())
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
                view.setHtml(self.home_html())
            self.tabs.setTabText(index, "New Tab")
            return

        view = self.tabs.widget(index)
        private = is_private_view(view)
        self.tabs.removeTab(index)
        
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

    def navigate_to_url(self):
        text = self.url_bar.text().strip()
        if not text:
            return
        if " " in text or "." not in text:
            template = self.settings.value("search_url", "https://duckduckgo.com/?q={query}")
            url = template.replace("{query}", quote_plus(text))
        else:
            if not text.startswith(("http://", "https://", "file://")):
                text = "https://" + text
            url = text
        view = self.current_view()
        if view:
            view.setUrl(QUrl(url))

    def go_back(self):
        view = self.current_view()
        if view: view.back()

    def go_forward(self):
        view = self.current_view()
        if view: view.forward()

    def reload_page(self):
        view = self.current_view()
        if view: view.reload()

    def go_home(self):
        view = self.current_view()
        if view: view.setHtml(self.home_html())

    def focus_address_bar(self):
        self.url_bar.setFocus()
        self.url_bar.selectAll()

    # ================ DATA CONTROLS ================
    def load_history(self):
        try:
            if HISTORY_FILE.exists():
                data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
        except Exception as error:
            print("History load error:", error)
        return []

    def save_history(self):
        try:
            HISTORY_FILE.write_text(json.dumps(self.history[-2000:], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as error:
            print("History save error:", error)

    def add_history(self, title, url):
        if not url or url.startswith("about:"): return
        self.history.append({
            "title": title or url,
            "url": url,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            listing.addItem(f"{entry.get('time', '')}  |  {entry.get('title', '')}\n{entry.get('url', '')}")
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
            if not item: return
            url = item.text().split("\n")[-1].strip()
            if url:
                view = self.current_view()
                if view: view.setUrl(QUrl(url))
                dialog.accept()

        def clear_history():
            answer = QMessageBox.question(dialog, "Clear History", "Delete all saved browsing history?", QMessageBox.Yes | QMessageBox.No)
            if answer == QMessageBox.Yes:
                self.history.clear()
                self.save_history()
                listing.clear()

        open_btn.clicked.connect(open_selected)
        clear_btn.clicked.connect(clear_history)
        close_btn.clicked.connect(dialog.accept)
        dialog.exec_()

    def load_bookmarks(self):
        try:
            if BOOKMARKS_FILE.exists():
                data = json.loads(BOOKMARKS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict) and item.get("url")]
        except Exception as error:
            print("Bookmarks load error:", error)
        return []

    def save_bookmarks(self):
        try:
            BOOKMARKS_FILE.write_text(json.dumps(self.bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as error:
            print("Bookmarks save error:", error)

    def refresh_bookmark_menu(self):
        self.bookmark_menu.blockSignals(True)
        self.bookmark_menu.clear()
        self.bookmark_menu.addItem("Bookmarks")
        for item in self.bookmarks:
            self.bookmark_menu.addItem(item.get("title") or item["url"], item["url"])
        self.bookmark_menu.blockSignals(False)

    def show_bookmarks(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Bookmarks")
        dialog.resize(650, 440)
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        for entry in self.bookmarks:
            item = QListWidgetItem(f"{entry.get('title', entry.get('url', 'Bookmark'))}\\n{entry.get('url', '')}")
            item.setData(Qt.UserRole, entry.get("url", ""))
            listing.addItem(item)
        layout.addWidget(listing)
        row = QHBoxLayout()
        open_btn, delete_btn, close_btn = QPushButton("Open"), QPushButton("Remove"), QPushButton("Close")
        row.addWidget(open_btn)
        row.addWidget(delete_btn)
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

        def open_selected():
            item = listing.currentItem()
            if item and item.data(Qt.UserRole):
                view = self.current_view()
                if view:
                    view.setUrl(QUrl(item.data(Qt.UserRole)))
                dialog.accept()

        def remove_selected():
            item = listing.currentItem()
            if item:
                url = item.data(Qt.UserRole)
                self.bookmarks = [bookmark for bookmark in self.bookmarks if bookmark.get("url") != url]
                self.save_bookmarks()
                listing.takeItem(listing.row(item))
                self.refresh_bookmark_menu()

        open_btn.clicked.connect(open_selected)
        delete_btn.clicked.connect(remove_selected)
        close_btn.clicked.connect(dialog.accept)
        dialog.exec_()

    def add_current_bookmark(self):
        view = self.current_view()
        if not view: return
        if is_private_view(view):
            QMessageBox.information(self, "Private Tab", "Private tabs are not added to bookmarks.")
            return
        url = view.url().toString()
        title = view.title() or url
        if not url or url.startswith("about:"): return
        if any(item["url"] == url for item in self.bookmarks):
            QMessageBox.information(self, "Bookmark", "Already bookmarked.")
            return
        self.bookmarks.append({"title": title, "url": url})
        self.save_bookmarks()
        self.refresh_bookmark_menu()
        QMessageBox.information(self, "Bookmark", "Page bookmarked!")

    def open_bookmark(self, index):
        if index <= 0: return
        url = self.bookmark_menu.itemData(index)
        if url:
            view = self.current_view()
            if view: view.setUrl(QUrl(str(url)))
        self.bookmark_menu.setCurrentIndex(0)

    def handle_download_requested(self, download):
        download_dir = Path.home() / "Downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        suggested = download.downloadFileName() or "download"
        target = download_dir / suggested
        if target.exists():
            stem, suffix = target.stem, target.suffix
            counter = 1
            while target.exists():
                target = download_dir / f"{stem} ({counter}){suffix}"
                counter += 1
        download.setDownloadDirectory(str(target.parent))
        download.setDownloadFileName(target.name)
        download.accept()
        self.statusBar().showMessage(f"Downloading: {target.name}", 5000)

    def show_downloads(self):
        download_dir = Path.home() / "Downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        dialog = QDialog(self)
        dialog.setWindowTitle("Downloads")
        dialog.resize(700, 450)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Download folder: {download_dir}"))
        listing = QListWidget()
        layout.addWidget(listing)

        def refresh_list():
            listing.clear()
            try:
                files = sorted(download_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
                for path in files:
                    if path.is_file():
                        size = path.stat().st_size
                        size_text = f"{size / 1048576:.1f} MB" if size >= 1024*1024 else f"{size / 1024:.1f} KB"
                        item = QListWidgetItem(f"{path.name}  ({size_text})")
                        item.setData(Qt.UserRole, str(path))
                        listing.addItem(item)
            except Exception as error:
                listing.addItem(str(error))

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

        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(listing.currentItem().data(Qt.UserRole))) if listing.currentItem() else None)
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(download_dir))))
        refresh_btn.clicked.connect(refresh_list)
        close_btn.clicked.connect(dialog.accept)
        refresh_list()
        dialog.exec_()

    def open_split_view(self):
        current = self.current_view()
        if not current:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Nexus-V Split View")
        dialog.resize(1200, 700)
        layout = QHBoxLayout(dialog)
        splitter = QSplitter(Qt.Horizontal, dialog)
        left = QWebEngineView(dialog)
        left.setPage(QWebEnginePage(QWebEngineProfile.defaultProfile(), left))
        right = QWebEngineView(dialog)
        right.setPage(QWebEnginePage(QWebEngineProfile.defaultProfile(), right))
        current_url = current.url()
        left.setUrl(current_url if current_url.toString() not in ("", "about:blank") else QUrl("https://duckduckgo.com"))
        right.setUrl(QUrl("https://duckduckgo.com"))
        splitter.addWidget(left)
        splitter.addWidget(right)
        layout.addWidget(splitter)
        dialog.exec_()

    def open_private_tab(self):
        self.add_new_tab(QUrl("about:blank"), "Private", private=True)
        QMessageBox.information(self, "Private Tab", "Private tab opened using an in-memory browser profile.")

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() == QDialog.Accepted:
            dialog.save_settings()
            self.apply_theme()
            profile = QWebEngineProfile.defaultProfile()
            profile.setUrlRequestInterceptor(
                self.adblock_interceptor if self.settings.value("adblock", "true") == "true" else None
            )
            QMessageBox.information(self, "Settings", "Settings saved successfully.")

    # ================ DYNAMIC FRAME DRAGGING & SIZING ================
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("⬜")
        else:
            self.showMaximized()
            self.max_btn.setText("🗗")

    def mousePressEvent(self, event):
        if self.title_tabs_container.underMouse():
            if event.button() == Qt.LeftButton:
                self.dragPosition = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if self.title_tabs_container.underMouse() and not self.isMaximized():
            if event.buttons() == Qt.LeftButton:
                self.move(event.globalPos() - self.dragPosition)
                event.accept()

    # ================ UPDATER MATRIX ================
    def check_for_updates(self, silent=False):
        self._update_silent = silent
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking...")
        self.update_worker = UpdateWorker()
        self.update_worker.update_signal.connect(self.handle_update_result)
        self.update_worker.finished.connect(lambda: self.update_btn.setEnabled(True))
        self.update_worker.finished.connect(lambda: self.update_btn.setText("Update"))
        self.update_worker.start()

    def handle_update_result(self, latest_version):
        if version_key(latest_version) <= version_key(CURRENT_VERSION):
            if not self._update_silent:
                QMessageBox.information(self, "Nexus-V Update", "You already have the latest version.")
            return
        answer = QMessageBox.question(self, "Update Available", f"New version {latest_version} available. Install now?", QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.install_update()

    def install_update(self):
        if getattr(sys, "frozen", False):
            QMessageBox.information(
                self, "Update available",
                "Installed EXE ko browser.py se safely replace nahi kiya ja sakta. "
                "GitHub Releases khulengi; latest installer download karke install karein."
            )
            QDesktopServices.openUrl(QUrl(RELEASES_URL))
            return
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Updating...")
        self.install_worker = UpdateInstallWorker()
        self.install_worker.finished_signal.connect(self.finish_install_update)
        self.install_worker.start()

    def finish_install_update(self, success, message):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Update")
        if not success:
            QMessageBox.warning(self, "Update Failed", message)
            return
        QMessageBox.information(self, "Update Ready", "Please restart browser to apply the update.")

    def closeEvent(self, event):
        self.save_history()
        self.save_bookmarks()
        open_tabs = []
        for index in range(self.tabs.count()):
            view = self.tabs.widget(index)
            if isinstance(view, QWebEngineView) and not is_private_view(view):
                url = view.url().toString()
                if url.startswith(("http://", "https://")):
                    open_tabs.append(url)
        self.settings.setValue("open_tabs", json.dumps(open_tabs))
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))
    browser = NexusVBrowser()
    browser.show()
    sys.exit(app.exec_())
