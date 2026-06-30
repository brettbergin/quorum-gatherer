"""Dark theme QSS, mirroring the web app's palette."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

DARK_QSS = """
QWidget { background: #0f1115; color: #e6e8ec; font-size: 13px; }
QMainWindow, QDialog { background: #0f1115; }

QPushButton { background:#1d212b; border:1px solid #2a2f3a; border-radius:8px; padding:7px 12px; }
QPushButton:hover { border-color:#5b8def; }
QPushButton:disabled { color:#5a6172; border-color:#23272f; }
QPushButton#primary { background:#5b8def; border-color:#5b8def; color:white; font-weight:600; }
QPushButton#primary:hover { background:#6ea8fe; }

QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox {
  background:#171a21; border:1px solid #2a2f3a; border-radius:8px; padding:6px 8px;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border-color:#5b8def; }
QComboBox::drop-down { border: none; }
QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled { color:#5a6172; background:#13161c; }
QSpinBox::up-button, QSpinBox::down-button { width:14px; border:none; background:transparent; }

QCheckBox { spacing:6px; }
QCheckBox::indicator {
  width:15px; height:15px; border:1px solid #2a2f3a; border-radius:4px; background:#171a21;
}
QCheckBox::indicator:checked { background:#5b8def; border-color:#5b8def; }

QListWidget { background:#171a21; border:1px solid #2a2f3a; border-radius:10px; padding:4px; }
QListWidget::item { padding:8px; border-radius:6px; }
QListWidget::item:selected { background:#1d212b; border:1px solid #5b8def; }

/* settings modal navigation rail */
QListWidget#settingsNav {
  border:none; border-right:1px solid #2a2f3a; border-radius:0; padding:8px;
}
QListWidget#settingsNav::item { padding:10px 12px; margin:2px 0; }
QListWidget#settingsNav::item:selected { background:#1d212b; border:1px solid #2a2f3a; }

QFrame#card { background:#171a21; border:1px solid #2a2f3a; border-radius:12px; }

/* chat bubbles */
QFrame#agentBubble { background:#171a21; border:1px solid #2a2f3a; border-radius:12px; }
QFrame#userBubble { background:#1e3250; border:1px solid #355b8c; border-radius:12px; }
QLabel#muted { color:#8b93a3; }
QLabel#agentName { font-weight:700; }
QLabel#chairTitle { font-weight:700; font-size:18px; }

QLabel#badge {
  color:#8b93a3; border:1px solid #2a2f3a; border-radius:9px; padding:1px 7px; font-size:10px;
}
QLabel#badge[state="running"] { color:#e0b34a; border-color:#e0b34a; }
QLabel#badge[state="completed"] { color:#46c66b; border-color:#46c66b; }
QLabel#badge[state="failed"] { color:#e5675f; border-color:#e5675f; }
QLabel#badge[state="enabled"] { color:#46c66b; border-color:#46c66b; }
QLabel#badge[state="valid"] { color:#5b8def; border-color:#5b8def; }
QLabel#badge[state="disabled"] { color:#e0b34a; border-color:#e0b34a; }

QLabel#statusLine[state="ok"] { color:#46c66b; }
QLabel#statusLine[state="error"] { color:#e5675f; }
QLabel#statusLine[state="applying"] { color:#e0b34a; }

QScrollArea { border:none; background:#0f1115; }
QScrollBar:vertical { background:#0f1115; width:10px; }
QScrollBar::handle:vertical { background:#2a2f3a; border-radius:5px; }
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(DARK_QSS)
