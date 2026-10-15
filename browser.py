import sys
import os
import subprocess
import tempfile
import py_compile
from pathlib import Path
from urllib.parse import quote_plus

import requests

from PyQt5.QtCore import QUrl, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QTabWidget,
    QProgressBar,
    QComboBox,
    QMessageBox,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView


# ================ CONFIGURATION ================

APP_NAME = "Nexus-V Advanced Browser"
CURRENT_VERSION = "1.0.1"

# GitHub repository ke owner/repo ko yahan set karein, example: "username/nexus-v"
# GitHub repository: https://github.com/anshbairagi1504-hub/Nexus-V-Browser
GITHUB_REPO = "anshbairagi1504-hub/Nexus-V-Browser"
GITHUB_BRANCH = "main"

VERSION_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/version.txt"
    if GITHUB_REPO else ""
)
RAW_SCRIPT_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/browser.py"
    if GITHUB_REPO else ""
)


# ================ UPDATE WORKER ================

class UpdateWorker(QThread):
    update_signal = pyqtSignal(str)

    def run(self):
        if not VERSION_URL:
            self.update_signal.emit("")
            return
        try:
            response = requests.get(VERSION_URL, timeout=10)
            response.raise_for_status()

            latest_version = response.text.strip()

            if latest_version:
                self.update_signal.emit(latest_version)

        except Exception as error:
            print("Update check failed:", error)


class UpdateInstallWorker(QThread):
    finished_signal = pyqtSignal(bool, str)

    def run(self):
        if not RAW_SCRIPT_URL:
            self.finished_signal.emit(False, "GitHub RAW_SCRIPT_URL abhi set nahi hai.")
            return
        try:
            response = requests.get(RAW_SCRIPT_URL, timeout=30)
            response.raise_for_status()
            new_code = response.text
            if not new_code.strip() or "class NexusVBrowser" not in new_code:
                raise ValueError("Downloaded file valid browser.py nahi lagti.")

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", encoding="utf-8", delete=False) as temp_file:
                temp_file.write(new_code)
                temp_path = temp_file.name
            try:
                py_compile.compile(temp_path, doraise=True)
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

            current_path = Path(__file__).resolve()
            backup_path = current_path.with_suffix(current_path.suffix + ".bak")
            new_path = current_path.with_suffix(current_path.suffix + ".new")
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


# ================ MAIN BROWSER ================

