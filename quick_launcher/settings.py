from __future__ import annotations

import uuid
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QDropEvent, QKeySequence, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QKeySequenceEdit,
    QLabel, QLineEdit, QProgressBar, QPushButton, QSlider, QTabWidget,
    QToolButton, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QVBoxLayout, QWidget,
)

from .categories import is_uncategorized, validate_category_layout
from .hotcorner_preview import HotCornerPreview
from .models import Category, LauncherConfig, LauncherSettings
from .ui_theme import ThemeTransition, colors, themed_icon
from .windows_hotkey import DEFAULT_HOTKEY

ApplySettings = Callable[[LauncherSettings, tuple[Category, ...]], str | None]
CORNER_LABELS = {
    "top_left": "左上角", "top_right": "右上角",
    "bottom_left": "左下角", "bottom_right": "右下角",
}


class CategoryEditDialog(QDialog):
    def __init__(self, categories: tuple[Category, ...], preferred_parent_id: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新增分类")
        layout = QFormLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        self._name = QLineEdit()
        self._name.setPlaceholderText("分类名称")
        self._parent = QComboBox()
        self._parent.addItem("无（一级分类）", None)
        for category in categories:
            if category.parent_id is None and not is_uncategorized(category.id, category.name):
                self._parent.addItem(category.name, category.id)
        index = self._parent.findData(preferred_parent_id)
        if index >= 0:
            self._parent.setCurrentIndex(index)
        layout.addRow("名称", self._name)
        layout.addRow("父分类", self._parent)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def category_name(self) -> str:
        return self._name.text().strip()

    @property
    def parent_id(self) -> str | None:
        value = self._parent.currentData()
        return str(value) if value is not None else None

    def _accept_if_valid(self) -> None:
        if self.category_name:
            self.accept()


class HotCornerDialog(QDialog):
    def __init__(self, position: str, zone_px: int, dwell_ms: int, theme: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("热角区域")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._preview = HotCornerPreview()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        title = QLabel("鼠标热角区域")
        title.setObjectName("dialogTitle")
        hint = QLabel("鼠标进入所选角落并停留后呼出速拾；对鼠标所在显示器生效。")
        hint.setObjectName("dialogDescription")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        form = QFormLayout()
        self._position = QComboBox()
        for value, label in CORNER_LABELS.items():
            self._position.addItem(label, value)
        self._position.setCurrentIndex(max(0, self._position.findData(position)))
        self._position.currentIndexChanged.connect(self._refresh_preview)
        form.addRow("触发角落", self._position)
        self._zone = QSlider(Qt.Orientation.Horizontal)
        self._zone.setRange(4, 48)
        self._zone.setSingleStep(4)
        self._zone.setValue(zone_px)
        self._zone_value = QLabel(f"{zone_px} px")
        self._zone.valueChanged.connect(self._zone_changed)
        zone_row = QHBoxLayout()
        zone_row.addWidget(self._zone, 1)
        zone_row.addWidget(self._zone_value)
        form.addRow("区域大小", zone_row)
        self._dwell = QSlider(Qt.Orientation.Horizontal)
        self._dwell.setRange(100, 1000)
        self._dwell.setSingleStep(50)
        self._dwell.setValue(dwell_ms)
        self._dwell_value = QLabel(f"{dwell_ms} ms")
        self._dwell.valueChanged.connect(lambda value: self._dwell_value.setText(f"{value} ms"))
        dwell_row = QHBoxLayout()
        dwell_row.addWidget(self._dwell, 1)
        dwell_row.addWidget(self._dwell_value)
        form.addRow("停留时间", dwell_row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(settings_style(theme))

    @property
    def values(self) -> tuple[str, int, int]:
        return str(self._position.currentData()), self._zone.value(), self._dwell.value()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_preview()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._preview.clear()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._preview.clear()
        super().done(result)

    def _zone_changed(self, value: int) -> None:
        self._zone_value.setText(f"{value} px")
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self._preview.show(str(self._position.currentData()), self._zone.value())


class CategoryTreeWidget(QTreeWidget):
    layout_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("categoryTree")
        self.setHeaderHidden(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self._categories: tuple[Category, ...] = ()

    def populate(self, categories: tuple[Category, ...]) -> None:
        self._categories = categories
        self.clear()
        items: dict[str, QTreeWidgetItem] = {}
        for category in categories:
            if category.parent_id is None:
                item = self._new_item(category)
                self.addTopLevelItem(item)
                items[category.id] = item
        for category in categories:
            if category.parent_id is not None and category.parent_id in items:
                item = self._new_item(category)
                items[category.parent_id].addChild(item)
                items[category.id] = item
        self.expandAll()

    @staticmethod
    def _new_item(category: Category) -> QTreeWidgetItem:
        item = QTreeWidgetItem([category.name])
        item.setData(0, Qt.ItemDataRole.UserRole, category.id)
        flags = item.flags() | Qt.ItemFlag.ItemIsDragEnabled
        if category.parent_id is None and not is_uncategorized(category.id, category.name):
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        else:
            flags &= ~Qt.ItemFlag.ItemIsDropEnabled
        item.setFlags(flags)
        return item

    def categories(self) -> tuple[Category, ...]:
        categories: list[Category] = []
        for index in range(self.topLevelItemCount()):
            parent = self.topLevelItem(index)
            parent_id = str(parent.data(0, Qt.ItemDataRole.UserRole))
            categories.append(Category(parent_id, parent.text(0)))
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                categories.append(Category(str(child.data(0, Qt.ItemDataRole.UserRole)),
                                           child.text(0), parent_id))
        return tuple(categories)

    def dropEvent(self, event: QDropEvent) -> None:
        dragged = self.currentItem()
        if dragged is None:
            event.ignore()
            return
        snapshot = self._categories
        selected_id = str(dragged.data(0, Qt.ItemDataRole.UserRole))
        target = self.itemAt(event.position().toPoint())
        on_item = self.dropIndicatorPosition() == QAbstractItemView.DropIndicatorPosition.OnItem
        if on_item and target is not None:
            target_id = str(target.data(0, Qt.ItemDataRole.UserRole))
            if (target.parent() is not None or dragged.childCount() > 0 or
                    is_uncategorized(selected_id, dragged.text(0)) or
                    is_uncategorized(target_id, target.text(0))):
                event.ignore()
                return
        super().dropEvent(event)
        candidate = self.categories()
        error = validate_category_layout(snapshot, candidate)
        if error:
            self.populate(snapshot)
            self.layout_error.emit(error)
            return
        self._categories = candidate
        self.expandAll()


class SettingsDialog(QDialog):
    def __init__(self, config: LauncherConfig, apply_settings: ApplySettings,
                 parent: QWidget | None = None,
                 preview_icon_size: Callable[[int], None] | None = None,
                 preview_theme: Callable[[str], None] | None = None,
                 preview_window_opacity: Callable[[float], None] | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._apply_settings = apply_settings
        self._preview_icon_size = preview_icon_size
        self._preview_theme = preview_theme
        self._preview_window_opacity = preview_window_opacity
        self._original_icon_size = config.settings.icon_size
        self._original_theme = config.settings.theme
        self._original_window_opacity = config.settings.window_opacity
        self._preview_restored = False
        self._hot_corner_position = config.settings.hot_corner_position
        self._hot_corner_zone_px = config.settings.hot_corner_zone_px
        self._hot_corner_dwell_ms = config.settings.hot_corner_dwell_ms
        self.setWindowTitle("速拾设置")
        self.setModal(True)
        self.setMinimumSize(610, 570)
        self._build_ui(config)
        self._theme_transition = ThemeTransition(self)
        self._apply_dialog_theme(config.settings.theme)

    def _build_ui(self, config: LauncherConfig) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        title = QLabel("速拾设置")
        title.setObjectName("dialogTitle")
        description = QLabel("保存后立即生效；快捷键冲突时会保留当前设置。")
        description.setObjectName("dialogDescription")
        layout.addWidget(title)
        layout.addWidget(description)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("settingsTabs")
        self._tabs.addTab(self._activation_tab(config), "启动与窗口")
        self._tabs.addTab(self._appearance_tab(config), "外观")
        self._tabs.addTab(self._category_tab(config), "分类")
        layout.addWidget(self._tabs, 1)
        self._error_label = QLabel("")
        self._error_label.setObjectName("dialogError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        reset_button = QPushButton("恢复默认")
        buttons.addButton(reset_button, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        reset_button.clicked.connect(self._restore_defaults)
        layout.addWidget(buttons)

    def _activation_tab(self, config: LauncherConfig) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        group = QGroupBox("启动方式与窗口行为")
        form = QFormLayout(group)
        form.setSpacing(12)
        self._hotkey_editor = QKeySequenceEdit()
        self._hotkey_editor.setKeySequence(_sequence_from_portable(config.settings.hotkey))
        form.addRow("全局快捷键", self._hotkey_editor)
        corner_row = QHBoxLayout()
        self._corner_checkbox = QCheckBox("启用鼠标热角")
        self._corner_checkbox.setChecked(config.settings.hot_corner_enabled)
        self._corner_gear = QToolButton()
        self._corner_gear.setObjectName("hotCornerSettingsButton")
        self._corner_gear.setToolTip("设置热角位置、大小和停留时间")
        self._corner_gear.clicked.connect(self._open_hot_corner_settings)
        corner_row.addWidget(self._corner_checkbox)
        corner_row.addStretch()
        corner_row.addWidget(self._corner_gear)
        form.addRow("鼠标热角", corner_row)
        self._focus_checkbox = QCheckBox("点击窗口外时自动隐藏到托盘")
        self._focus_checkbox.setChecked(config.settings.hide_on_focus_lost)
        form.addRow("窗口行为", self._focus_checkbox)
        self._remember_position_checkbox = QCheckBox("记住拖动位置并跨重启恢复")
        self._remember_position_checkbox.setChecked(config.settings.remember_window_position)
        form.addRow("呼出位置", self._remember_position_checkbox)
        self._autostart_checkbox = QCheckBox("开机时自动启动速拾")
        self._autostart_checkbox.setChecked(config.settings.launch_at_login)
        form.addRow("开机自启动", self._autostart_checkbox)
        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _appearance_tab(self, config: LauncherConfig) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        group = QGroupBox("主题与图标")
        form = QFormLayout(group)
        form.setSpacing(14)
        self._theme_combo = QComboBox()
        self._theme_combo.addItem("抹茶亮色", "light")
        self._theme_combo.addItem("VS Code 暗色", "dark")
        self._theme_combo.setCurrentIndex(max(0, self._theme_combo.findData(config.settings.theme)))
        self._theme_combo.currentIndexChanged.connect(self._theme_changed)
        form.addRow("界面主题", self._theme_combo)
        row = QHBoxLayout()
        self._icon_size_slider = QSlider(Qt.Orientation.Horizontal)
        self._icon_size_slider.setRange(32, 80)
        self._icon_size_slider.setValue(config.settings.icon_size)
        self._icon_size_slider.setSingleStep(4)
        self._icon_size_slider.setPageStep(8)
        self._icon_size_progress = QProgressBar()
        self._icon_size_progress.setRange(32, 80)
        self._icon_size_progress.setValue(config.settings.icon_size)
        self._icon_size_progress.setFormat("%v px")
        self._icon_size_progress.setFixedWidth(92)
        self._icon_size_slider.valueChanged.connect(self._icon_size_changed)
        row.addWidget(self._icon_size_slider, 1)
        row.addWidget(self._icon_size_progress)
        form.addRow("应用图标大小", row)
        opacity_row = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(60, 100)
        self._opacity_slider.setSingleStep(5)
        self._opacity_slider.setValue(round(config.settings.window_opacity * 100))
        self._opacity_value = QLabel(f"{self._opacity_slider.value()}%")
        self._opacity_slider.valueChanged.connect(self._opacity_changed)
        opacity_row.addWidget(self._opacity_slider, 1)
        opacity_row.addWidget(self._opacity_value)
        form.addRow("窗口透明度", opacity_row)
        layout.addWidget(group)
        hint = QLabel("拖动时主界面图标、卡片尺寸和网格会同步预览。")
        hint.setObjectName("categoryHint")
        layout.addWidget(hint)
        layout.addStretch()
        return tab

    def _category_tab(self, config: LauncherConfig) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        hint = QLabel("分类最多两级；可直接拖动排序或归入父分类。删除后应用会移到“未分类”。")
        hint.setObjectName("categoryHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._category_tree = CategoryTreeWidget()
        self._category_tree.populate(config.categories)
        self._category_tree.layout_error.connect(self._show_error)
        layout.addWidget(self._category_tree, 1)
        buttons = QHBoxLayout()
        add_button, rename_button, delete_button = (QPushButton("新增分类"),
                                                     QPushButton("重命名"), QPushButton("删除"))
        add_button.clicked.connect(self._add_category)
        rename_button.clicked.connect(self._rename_category)
        delete_button.clicked.connect(self._delete_category)
        buttons.addWidget(add_button)
        buttons.addWidget(rename_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        return tab

    def _open_hot_corner_settings(self) -> None:
        dialog = HotCornerDialog(self._hot_corner_position, self._hot_corner_zone_px,
                                 self._hot_corner_dwell_ms,
                                 str(self._theme_combo.currentData()), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            (self._hot_corner_position, self._hot_corner_zone_px,
             self._hot_corner_dwell_ms) = dialog.values

    def _icon_size_changed(self, value: int) -> None:
        self._icon_size_progress.setValue(value)
        if self._preview_icon_size is not None:
            self._preview_icon_size(value)

    def _opacity_changed(self, value: int) -> None:
        self._opacity_value.setText(f"{value}%")
        if self._preview_window_opacity is not None:
            self._preview_window_opacity(value / 100)

    def _theme_changed(self) -> None:
        theme = str(self._theme_combo.currentData())
        self._apply_dialog_theme(theme)
        if self._preview_theme is not None:
            self._preview_theme(theme)

    def _apply_dialog_theme(self, theme: str) -> None:
        def apply() -> None:
            self.setStyleSheet(settings_style(theme))
            if hasattr(self, "_corner_gear"):
                self._corner_gear.setIcon(themed_icon("settings", theme, 18))

        if hasattr(self, "_theme_transition"):
            self._theme_transition.apply(apply)
        else:
            apply()

    def _all_items(self) -> list[QTreeWidgetItem]:
        iterator = QTreeWidgetItemIterator(self._category_tree)
        items: list[QTreeWidgetItem] = []
        while iterator.value() is not None:
            items.append(iterator.value())
            iterator += 1
        return items

    def _validate_category_name(self, name: str,
                                ignored_item: QTreeWidgetItem | None = None) -> str | None:
        if not name:
            return "分类名称不能为空。"
        if name.casefold() == "全部".casefold():
            return "“全部”是固定入口，请使用其他名称。"
        for item in self._all_items():
            if item is not ignored_item and item.text(0).casefold() == name.casefold():
                return "分类名称不能重复。"
        return None

    def _add_category(self) -> None:
        current = self._category_tree.currentItem()
        preferred_parent = None
        if current is not None and current.parent() is None:
            current_id = str(current.data(0, Qt.ItemDataRole.UserRole))
            if not is_uncategorized(current_id, current.text(0)):
                preferred_parent = current_id
        dialog = CategoryEditDialog(self._categories(), preferred_parent, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        error = self._validate_category_name(dialog.category_name)
        if error:
            self._show_error(error)
            return
        category = Category(f"category-{uuid.uuid4().hex[:10]}", dialog.category_name,
                            dialog.parent_id)
        categories = list(self._categories())
        if dialog.parent_id is None:
            categories.append(category)
        else:
            insert_at = max(i for i, existing in enumerate(categories)
                            if existing.id == dialog.parent_id or
                            existing.parent_id == dialog.parent_id) + 1
            categories.insert(insert_at, category)
        self._category_tree.populate(tuple(categories))
        self._error_label.hide()

    def _rename_category(self) -> None:
        item = self._category_tree.currentItem()
        if item is None:
            self._show_error("请先选择要重命名的分类。")
            return
        category_id = str(item.data(0, Qt.ItemDataRole.UserRole))
        if is_uncategorized(category_id, item.text(0)):
            self._show_error("“未分类”是保底分类，不能重命名。")
            return
        name, accepted = QInputDialog.getText(self, "重命名分类", "分类名称",
                                              text=item.text(0))
        if not accepted:
            return
        name = name.strip()
        error = self._validate_category_name(name, item)
        if error:
            self._show_error(error)
            return
        item.setText(0, name)
        self._error_label.hide()

    def _delete_category(self) -> None:
        item = self._category_tree.currentItem()
        if item is None:
            self._show_error("请先选择要删除的分类。")
            return
        category_id = str(item.data(0, Qt.ItemDataRole.UserRole))
        if is_uncategorized(category_id, item.text(0)):
            self._show_error("“未分类”是保底分类，不能删除。")
            return
        parent = item.parent()
        if parent is None:
            self._category_tree.takeTopLevelItem(self._category_tree.indexOfTopLevelItem(item))
        else:
            parent.takeChild(parent.indexOfChild(item))
        self._error_label.hide()

    def _categories(self) -> tuple[Category, ...]:
        return self._category_tree.categories()

    def _restore_defaults(self) -> None:
        self._hotkey_editor.setKeySequence(_sequence_from_portable(DEFAULT_HOTKEY))
        self._corner_checkbox.setChecked(True)
        self._hot_corner_position, self._hot_corner_zone_px = "top_right", 8
        self._hot_corner_dwell_ms = 250
        self._focus_checkbox.setChecked(True)
        self._remember_position_checkbox.setChecked(False)
        self._autostart_checkbox.setChecked(False)
        self._theme_combo.setCurrentIndex(self._theme_combo.findData("light"))
        self._icon_size_slider.setValue(48)
        self._opacity_slider.setValue(100)
        self._error_label.hide()

    def _restore_preview(self) -> None:
        if self._preview_restored:
            return
        self._preview_restored = True
        if self._preview_icon_size is not None:
            self._preview_icon_size(self._original_icon_size)
        if self._preview_theme is not None:
            self._preview_theme(self._original_theme)
        if self._preview_window_opacity is not None:
            self._preview_window_opacity(self._original_window_opacity)

    def reject(self) -> None:
        self._restore_preview()
        super().reject()

    def _save(self) -> None:
        hotkey = self._hotkey_editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if not hotkey:
            self._show_error("请先录入一个快捷键。")
            return
        remember = self._remember_position_checkbox.isChecked()
        error = self._apply_settings(LauncherSettings(
            hotkey=hotkey, hot_corner_enabled=self._corner_checkbox.isChecked(),
            hot_corner_position=self._hot_corner_position,
            hot_corner_zone_px=self._hot_corner_zone_px,
            hot_corner_dwell_ms=self._hot_corner_dwell_ms,
            hide_on_focus_lost=self._focus_checkbox.isChecked(),
            remember_window_position=remember,
            window_x=self._config.settings.window_x if remember else None,
            window_y=self._config.settings.window_y if remember else None,
            icon_size=self._icon_size_slider.value(),
            launch_at_login=self._autostart_checkbox.isChecked(),
            theme=str(self._theme_combo.currentData()),
            window_opacity=self._opacity_slider.value() / 100,
        ), self._categories())
        if error:
            self._show_error(error)
            return
        self._preview_restored = True
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()


def _sequence_from_portable(shortcut: str) -> QKeySequence:
    return QKeySequence.fromString(shortcut, QKeySequence.SequenceFormat.PortableText)


def settings_style(theme: str) -> str:
    c = colors(theme)
    style = """
QDialog, QWidget { background-color: @surface@; color: @text@; }
QLabel#dialogTitle { font-size: 20px; font-weight: 700; color: @text@; }
QLabel#dialogDescription, QLabel#categoryHint { color: @muted@; }
QGroupBox { color: @text@; font-weight: 700; border: 1px solid @border@; border-radius: 10px; margin-top: 10px; padding-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QTabWidget::pane { border: 1px solid @border@; border-radius: 10px; background: @surface@; }
QTabBar::tab { background: @sidebar@; color: @muted@; border: 1px solid @border@; padding: 8px 16px; }
QTabBar::tab:selected { background: @accent@; color: white; font-weight: 700; }
QKeySequenceEdit, QLineEdit, QComboBox, QTreeWidget#categoryTree { background: @input@; color: @text@; border: 1px solid @border@; border-radius: 8px; padding: 8px; }
QKeySequenceEdit:focus, QLineEdit:focus, QComboBox:focus, QTreeWidget#categoryTree:focus { border: 2px solid @accent@; }
QTreeWidget#categoryTree::item { padding: 6px; border-radius: 6px; }
QTreeWidget#categoryTree::item:selected { background: @accent@; color: white; }
QCheckBox { color: @text@; padding: 4px 0; }
QSlider::groove:horizontal { height: 6px; background: @hover@; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0; background: @accent_dark@; border-radius: 8px; }
QProgressBar { background: @sidebar@; color: @text@; border: 1px solid @border@; border-radius: 7px; text-align: center; }
QProgressBar::chunk { background: @accent_soft@; border-radius: 6px; }
QPushButton, QToolButton { background: @sidebar@; color: @text@; border: 1px solid @border@; border-radius: 8px; padding: 7px 12px; }
QPushButton:hover, QToolButton:hover { background: @hover@; }
QPushButton:default { background: @accent@; color: white; border-color: @accent@; }
QLabel#dialogError { color: @error@; background: @error_bg@; border-radius: 8px; padding: 8px; }
"""
    for name, value in c.items():
        style = style.replace(f"@{name}@", value)
    return style
