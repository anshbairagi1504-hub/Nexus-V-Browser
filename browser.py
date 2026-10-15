import sys
import os
import json
import tempfile
import py_compile
import subprocess
from pathlib import Path
from urllib.parse import quote_plus
import re
from datetime import datetime
from PyQt5.QtGui import QIcon

import requests

from PyQt5.QtCore import QUrl, QThread, pyqtSignal, QSettings, Qt
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTabWidget, QProgressBar, QComboBox,
    QMessageBox, QDialog, QListWidget, QListWidgetItem, QLabel,
    QCheckBox, QFormLayout, QDialogButtonBox, QShortcut, QMenu,
    QFileDialog, QSizeGrip
)
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QDesktopServices


# ================ CONFIGURATION ================
APP_NAME = "Nexus-V Advanced Browser"
CURRENT_VERSION = "1.0.9"

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
            print("Update check failed:", error)


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
    def __init__(self, settings, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Nexus-V Settings")
        self.setMinimumWidth(420)
        self.settings = settings

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.home = QLineEdit(
            settings.value(
                "home_url", "https://duckduckgo.com"
            )
        )
        self.search = QLineEdit(
            settings.value(
                "search_url",
                "https://duckduckgo.com/?q={query}"
            )
        )

        self.dark = QCheckBox("Use modern dark theme")
        self.dark.setChecked(
            settings.value("dark_mode", "true") == "true"
        )

        self.shortcuts = QCheckBox(
            "Show quick shortcuts on the home page"
        )
        self.shortcuts.setChecked(
            settings.value("shortcuts", "true") == "true"
        )

        form.addRow("Home page URL:", self.home)
        form.addRow("Search URL ({query}):", self.search)

        layout.addLayout(form)
        layout.addWidget(self.dark)
        layout.addWidget(self.shortcuts)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_settings(self):
        self.settings.setValue(
            "home_url",
            self.home.text().strip()
            or "https://duckduckgo.com"
        )
        self.settings.setValue(
            "search_url",
            self.search.text().strip()
            or "https://duckduckgo.com/?q={query}"
        )
        self.settings.setValue(
            "dark_mode",
            "true" if self.dark.isChecked() else "false"
        )
        self.settings.setValue(
            "shortcuts",
            "true" if self.shortcuts.isChecked() else "false"
        )


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
        self.overflow_btn = self.make_button("⋮", "More options")
        self.overflow_btn.setObjectName("overflowButton")
        self.overflow_btn.clicked.connect(self.show_overflow_menu)
        title_layout.addWidget(self.overflow_btn)
        self.min_btn = self.make_button("—", "Minimize")
        self.min_btn.clicked.connect(self.showMinimized)
        title_layout.addWidget(self.min_btn)
        self.max_btn = self.make_button("□", "Maximize / restore")
        self.max_btn.clicked.connect(self.toggle_maximize)
        title_layout.addWidget(self.max_btn)
        self.close_btn = self.make_button("×", "Close browser")
        self.close_btn.setObjectName("windowCloseButton")
        self.close_btn.clicked.connect(self.close)
        title_layout.addWidget(self.close_btn)
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
        self.url_bar.setPlaceholderText("Ask Google or type URL")

        self.url_bar.setObjectName("urlBar")
        self.url_bar.setPlaceholderText(
            "Search or enter a website address"
        )
        self.url_bar.returnPressed.connect(
            self.navigate_to_url
        )
        bar.addWidget(self.url_bar, 1)

        # History, bookmarks, downloads, settings and update live in ⋮ menu.
        self.update_btn = self.make_button("Update", "Check GitHub for updates")
        self.update_btn.setVisible(False)

        self.main_layout.addWidget(self.top_bar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("browserTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)

        self.main_layout.addWidget(self.tabs, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.main_layout.addWidget(self.progress_bar)

        self.apply_theme()
        self.add_new_tab(QUrl("about:blank"), "Home")
        self.setup_shortcuts()
        QWebEngineProfile.defaultProfile().downloadRequested.connect(self.handle_download)
        self.check_for_updates(silent=True)

    def show_overflow_menu(self):
        menu = QMenu(self)
        menu.addAction("History", self.show_history)
        menu.addAction("Bookmarks", self.show_bookmarks)
        menu.addAction("Bookmark this page", self.add_current_bookmark)
        menu.addAction("Downloads", self.show_downloads)
        menu.addSeparator()
        menu.addAction("Incognito tab", self.open_private_tab)
        menu.addAction("Settings", self.open_settings)
        menu.addAction("Check for updates", self.check_for_updates)
        menu.addAction("About", self.show_about)
        menu.exec_(self.overflow_btn.mapToGlobal(self.overflow_btn.rect().bottomLeft()))

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
                QPushButton#windowCloseButton:hover { background: #d93025; color: white; }
            """)

    # ================ HOME PAGE ================
    def home_html(self):
        show_shortcuts = (
            self.settings.value("shortcuts", "true")
            == "true"
        )

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
                cards += f"""
                    <a class="card" href="{url}">
                        <span class="icon">✦</span>
                        <span>{title}</span>
                    </a>
                """

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
                background:
                    radial-gradient(
                        circle at 50% 20%,
                        #29345c 0,
                        #151923 45%,
                        #101217 100%
                    );
                color: #f5f6ff;
            }}
            .wrap {{
                width: min(850px, 90%);
                text-align: center;
                padding: 45px 0;
            }}
            .logo {{
                font-size: 58px;
                font-weight: 800;
                letter-spacing: -3px;
                margin-bottom: 8px;
            }}
            .logo span {{
                color: #91a0ff;
            }}
            .sub {{
                color: #aeb6d0;
                margin-bottom: 35px;
            }}
            .search {{
                display: block;
                box-sizing: border-box;
                width: 100%;
                padding: 19px 22px;
                border-radius: 18px;
                border: 1px solid #444c68;
                background: #202536;
                color: white;
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
                background: #ffffff0b;
                border: 1px solid #ffffff16;
                color: #e8ebff;
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
                color: #7f89a7;
                margin-top: 35px;
                font-size: 12px;
            }}
        </style>
        </head>
        <body>
            <div class="wrap">
                <div class="logo">NEXUS<span>-V</span></div>
                <div class="sub">
                    Your space. Your web. Your browser.
                </div>
                <form action="https://www.google.com/search"
                      method="get">
                    <input class="search" type="search"
                           name="q"
                          placeholder="Search Google or enter a website address"

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
    def add_new_blank_tab(self):
        self.add_new_tab(QUrl("about:blank"), "Home")

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

        if url and url.toString() != "about:blank":
            view.setUrl(url)
        elif not private:
            view.setHtml(self.home_html())

        return view

    def update_tab_title(self, view, title):
        index = self.tabs.indexOf(view)
        if index >= 0:
            title = title.strip() or "New Tab"
            if len(title) > 24:
                title = title[:21] + "..."
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
                self.add_history(
                    view.title() or url, url
                )

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
            self.tabs.setTabText(index, "Home")
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
    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)

        if dialog.exec_() == QDialog.Accepted:
            dialog.save_settings()
            self.apply_theme()

            view = self.current_view()
            if view and (
                view.url().toString() in
                ("about:blank", "")
            ):
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
        if latest_version == CURRENT_VERSION:
            if not self._update_silent:
                QMessageBox.information(
                    self,
                    "Nexus-V Update",
                    "You already have the latest version."
                )
            return

        def version_tuple(value):
            return tuple(int(part) if part.isdigit() else part for part in re.split(r"[._-]", value))

        try:
            is_older = version_tuple(latest_version) < version_tuple(CURRENT_VERSION)
        except TypeError:
            is_older = False
        if is_older:
            if not self._update_silent:
                QMessageBox.information(
                    self,
                    "Nexus-V Update",
                    f"Local version: {CURRENT_VERSION}\n"
                    f"GitHub version: {latest_version}"
                )
            return

        answer = QMessageBox.question(
            self,
            "Update Available",
            f"New version {latest_version} is available.\n"
            f"Installed version: {CURRENT_VERSION}\n\n"
            "Download and install it now?",
            QMessageBox.Yes | QMessageBox.No
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
