from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .categories import category_scope, is_uncategorized, validate_category_layout
from .icon_service import IconService
from .models import AppEntry, Category, LauncherConfig
from .search import filter_apps
from .ui_theme import ThemeTransition, bundled_icon, colors, themed_icon


class DragBar(QFrame):
    """A small top-right drag handle for the frameless launcher window."""

    def __init__(self) -> None:
        super().__init__()
        self._drag_offset: QPoint | None = None
        self.setObjectName("moveHandle")
        self.setFixedSize(34, 30)
        self.setToolTip("拖动窗口")
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("⠿")
        label.setObjectName("moveHandleIcon")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(label)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            handle = window.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class BottomLeftResizeGrip(QFrame):
    """Invisible at rest; shows thin green arcs while hovered or dragged."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start_position: QPoint | None = None
        self._start_geometry: QRect | None = None
        self._active = False
        self.setObjectName("bottomLeftResizeGrip")
        self.setFixedSize(30, 30)
        self.setToolTip("拖动调整窗口大小")
        self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._pen_color = QColor("#466339")

    def set_theme(self, theme: str) -> None:
        self._pen_color = QColor(colors(theme)["accent_dark"])
        self.update()

    def enterEvent(self, event: QEvent) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.underMouse() and not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self._pen_color, 1.6))
        painter.drawArc(QRectF(-9, 10, 28, 28), 0, 90 * 16)
        painter.drawArc(QRectF(-4, 15, 18, 18), 0, 90 * 16)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._active = True
            self.update()
            window = self.window()
            handle = window.windowHandle()
            edges = Qt.Edge.LeftEdge | Qt.Edge.BottomEdge
            if handle is not None and handle.startSystemResize(edges):
                event.accept()
                return
            self._start_position = event.globalPosition().toPoint()
            self._start_geometry = window.geometry()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._start_position is not None
            and self._start_geometry is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            window = self.window()
            delta = event.globalPosition().toPoint() - self._start_position
            new_width = max(window.minimumWidth(), self._start_geometry.width() - delta.x())
            new_height = max(window.minimumHeight(), self._start_geometry.height() + delta.y())
            right = self._start_geometry.x() + self._start_geometry.width()
            window.setGeometry(
                right - new_width,
                self._start_geometry.y(),
                new_width,
                new_height,
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_position = None
            self._start_geometry = None
            self._active = False
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class AppCard(QToolButton):
    context_requested = Signal(object, object)

    def __init__(self, app: AppEntry, icon_service: IconService, icon_size: int) -> None:
        super().__init__()
        self.app = app
        self.setObjectName("appCard")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIcon(icon_service.icon_for(app))
        self.setIconSize(QSize(icon_size, icon_size))
        self.setText(app.name)
        self.setMinimumSize(max(104, icon_size + 56), icon_size + 58)
        self.setMaximumWidth(max(150, icon_size + 76))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda position: self.context_requested.emit(self.app, self.mapToGlobal(position))
        )

    def set_icon_size(self, icon_size: int) -> None:
        self.setIconSize(QSize(icon_size, icon_size))
        self.setMinimumSize(max(104, icon_size + 56), icon_size + 58)
        self.setMaximumWidth(max(150, icon_size + 76))


class CategorySidebar(QTreeWidget):
    """Flat-looking two-level category tree with validated internal moves."""

    selection_requested = Signal(object)
    context_requested = Signal(object, object)
    blank_context_requested = Signal(object)
    layout_candidate = Signal(object)
    layout_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("categoryTree")
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setIndentation(14)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.itemClicked.connect(self._emit_selection)
        self.customContextMenuRequested.connect(self._show_context)
        self._categories: tuple[Category, ...] = ()

    def populate(self, categories: tuple[Category, ...], selected_id: str | None) -> None:
        self._categories = categories
        self.clear()
        all_item = QTreeWidgetItem(["全部"])
        all_item.setData(0, Qt.ItemDataRole.UserRole, None)
        all_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.addTopLevelItem(all_item)
        by_id: dict[str, QTreeWidgetItem] = {}
        for category in categories:
            if category.parent_id is not None:
                continue
            item = self._make_item(category)
            self.addTopLevelItem(item)
            by_id[category.id] = item
        for category in categories:
            if category.parent_id is None:
                continue
            parent = by_id.get(category.parent_id)
            if parent is None:
                continue
            item = self._make_item(category)
            parent.addChild(item)
            by_id[category.id] = item
        self.expandAll()
        selected = all_item if selected_id is None else by_id.get(selected_id, all_item)
        self.setCurrentItem(selected)

    @staticmethod
    def _make_item(category: Category) -> QTreeWidgetItem:
        item = QTreeWidgetItem([category.name])
        item.setData(0, Qt.ItemDataRole.UserRole, category.id)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        if category.parent_id is None and not is_uncategorized(category.id, category.name):
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        item.setFlags(flags)
        return item

    def _emit_selection(self, item: QTreeWidgetItem) -> None:
        self.selection_requested.emit(item.data(0, Qt.ItemDataRole.UserRole))

    def _show_context(self, position: QPoint) -> None:
        item = self.itemAt(position)
        global_position = self.viewport().mapToGlobal(position)
        category_id = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if item is None or category_id is None:
            self.blank_context_requested.emit(global_position)
        else:
            self.context_requested.emit(global_position, category_id)

    def categories(self) -> tuple[Category, ...]:
        categories: list[Category] = []
        for index in range(1, self.topLevelItemCount()):
            parent = self.topLevelItem(index)
            parent_id = str(parent.data(0, Qt.ItemDataRole.UserRole))
            categories.append(Category(parent_id, parent.text(0)))
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                categories.append(
                    Category(str(child.data(0, Qt.ItemDataRole.UserRole)), child.text(0), parent_id)
                )
        return tuple(categories)

    def dropEvent(self, event: QDropEvent) -> None:
        dragged = self.currentItem()
        if dragged is None or dragged.data(0, Qt.ItemDataRole.UserRole) is None:
            event.ignore()
            return
        snapshot = self._categories
        selected_id = str(dragged.data(0, Qt.ItemDataRole.UserRole))
        target = self.itemAt(event.position().toPoint())
        on_item = self.dropIndicatorPosition() == QAbstractItemView.DropIndicatorPosition.OnItem
        if on_item and target is not None:
            target_id = target.data(0, Qt.ItemDataRole.UserRole)
            if target_id is None or is_uncategorized(str(target_id), target.text(0)):
                event.ignore()
                return
            if dragged.childCount() > 0 or is_uncategorized(selected_id, dragged.text(0)):
                event.ignore()
                return
        super().dropEvent(event)
        candidate = self.categories()
        error = validate_category_layout(snapshot, candidate)
        if error:
            self.populate(snapshot, selected_id)
            self.layout_error.emit(error)
            return
        self._categories = candidate
        self.layout_candidate.emit(candidate)


class LauncherWindow(QMainWindow):
    app_requested = Signal(object)
    app_context_requested = Signal(object, object)
    background_context_requested = Signal(object, object)
    category_context_requested = Signal(object, object)
    sidebar_context_requested = Signal(object)
    files_dropped = Signal(object, object)
    launcher_hidden = Signal()
    settings_requested = Signal()
    theme_toggle_requested = Signal()
    categories_reordered = Signal(object)
    position_changed = Signal(object)

    def __init__(self, config: LauncherConfig, icon_service: IconService) -> None:
        super().__init__()
        self._config = config
        self._icon_service = icon_service
        self._category_id: str | None = None
        self._cards: list[AppCard] = []
        self._quitting = False
        self._relayout_pending = False
        self._hide_on_focus_lost = config.settings.hide_on_focus_lost
        self._preview_icon_size: int | None = None
        self._programmatic_move = False
        self._theme_transition = ThemeTransition(self)
        self._position_timer = QTimer(self)
        self._position_timer.setSingleShot(True)
        self._position_timer.setInterval(250)
        self._position_timer.timeout.connect(lambda: self.position_changed.emit(self.pos()))

        self.setWindowTitle("速拾")
        self.setObjectName("launcherWindow")
        self.setWindowIcon(bundled_icon("sushi-organizer.exe.ico"))
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(config.settings.window_opacity)
        self.setAutoFillBackground(False)
        self.setAcceptDrops(True)
        self.setMinimumSize(720, 460)
        self.resize(780, 520)
        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._render_apps()

    def _build_ui(self) -> None:
        self._surface = QFrame()
        self._surface.setObjectName("surface")
        self._surface.setProperty("dropActive", False)
        self._surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QVBoxLayout(self._surface)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        heading = QHBoxLayout(title_bar)
        heading.setContentsMargins(0, 0, 0, 0)
        title = QLabel("速拾")
        title.setObjectName("title")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._theme_button = QToolButton()
        self._theme_button.setObjectName("themeButton")
        self._theme_button.setAccessibleName("切换亮暗模式")
        self._theme_button.clicked.connect(self.theme_toggle_requested)
        self._settings_button = QToolButton()
        self._settings_button.setObjectName("settingsButton")
        self._settings_button.setText("设置")
        self._settings_button.clicked.connect(self.settings_requested)
        self._minimize_button = QToolButton()
        self._minimize_button.setObjectName("minimizeButton")
        self._minimize_button.setToolTip("隐藏到托盘")
        self._minimize_button.setAccessibleName("最小化到托盘")
        self._minimize_button.clicked.connect(self.hide_launcher)
        heading.addWidget(title)
        heading.addWidget(self._theme_button)
        heading.addStretch()
        heading.addWidget(DragBar())
        heading.addWidget(self._settings_button)
        heading.addWidget(self._minimize_button)
        root.addWidget(title_bar)

        self._search = QLineEdit()
        self._search.setObjectName("search")
        self._search.setPlaceholderText("搜索应用…")
        self._search.setClearButtonEnabled(True)
        self._search.setAcceptDrops(False)
        self._search.textChanged.connect(self._render_apps)
        self._search.installEventFilter(self)
        root.addWidget(self._search)

        content = QHBoxLayout()
        content.setSpacing(18)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(142)
        self._sidebar_layout = QVBoxLayout(sidebar)
        self._sidebar_layout.setContentsMargins(9, 9, 9, 9)
        self._sidebar_layout.setSpacing(5)
        self._category_tree = CategorySidebar()
        self._category_tree.populate(self._config.categories, self._category_id)
        self._category_tree.selection_requested.connect(self._select_category)
        self._category_tree.context_requested.connect(self.category_context_requested)
        self._category_tree.blank_context_requested.connect(self.sidebar_context_requested)
        self._category_tree.layout_candidate.connect(self.categories_reordered)
        self._category_tree.layout_error.connect(self.show_error)
        self._sidebar_layout.addWidget(self._category_tree, 1)
        category_settings_button = QToolButton()
        category_settings_button.setObjectName("categorySettingsButton")
        category_settings_button.setText("编辑分类")
        category_settings_button.clicked.connect(self.settings_requested)
        self._sidebar_layout.addWidget(category_settings_button)
        content.addWidget(sidebar)

        self._grid_widget = QWidget()
        self._grid_widget.setObjectName("gridWidget")
        self._enable_background_context(self._grid_widget)
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
        grid_container.setObjectName("gridContainer")
        self._enable_background_context(grid_container)
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self._grid_widget)
        grid_layout.addWidget(self._empty)
        grid_layout.addStretch()
        self._scroll = QScrollArea()
        self._scroll.setObjectName("appScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.viewport().setObjectName("appViewport")
        self._scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._scroll.viewport().installEventFilter(self)
        self._enable_background_context(self._scroll.viewport())
        self._scroll.setWidget(grid_container)
        content.addWidget(self._scroll, 1)
        root.addLayout(content, 1)

        self._status = QLabel("")
        self._status.setObjectName("status")
        self._status.hide()
        root.addWidget(self._status)
        self.setCentralWidget(self._surface)
        self._resize_grip = BottomLeftResizeGrip(self)
        self._position_resize_grip()
        self._resize_grip.raise_()
        self.apply_theme(self._config.settings.theme)

    @property
    def settings(self):
        return self._config.settings

    def apply_config(
        self,
        config: LauncherConfig,
        *,
        animate_theme: bool = False,
        theme_prepare: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._hide_on_focus_lost = config.settings.hide_on_focus_lost
        self._preview_icon_size = None
        valid_ids = {category.id for category in config.categories}
        if self._category_id not in valid_ids:
            self._category_id = None
        self._category_tree.populate(config.categories, self._category_id)
        self.apply_theme(
            config.settings.theme,
            animated=animate_theme,
            prepare=theme_prepare,
        )
        self.setWindowOpacity(config.settings.window_opacity)
        self._render_apps()

    def _select_category(self, category_id: str | None) -> None:
        self._category_id = category_id
        self._render_apps()

    def preview_icon_size(self, icon_size: int) -> None:
        self._preview_icon_size = icon_size
        for card in self._cards:
            card.set_icon_size(icon_size)
        self._schedule_relayout()

    def preview_theme(self, theme: str, *, prepare: Callable[[], None] | None = None) -> None:
        self.apply_theme(theme, animated=True, prepare=prepare)

    def preview_window_opacity(self, opacity: float) -> None:
        self.setWindowOpacity(opacity)

    def apply_theme(
        self,
        theme: str,
        *,
        animated: bool = False,
        prepare: Callable[[], None] | None = None,
    ) -> None:
        def apply() -> None:
            if prepare is not None:
                prepare()
            self.setProperty("theme", theme)
            self.setStyleSheet(_window_style(theme))
            self._theme_button.setIcon(
                themed_icon("bulb-off" if theme == "dark" else "bulb", theme)
            )
            self._theme_button.setIconSize(QSize(20, 20))
            self._theme_button.setToolTip(
                "切换到亮色模式" if theme == "dark" else "切换到暗色模式"
            )
            self._settings_button.setIcon(themed_icon("settings", theme, 16))
            self._settings_button.setIconSize(QSize(16, 16))
            self._minimize_button.setIcon(themed_icon("minus", theme, 18))
            self._minimize_button.setIconSize(QSize(18, 18))
            self._resize_grip.set_theme(theme)

        if animated and self.property("theme") != theme:
            self._theme_transition.apply(apply)
        else:
            apply()

    def _render_apps(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
                item.widget().deleteLater()
        self._cards.clear()
        apps = filter_apps(
            self._config.apps,
            self._category_id,
            self._search.text(),
            category_scope(self._config.categories, self._category_id),
        )
        self._empty.setVisible(not apps)
        for app in apps:
            icon_size = self._preview_icon_size or self._config.settings.icon_size
            card = AppCard(app, self._icon_service, icon_size)
            card.clicked.connect(lambda checked=False, selected=app: self.app_requested.emit(selected))
            card.context_requested.connect(self.app_context_requested)
            self._cards.append(card)
        self._relayout_cards()

    def _schedule_relayout(self) -> None:
        if self._relayout_pending:
            return
        self._relayout_pending = True
        QTimer.singleShot(0, self._relayout_cards)

    def _relayout_cards(self) -> None:
        self._relayout_pending = False
        while self._grid.count():
            self._grid.takeAt(0)
        if not self._cards:
            return
        card_width = max(card.minimumWidth() for card in self._cards)
        spacing = self._grid.horizontalSpacing()
        available_width = max(card_width, self._scroll.viewport().width() - 8)
        columns = max(1, (available_width + spacing) // (card_width + spacing))
        for index, card in enumerate(self._cards):
            self._grid.addWidget(card, index // columns, index % columns)

    def prepare_to_show(self, position: QPoint) -> None:
        self._status.hide()
        self._programmatic_move = True
        self.move(position)
        self._programmatic_move = False
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus()
        self._search.selectAll()

    def show_error(self, message: str) -> None:
        self.show_status(message, "error")

    def show_status(self, message: str, kind: str = "success") -> None:
        self._status.setText(message)
        self._status.setProperty("kind", kind)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.show()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_resize_grip()
        self._schedule_relayout()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        if (
            self.isVisible()
            and self._config.settings.remember_window_position
            and not self._programmatic_move
        ):
            self._position_timer.start()

    def _position_resize_grip(self) -> None:
        if not hasattr(self, "_resize_grip"):
            return
        self._resize_grip.move(2, max(0, self.height() - self._resize_grip.height() - 2))
        self._resize_grip.raise_()

    def _enable_background_context(self, widget: QWidget) -> None:
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda position, source=widget: self.background_context_requested.emit(
                source.mapToGlobal(position), self._category_id
            )
        )

    @staticmethod
    def _local_drop_paths(mime_data: QMimeData) -> tuple[str, ...]:
        return tuple(url.toLocalFile() for url in mime_data.urls() if url.isLocalFile())

    def _set_drop_active(self, active: bool) -> None:
        if self._surface.property("dropActive") == active:
            return
        self._surface.setProperty("dropActive", active)
        self._surface.style().unpolish(self._surface)
        self._surface.style().polish(self._surface)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._local_drop_paths(event.mimeData()):
            self._set_drop_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drop_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._local_drop_paths(event.mimeData())
        self._set_drop_active(False)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.files_dropped.emit(paths, self._category_id)

    def hide_launcher(self) -> None:
        was_visible = self.isVisible()
        self.hide()
        if was_visible:
            self.launcher_hidden.emit()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if (
            watched is QApplication.instance()
            and event.type() == QEvent.Type.ApplicationDeactivate
            and self._hide_on_focus_lost
        ):
            QTimer.singleShot(80, self._hide_if_inactive)
        if (
            hasattr(self, "_scroll")
            and watched is self._scroll.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._schedule_relayout()
        if watched is self._search and event.type() == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent):
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._cards:
                    self.app_requested.emit(self._cards[0].app)
                    return True
                if event.key() == Qt.Key.Key_Down and self._cards:
                    self._cards[0].setFocus()
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self.hide_launcher()
                    return True
        return super().eventFilter(watched, event)

    def event(self, event: QEvent) -> bool:
        result = super().event(event)
        if event.type() == QEvent.Type.WindowDeactivate and self._hide_on_focus_lost:
            QTimer.singleShot(80, self._hide_if_inactive)
        return result

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_launcher()
            event.accept()
            return
        super().keyPressEvent(event)

    def _hide_if_inactive(self) -> None:
        if QApplication.activePopupWidget() is not None or QApplication.activeModalWidget() is not None:
            QTimer.singleShot(120, self._hide_if_inactive)
            return
        if (
            self._hide_on_focus_lost
            and not self._quitting
            and self.isVisible()
            and not self.isActiveWindow()
        ):
            self.hide_launcher()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
        else:
            self.hide_launcher()
            event.ignore()

    def allow_quit(self) -> None:
        self._quitting = True
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)


def _window_style(theme: str) -> str:
    c = colors(theme)
    style = """
