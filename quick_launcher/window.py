from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icon_service import IconService
from .models import AppEntry, LauncherConfig
from .search import filter_apps


class AppCard(QToolButton):
    def __init__(self, app: AppEntry, icon_service: IconService) -> None:
        super().__init__()
        self.app = app
        self.setObjectName("appCard")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIcon(icon_service.icon_for(app))
        self.setIconSize(QSize(48, 48))
        self.setText(app.name)
        self.setMinimumSize(116, 104)
        self.setMaximumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class LauncherWindow(QMainWindow):
    app_requested = Signal(object)
    launcher_hidden = Signal()

    def __init__(self, config: LauncherConfig, icon_service: IconService) -> None:
        super().__init__()
        self._config = config
        self._icon_service = icon_service
        self._category_id: str | None = None
        self._cards: list[AppCard] = []
        self._quitting = False

        self.setWindowTitle("Quick Launcher")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(720, 460)
        self.resize(780, 520)
        self._build_ui()
        self._render_apps()

    def _build_ui(self) -> None:
        surface = QFrame()
        surface.setObjectName("surface")
        root = QVBoxLayout(surface)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        heading = QHBoxLayout()
        title = QLabel("快速启动")
        title.setObjectName("title")
        hint = QLabel("Win + Alt + Space")
        hint.setObjectName("hotkeyHint")
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(hint)
        root.addLayout(heading)

        self._search = QLineEdit()
        self._search.setObjectName("search")
        self._search.setPlaceholderText("搜索应用…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._render_apps)
        self._search.installEventFilter(self)
        root.addWidget(self._search)

        content = QHBoxLayout()
        content.setSpacing(18)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(118)
        self._sidebar_layout = QVBoxLayout(sidebar)
        self._sidebar_layout.setContentsMargins(9, 9, 9, 9)
        self._sidebar_layout.setSpacing(5)
        self._category_buttons = QButtonGroup(self)
        self._category_buttons.setExclusive(True)
        self._add_category_button("全部", None, checked=True)
        for category in self._config.categories:
            self._add_category_button(category.name, category.id)
        self._sidebar_layout.addStretch()
        content.addWidget(sidebar)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(0, 0, 8, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._empty = QLabel("没有匹配的应用")
        self._empty.setObjectName("empty")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.hide()

        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self._grid_widget)
        grid_layout.addWidget(self._empty)
        grid_layout.addStretch()
        scroll = QScrollArea()
        scroll.setObjectName("appScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(grid_container)
        content.addWidget(scroll, 1)
        root.addLayout(content, 1)

        self._status = QLabel("")
        self._status.setObjectName("status")
        self._status.hide()
        root.addWidget(self._status)
        self.setCentralWidget(surface)
        self.setStyleSheet(_STYLE)

    def _add_category_button(self, label: str, category_id: str | None, checked: bool = False) -> None:
        button = QToolButton()
        button.setText(label)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setProperty("category_id", category_id)
        button.clicked.connect(lambda: self._select_category(category_id))
        self._category_buttons.addButton(button)
        self._sidebar_layout.insertWidget(self._sidebar_layout.count() - 1, button)

    def _select_category(self, category_id: str | None) -> None:
        self._category_id = category_id
        self._render_apps()

    def _render_apps(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._cards.clear()
        apps = filter_apps(self._config.apps, self._category_id, self._search.text())
        self._empty.setVisible(not apps)
        for index, app in enumerate(apps):
            card = AppCard(app, self._icon_service)
            card.clicked.connect(lambda checked=False, selected=app: self.app_requested.emit(selected))
            self._cards.append(card)
            self._grid.addWidget(card, index // 4, index % 4)

    def prepare_to_show(self, position: QPoint) -> None:
        self._status.hide()
        self.move(position)
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus()
        self._search.selectAll()

    def show_error(self, message: str) -> None:
        self._status.setText(message)
        self._status.show()

    def hide_launcher(self) -> None:
        was_visible = self.isVisible()
        self.hide()
        if was_visible:
            self.launcher_hidden.emit()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._search and event.type() == QEvent.Type.KeyPress:
            key_event = event  # Runtime type is QKeyEvent after the type check.
            if isinstance(key_event, QKeyEvent):
                if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._cards:
                    self.app_requested.emit(self._cards[0].app)
                    return True
                if key_event.key() == Qt.Key.Key_Down and self._cards:
                    self._cards[0].setFocus()
                    return True
                if key_event.key() == Qt.Key.Key_Escape:
                    self.hide_launcher()
                    return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_launcher()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QEvent) -> None:
        super().focusOutEvent(event)
        QTimer.singleShot(80, self._hide_if_inactive)

    def _hide_if_inactive(self) -> None:
        if not self._quitting and self.isVisible() and not self.isActiveWindow():
            self.hide_launcher()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
        else:
            self.hide_launcher()
            event.ignore()

    def allow_quit(self) -> None:
        self._quitting = True


_STYLE = """
QFrame#surface {
    background: #F4F8EE;
    border: 1px solid #C9D9BB;
    border-radius: 18px;
}
QLabel#title { color: #2F3D2A; font-size: 22px; font-weight: 700; }
QLabel#hotkeyHint {
    color: #557146; background: #D7EAC5; border-radius: 9px;
    padding: 6px 10px; font-size: 12px; font-weight: 600;
}
QLineEdit#search {
    background: #FFFFFF; color: #2F3D2A; border: 1px solid #C9D9BB;
    border-radius: 11px; padding: 11px 13px; font-size: 14px;
}
QLineEdit#search:focus { border: 2px solid #789A63; }
QFrame#sidebar { background: #E8F2DD; border-radius: 12px; }
QToolButton {
    color: #52604B; border: none; border-radius: 8px; padding: 9px 7px;
    font-size: 14px; text-align: left;
}
QToolButton:hover { background: #D7EAC5; color: #2F3D2A; }
QToolButton:checked { background: #789A63; color: white; font-weight: 700; }
QToolButton#appCard {
    background: #FFFFFF; color: #2F3D2A; border: 1px solid #D7E4CC;
    border-radius: 12px; padding: 10px 6px;
}
QToolButton#appCard:hover, QToolButton#appCard:focus {
    background: #EDF6E4; border: 2px solid #789A63;
}
QScrollArea#appScroll { background: transparent; }
QLabel#empty { color: #6D7A65; padding: 40px; }
QLabel#status { color: #A13F3F; background: #FBEAEA; border-radius: 8px; padding: 7px 10px; }
"""