class NexusVBrowser(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            f"{APP_NAME} - v{CURRENT_VERSION}"
        )
        self.resize(1200, 850)

        self.bookmarks = []

        central = QWidget()
        self.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Navigation bar
        self.top_bar = QWidget()
        self.top_bar.setStyleSheet("""
            QWidget {
                background-color: #f1f3f4;
            }
            QPushButton {
                background: white;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover {
                background: #e0e7ff;
            }
        """)

        bar = QHBoxLayout(self.top_bar)
        bar.setContentsMargins(6, 6, 6, 6)

        self.back_btn = QPushButton("◀")
        self.back_btn.setFixedSize(36, 34)
        self.back_btn.clicked.connect(self.go_back)
        bar.addWidget(self.back_btn)

        self.forward_btn = QPushButton("▶")
        self.forward_btn.setFixedSize(36, 34)
        self.forward_btn.clicked.connect(self.go_forward)
        bar.addWidget(self.forward_btn)

        self.reload_btn = QPushButton("⟳")
        self.reload_btn.setFixedSize(36, 34)
        self.reload_btn.clicked.connect(self.reload_page)
        bar.addWidget(self.reload_btn)

        self.home_btn = QPushButton("Home")
        self.home_btn.clicked.connect(self.go_home)
        bar.addWidget(self.home_btn)

        self.add_tab_btn = QPushButton("+")
        self.add_tab_btn.setFont(
            QFont("Arial", 13, QFont.Bold)
        )
        self.add_tab_btn.setFixedSize(36, 34)
        self.add_tab_btn.clicked.connect(self.add_new_blank_tab)
        bar.addWidget(self.add_tab_btn)

        self.url_bar = QLineEdit()
        self.url_bar.setFont(QFont("Arial", 11))
        self.url_bar.setPlaceholderText(
            "Enter URL or search the web..."
        )
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        bar.addWidget(self.url_bar, 1)

        self.bookmark_btn = QPushButton("⭐")
        self.bookmark_btn.setFixedSize(36, 34)
        self.bookmark_btn.setToolTip("Add bookmark")
        self.bookmark_btn.clicked.connect(
            self.add_current_bookmark
        )
        bar.addWidget(self.bookmark_btn)

        self.bookmark_menu = QComboBox()
        self.bookmark_menu.setMinimumWidth(140)
        self.bookmark_menu.addItem("Bookmarks")
        self.bookmark_menu.activated.connect(
            self.open_bookmark
        )
        bar.addWidget(self.bookmark_menu)

        self.update_btn = QPushButton("Update")
        self.update_btn.setToolTip("GitHub se update check/install karein")
        self.update_btn.clicked.connect(self.check_for_updates)
        bar.addWidget(self.update_btn)

        self.main_layout.addWidget(self.top_bar)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)

        self.main_layout.addWidget(self.tabs, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)

        self.main_layout.addWidget(self.progress_bar)

        # Initial home tab
        self.add_new_tab(QUrl("about:blank"), "Home")

        # Startup par background update check.
        self.check_for_updates(silent=True)

    # ================ DASHBOARD ================

    def dashboard_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport"
                  content="width=device-width, initial-scale=1">
            <title>Nexus-V Home</title>
            <style>
                body {
                    background: #202124;
                    color: white;
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 100px 20px;
                }
                h1 {
                    color: #8ab4f8;
                    font-size: 46px;
                }
                p {
                    color: #bdc1c6;
                }
                input {
                    box-sizing: border-box;
                    width: 90%;
                    max-width: 600px;
                    padding: 14px;
                    border-radius: 25px;
                    border: 1px solid #777;
                    font-size: 16px;
                }
                a {
                    color: #8ab4f8;
                    margin: 12px;
                    text-decoration: none;
                }
            </style>
        </head>
        <body>
            <h1>Nexus-V Browser</h1>
            <p>Welcome to your browsing experience.</p>

            <form action="https://duckduckgo.com/" method="get">
                <input name="q" placeholder="Search the web...">
            </form>

            <p>
                <a href="https://google.com">Google</a>
                <a href="https://github.com">GitHub</a>
                <a href="https://youtube.com">YouTube</a>
            </p>
        </body>
        </html>
        """

    def build_dashboard(self):
        browser = QWebEngineView()
        browser.setHtml(self.dashboard_html())
        return browser

    # ================ TAB MANAGEMENT ================

    def add_new_tab(self, url=None, title="New Tab"):
        if url is None or url.toString() == "about:blank":
            browser = self.build_dashboard()
        else:
            browser = QWebEngineView()
            browser.setUrl(url)

        browser.urlChanged.connect(
            lambda qurl, b=browser:
            self.update_url_bar(qurl, b)
        )

        browser.titleChanged.connect(
            lambda page_title, b=browser:
            self.update_tab_title(b, page_title)
        )

        browser.loadProgress.connect(self.update_progress)
        browser.loadFinished.connect(self.load_finished)

        index = self.tabs.addTab(browser, title)
        self.tabs.setCurrentIndex(index)

    def add_new_blank_tab(self):
        self.add_new_tab(QUrl("about:blank"), "New Tab")

    def current_browser(self):
        widget = self.tabs.currentWidget()

        if isinstance(widget, QWebEngineView):
            return widget

        return None

    def close_tab(self, index):
        if self.tabs.count() <= 1:
            self.go_home()
            return

        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)

        if widget is not None:
            widget.deleteLater()

    # ================ NAVIGATION ================

    def navigate_to_url(self):
        text = self.url_bar.text().strip()

        if not text:
            return

        if " " in text or (
            "." not in text and text.lower() != "localhost"
        ):
            url = QUrl(
                "https://duckduckgo.com/?q="
                + quote_plus(text)
            )
        else:
            url = QUrl.fromUserInput(text)

        browser = self.current_browser()

        if browser:
            browser.setUrl(url)
        else:
            self.add_new_tab(url)

    def go_back(self):
        browser = self.current_browser()
        if browser:
            browser.back()

    def go_forward(self):
        browser = self.current_browser()
        if browser:
            browser.forward()

    def reload_page(self):
        browser = self.current_browser()
        if browser:
            browser.reload()

    def go_home(self):
        browser = self.current_browser()

        if browser:
            browser.setHtml(self.dashboard_html())
        else:
            self.add_new_tab(QUrl("about:blank"), "Home")

    # ================ URL AND PROGRESS ================

    def update_url_bar(self, url, browser):
        if self.tabs.currentWidget() == browser:
            if url.toString() == "about:blank":
                self.url_bar.clear()
            else:
                self.url_bar.setText(url.toString())

    def update_tab_title(self, browser, title):
        index = self.tabs.indexOf(browser)

        if index != -1 and title:
            self.tabs.setTabText(index, title[:20])

    def tab_changed(self, index):
        browser = self.tabs.widget(index)

        if isinstance(browser, QWebEngineView):
            url = browser.url().toString()

            if url and url != "about:blank":
                self.url_bar.setText(url)
            else:
                self.url_bar.clear()

    def update_progress(self, progress):
        self.progress_bar.setValue(progress)

    def load_finished(self, success):
        self.progress_bar.setValue(0)

        if not success:
            print(
                "Page load failed. Check URL and internet connection."
            )

    # ================ BOOKMARKS ================

    def add_current_bookmark(self):
        browser = self.current_browser()

        if browser is None:
            return

        url = browser.url().toString()

        if not url or url == "about:blank":
            QMessageBox.information(
                self,
                "Bookmark",
                "Open a website before adding a bookmark."
            )
            return

        if url not in self.bookmarks:
            self.bookmarks.append(url)
            self.bookmark_menu.addItem(url)

    def open_bookmark(self, index):
        if index <= 0:
            return

        url = self.bookmark_menu.itemText(index)
        browser = self.current_browser()

        if browser and url:
            browser.setUrl(QUrl(url))

        self.bookmark_menu.setCurrentIndex(0)

    # ================ UPDATE CHECKER ================

    def check_for_updates(self, silent=False):
        self._update_silent = silent
        if not GITHUB_REPO:
            if not silent:
                QMessageBox.information(
                    self, "GitHub setup required",
                    "Pehle GitHub par repository banayein, phir GITHUB_REPO mein "
                    "'username/repository-name' set karein. Repository mein "
                    "browser.py aur version.txt dono files honi chahiye."
                )
            return
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking...")
        self.update_thread = UpdateWorker()
        self.update_thread.update_signal.connect(self.handle_update_result)
        self.update_thread.finished.connect(self.restore_update_button)
        self.update_thread.start()

    def restore_update_button(self):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Update")

    @staticmethod
    def version_tuple(version):
        try:
            return tuple(int(part) for part in version.strip().lstrip("vV").split("."))
        except (ValueError, AttributeError):
            return ()

    def handle_update_result(self, latest_version):
        latest_version = latest_version.strip()
        if not latest_version:
            if not getattr(self, "_update_silent", False):
                QMessageBox.warning(
                    self, "Update check failed",
                    "GitHub se version nahi mila. Repository aur version.txt check karein."
                )
            return
        current = self.version_tuple(CURRENT_VERSION)
        latest = self.version_tuple(latest_version)

        if not latest:
            if not getattr(self, "_update_silent", False):
                QMessageBox.warning(self, "Update", "Version file ka format sahi nahi hai.")
            return

        if latest <= current:
            if not getattr(self, "_update_silent", False):
                QMessageBox.information(
                    self, "Nexus-V Update",
                    f"Aapka browser latest version par hai. (v{CURRENT_VERSION})"
                )
            return

        reply = QMessageBox.question(
            self, "Nexus-V Update Available",
            f"New version available: v{latest_version}\\n"
            f"Current version: v{CURRENT_VERSION}\\n\\n"
            "Kya aap abhi update install karna chahte hain?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        if not RAW_SCRIPT_URL:
            QMessageBox.information(
                self, "GitHub URL required",
                "Update check kaam kar raha hai, lekin automatic install ke liye "
                "browser.py ka GitHub RAW URL set karna baaki hai. "
                "Repository banne ke baad RAW_SCRIPT_URL configure karein."
            )
            return

        self.update_btn.setEnabled(False)
        self.update_btn.setText("Updating...")
        self.install_thread = UpdateInstallWorker()
        self.install_thread.finished_signal.connect(self.finish_update_install)
        self.install_thread.start()

    def finish_update_install(self, success, message):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Update")
        if not success:
            QMessageBox.warning(self, "Update failed", message)
            return

        reply = QMessageBox.information(
            self, "Update installed",
            "Update file install ho gayi hai. Browser ko restart karna hoga.\\n\\n"
            "Restart now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            try:
                script_path = str(Path(__file__).resolve())
                subprocess.Popen([sys.executable, script_path])
                QApplication.quit()
            except Exception as error:
                QMessageBox.warning(
                    self, "Restart failed",
                    f"Update install ho gayi, lekin restart nahi hua: {error}\\n"
                    "Browser ko manually band karke dobara chalao."
                )


# ================ START APPLICATION ================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = NexusVBrowser()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