QMainWindow#launcherWindow { background: transparent; }
QMainWindow#launcherWindow QWidget { background-color: @surface@; color: @text@; }
QFrame#surface { background: @surface@; border: 1px solid @border@; border-radius: 20px; }
QFrame#titleBar { background-color: @surface@; border: none; }
QLabel#title { color: @text@; font-size: 22px; font-weight: 700; }
QFrame#moveHandle { color: @accent_dark@; background: @sidebar@; border: 1px solid @border@; border-radius: 8px; }
QFrame#moveHandle:hover { background: @hover@; }
QLabel#moveHandleIcon { background: transparent; color: @accent_dark@; }
QFrame#bottomLeftResizeGrip { background: transparent; border: none; }
QToolButton#settingsButton, QToolButton#themeButton {
    color: @accent_dark@; background: transparent; border: 1px solid @border@;
    border-radius: 8px; padding: 6px 10px; font-size: 12px;
}
QToolButton#settingsButton:hover, QToolButton#themeButton:hover { background: @hover@; }
QToolButton#minimizeButton {
    color: @accent_dark@; background: transparent; border: 1px solid @border@;
    border-radius: 8px; padding: 6px 11px;
}
QToolButton#minimizeButton:hover { background: @hover@; }
QFrame#surface[dropActive="true"] { border: 3px solid @accent@; }
QToolButton#categorySettingsButton {
    color: @accent_dark@; background: @hover@; border: none;
    border-radius: 7px; padding: 7px 5px; font-size: 12px;
}
QToolButton#categorySettingsButton:hover { background: @accent_soft@; }
QLineEdit#search {
    background: @input@; color: @text@; border: 1px solid @border@;
    border-radius: 11px; padding: 11px 13px; font-size: 14px;
}
QLineEdit#search:focus { border: 2px solid @accent@; }
QFrame#sidebar { background: @sidebar@; border-radius: 12px; }
QTreeWidget#categoryTree { background: transparent; color: @text@; border: none; outline: none; }
QTreeWidget#categoryTree::item { border: none; border-radius: 8px; padding: 8px 7px; min-height: 20px; }
QTreeWidget#categoryTree::item:hover { background: @hover@; }
QTreeWidget#categoryTree::item:selected { background: @accent@; color: white; font-weight: 700; }
QTreeWidget#categoryTree::branch { background: transparent; }
QToolButton { color: @text@; border: none; border-radius: 8px; padding: 9px 7px; font-size: 14px; text-align: left; }
QToolButton:hover { background: @hover@; color: @text@; }
QToolButton#appCard { background: @card@; color: @text@; border: 1px solid @border@; border-radius: 12px; padding: 10px 6px; }
QToolButton#appCard:hover, QToolButton#appCard:focus { background: @hover@; border: 2px solid @accent@; }
QScrollArea#appScroll { background-color: @surface@; border: none; }
QWidget#appViewport, QWidget#gridContainer, QWidget#gridWidget { background-color: @surface@; }
QScrollBar:vertical { background: @sidebar@; width: 9px; border-radius: 4px; }
QScrollBar::handle:vertical { background: @accent_soft@; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel#empty { color: @muted@; padding: 40px; }
QLabel#status { border-radius: 8px; padding: 7px 10px; }
QLabel#status[kind="error"] { color: @error@; background: @error_bg@; }
QLabel#status[kind="success"] { color: @success@; background: @success_bg@; }
"""
    for name, value in c.items():
        style = style.replace(f"@{name}@", value)
    return style
