from __future__ import annotations

import sys
import uuid
from dataclasses import replace
from collections.abc import Callable

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
)

from .config import AppPaths, ConfigError, ConfigStore
from .categories import (
    category_label,
    category_subtree_ids,
    is_uncategorized,
    move_orphaned_apps,
    validate_category_layout,
)
from .autostart import AutostartError, WindowsAutostart
from .hotcorner import HotCorner
from .icon_service import IconService
from .importer import format_import_summary, persist_import
from .launcher import LaunchError, TargetLauncher
from .models import AppEntry, Category, LauncherConfig, LauncherSettings
from .settings import CategoryEditDialog, SettingsDialog
from .single_instance import SingleInstance
from .web_shortcut import (
    WebIconLoader,
    WebShortcutError,
    build_web_entry,
    default_web_name,
    normalize_web_url,
)
from .window import LauncherWindow
from .windows_hotkey import WindowsHotkey
from .ui_theme import apply_palette, bundled_icon


class PanelController:
    def __init__(self, window: LauncherWindow, settings_provider: Callable[[], LauncherSettings]) -> None:
        self._window = window
        self._settings_provider = settings_provider

    def toggle(self) -> None:
        if self._window.isVisible():
            self._window.hide_launcher()
        else:
            self.show()

    def show(self) -> None:
        settings = self._settings_provider()
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            self._window.prepare_to_show(QPoint(80, 80))
            return
        area = screen.availableGeometry()
        if settings.remember_window_position and settings.window_x is not None:
            remembered = QPoint(settings.window_x, settings.window_y or 0)
            remembered_screen = QGuiApplication.screenAt(remembered)
            if remembered_screen is not None:
                area = remembered_screen.availableGeometry()
            x = min(max(remembered.x(), area.left()), max(area.left(), area.right() - self._window.width() + 1))
            y = min(max(remembered.y(), area.top()), max(area.top(), area.bottom() - self._window.height() + 1))
        else:
            x = area.x() + max(0, (area.width() - self._window.width()) // 2)
            y = area.y() + max(0, (area.height() - self._window.height()) // 2)
        self._window.prepare_to_show(QPoint(x, y))


def _save_settings_with_autostart(
    store: ConfigStore,
    autostart: WindowsAutostart,
    previous: LauncherConfig,
    candidate: LauncherConfig,
) -> str | None:
    """Persist settings while returning the Run entry to its prior state on failure."""
    changed = candidate.settings.launch_at_login != previous.settings.launch_at_login
    if changed:
        try:
            autostart.set_enabled(candidate.settings.launch_at_login)
        except AutostartError as exc:
            return str(exc)
    try:
        store.save(candidate)
    except OSError as exc:
        rollback_error: AutostartError | None = None
        if changed:
            try:
                autostart.set_enabled(previous.settings.launch_at_login)
            except AutostartError as rollback_exc:
                rollback_error = rollback_exc
        suffix = f"；开机自启动状态可能已变化：{rollback_error}" if rollback_error else ""
        return f"保存设置失败：{exc}{suffix}"
    return None


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("速拾")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(bundled_icon("sushi-organizer.exe.ico"))

    instance = SingleInstance()
    if not instance.acquire():
        QMessageBox.information(None, "速拾", "速拾已在运行。")
        return 0

    paths = AppPaths.for_current_user()
    store = ConfigStore(paths)
    try:
        config = store.load_or_create()
    except (ConfigError, OSError) as exc:
        QMessageBox.critical(None, "速拾配置错误", str(exc))
        instance.release()
        return 1

    apply_palette(app, config.settings.theme)

    icon_service = IconService(paths.icon_cache_dir, app.style())
    window = LauncherWindow(config, icon_service)
    controller = PanelController(window, lambda: config.settings)
    target_launcher = TargetLauncher()
    autostart = WindowsAutostart()
    web_icon_loader = WebIconLoader(icon_service, app)

    def launch_selected(entry: AppEntry) -> None:
        try:
            target_launcher.open(entry)
        except LaunchError as exc:
            window.show_error(str(exc))
        else:
            window.hide_launcher()

    window.app_requested.connect(launch_selected)

    def choose_category(preferred_id: str | None = None) -> str | None:
        category_ids = {category.id for category in config.categories}
        if preferred_id in category_ids:
            return preferred_id
        if not config.categories:
            window.show_error("请先在设置中创建分类。")
            return None
        category_names = [category_label(config.categories, category) for category in config.categories]
        selected_name, accepted = QInputDialog.getItem(
            window,
            "选择分类",
            "添加到：",
            category_names,
            0,
            False,
        )
        if not accepted:
            return None
        return config.categories[category_names.index(selected_name)].id

    def save_runtime_config(candidate_config, success_message: str) -> bool:
        nonlocal config
        try:
            store.save(candidate_config)
        except OSError as exc:
            window.show_error(f"保存失败：{exc}")
            return False
        config = candidate_config
        window.apply_config(config)
        window.show_status(success_message)
        return True

    def update_app(entry_id: str, updated_entry: AppEntry, message: str) -> None:
        candidate_apps = tuple(
            updated_entry if existing.id == entry_id else existing for existing in config.apps
        )
        save_runtime_config(replace(config, apps=candidate_apps), message)

    def rename_app(entry: AppEntry) -> None:
        name, accepted = QInputDialog.getText(
            window,
            "重命名应用",
            "应用名称：",
            text=entry.name,
        )
        name = name.strip()
        if not accepted:
            return
        if not name:
            window.show_error("应用名称不能为空。")
            return
        update_app(entry.id, replace(entry, name=name), "应用已重命名。")

    def move_app(entry: AppEntry, category_id: str) -> None:
        if entry.category_id == category_id:
            return
        update_app(entry.id, replace(entry, category_id=category_id), "应用已移动。")

    def delete_app(entry: AppEntry) -> None:
        answer = QMessageBox.question(
            window,
            "删除应用",
            f"确定从速拾中删除“{entry.name}”吗？\n不会删除原始文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        candidate_apps = tuple(existing for existing in config.apps if existing.id != entry.id)
        save_runtime_config(replace(config, apps=candidate_apps), "应用已删除，原始文件未受影响。")

    def add_website(preferred_category_id: str | None = None) -> None:
        raw_url, accepted = QInputDialog.getText(window, "添加网页", "网页地址：")
        if not accepted:
            return
        try:
            normalized_url = normalize_web_url(raw_url)
        except WebShortcutError as exc:
            window.show_error(str(exc))
            return
        name, accepted = QInputDialog.getText(
            window,
            "添加网页",
            "显示名称：",
            text=default_web_name(normalized_url),
        )
        if not accepted:
            return
        category_id = choose_category(preferred_category_id)
        if category_id is None:
            return
        try:
            entry = build_web_entry(normalized_url, name, category_id, config.apps)
        except WebShortcutError as exc:
            window.show_error(str(exc))
            return
        if save_runtime_config(
            replace(config, apps=(*config.apps, entry)),
            "网页已添加，正在获取网站图标…",
        ):
            web_icon_loader.fetch(entry.target)

    def show_app_context_menu(entry: AppEntry, global_position: QPoint) -> None:
        menu = QMenu(window)
        open_action = menu.addAction("打开")
        rename_action = menu.addAction("重命名")
        move_menu = menu.addMenu("移动到")
        move_actions = {}
        for category in config.categories:
            action = move_menu.addAction(category_label(config.categories, category))
            action.setEnabled(category.id != entry.category_id)
            move_actions[action] = category.id
        delete_action = menu.addAction("删除")
        menu.addSeparator()
        add_web_action = menu.addAction("添加网页")
        selected = menu.exec(global_position)
        if selected is open_action:
            launch_selected(entry)
        elif selected is rename_action:
            rename_app(entry)
        elif selected is delete_action:
            delete_app(entry)
        elif selected is add_web_action:
            add_website(entry.category_id)
        elif selected in move_actions:
            move_app(entry, move_actions[selected])

    def show_background_context_menu(
        global_position: QPoint,
        category_id: str | None,
    ) -> None:
        menu = QMenu(window)
        add_web_action = menu.addAction("添加网页")
        if menu.exec(global_position) is add_web_action:
            add_website(category_id)

    def create_category(preferred_parent_id: str | None = None) -> None:
        preferred_parent = next(
            (category for category in config.categories if category.id == preferred_parent_id),
            None,
        )
        if preferred_parent is not None and preferred_parent.parent_id is not None:
            preferred_parent_id = preferred_parent.parent_id
        if preferred_parent is not None and is_uncategorized(
            preferred_parent.id, preferred_parent.name
        ):
            preferred_parent_id = None
        dialog = CategoryEditDialog(config.categories, preferred_parent_id, window)
        if not dialog.exec():
            return
        name = dialog.category_name
        if name.casefold() == "全部".casefold() or any(
            category.name.casefold() == name.casefold() for category in config.categories
        ):
            window.show_error("分类名称不能与现有分类或“全部”重复。")
            return
        category = Category(
            f"category-{uuid.uuid4().hex[:10]}",
            name,
            dialog.parent_id,
        )
        categories = list(config.categories)
        if dialog.parent_id is None:
            categories.append(category)
        else:
            insert_at = max(
                index
                for index, existing in enumerate(categories)
                if existing.id == dialog.parent_id or existing.parent_id == dialog.parent_id
            ) + 1
            categories.insert(insert_at, category)
        save_runtime_config(
            replace(config, categories=tuple(categories)),
            "分类已创建。",
        )

    def delete_category(category_id: str) -> None:
        category = next(
            (candidate for candidate in config.categories if candidate.id == category_id),
            None,
        )
        if category is None:
            return
        if is_uncategorized(category.id, category.name):
            window.show_error("“未分类”是保底分类，不能删除。")
            return
        subtree_ids = category_subtree_ids(config.categories, category.id)
        answer = QMessageBox.question(
            window,
            "删除分类",
            f"确定删除“{category.name}”吗？其中的应用会移到“未分类”。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        categories = tuple(
            candidate for candidate in config.categories if candidate.id not in subtree_ids
        )
        migrated_categories, migrated_apps = move_orphaned_apps(
            config.categories,
            categories,
            config.apps,
        )
        save_runtime_config(
            replace(config, categories=migrated_categories, apps=migrated_apps),
            "分类已删除，其中的应用已移到“未分类”。",
        )

    def show_sidebar_context_menu(global_position: QPoint) -> None:
        menu = QMenu(window)
        create_action = menu.addAction("创建分类")
        delete_menu = menu.addMenu("删除分类")
        delete_actions = {}
        for category in config.categories:
            action = delete_menu.addAction(category_label(config.categories, category))
            action.setEnabled(not is_uncategorized(category.id, category.name))
            delete_actions[action] = category.id
        delete_menu.setEnabled(bool(delete_actions))
        selected = menu.exec(global_position)
        if selected is create_action:
            create_category()
        elif selected in delete_actions:
            delete_category(delete_actions[selected])

    def show_category_context_menu(
        global_position: QPoint,
        category_id: str | None,
    ) -> None:
        menu = QMenu(window)
        create_root_action = menu.addAction("创建分类")
        category = next(
            (candidate for candidate in config.categories if candidate.id == category_id),
            None,
        )
        delete_action = None
        if category is not None:
            delete_action = menu.addAction("删除分类")
            if is_uncategorized(category.id, category.name):
                delete_action.setEnabled(False)
        selected = menu.exec(global_position)
        if selected is create_root_action:
            create_category(category_id)
        elif selected is delete_action and category is not None:
            delete_category(category.id)

    window.app_context_requested.connect(show_app_context_menu)
    window.background_context_requested.connect(show_background_context_menu)
    window.sidebar_context_requested.connect(show_sidebar_context_menu)
    window.category_context_requested.connect(show_category_context_menu)

    def refresh_web_icon(target: str, success: bool) -> None:
        if success:
            window.apply_config(config)
            window.show_status("网站图标已更新。")
        else:
            window.show_status("网页已添加；未获取到网站图标，已使用默认图标。")

    web_icon_loader.finished.connect(refresh_web_icon)

    def import_dropped_files(paths: tuple[str, ...], selected_category_id: str | None) -> None:
        nonlocal config
        category_id = choose_category(selected_category_id)
        if category_id is None:
            return

        outcome = persist_import(config, paths, category_id, store.save)
        summary = format_import_summary(outcome.plan)
        if outcome.error:
            window.show_error(outcome.error)
            return
        if not outcome.plan.entries:
            window.show_status(summary, "error")
            return

        config = outcome.config
        window.apply_config(config)
        window.show_status(summary)

    window.files_dropped.connect(import_dropped_files)

    hot_corner = HotCorner()
    hot_corner.activated.connect(controller.show)
    window.launcher_hidden.connect(hot_corner.launcher_hidden)
    hot_corner.configure(
        config.settings.hot_corner_position,
        config.settings.hot_corner_zone_px,
        config.settings.hot_corner_dwell_ms,
    )
    hot_corner.set_enabled(config.settings.hot_corner_enabled)
    hot_corner.start()

    hotkey = WindowsHotkey(controller.toggle, config.settings.hotkey)
    app.installNativeEventFilter(hotkey.native_filter)
    registered, hotkey_error = hotkey.register()

    def apply_settings(
        new_settings: LauncherSettings,
        categories: tuple[Category, ...],
    ) -> str | None:
        nonlocal config
        migrated_categories, migrated_apps = move_orphaned_apps(
            config.categories,
            categories,
            config.apps,
        )

        previous_settings = config.settings
        hotkey_changed = new_settings.hotkey != previous_settings.hotkey
        if hotkey_changed:
            rebound, error = hotkey.rebind(new_settings.hotkey)
            if not rebound:
                return error or "无法注册新的快捷键。"

        candidate_config = replace(
            config,
            settings=new_settings,
            categories=migrated_categories,
            apps=migrated_apps,
        )
        save_error = _save_settings_with_autostart(
            store, autostart, config, candidate_config
        )
        if save_error:
            if hotkey_changed:
                hotkey.rebind(previous_settings.hotkey)
            return save_error

        theme_changed = new_settings.theme != previous_settings.theme
        config = candidate_config
        hot_corner.configure(
            new_settings.hot_corner_position,
            new_settings.hot_corner_zone_px,
            new_settings.hot_corner_dwell_ms,
        )
        hot_corner.set_enabled(new_settings.hot_corner_enabled)
        window.apply_config(
            config,
            animate_theme=theme_changed,
            theme_prepare=lambda: apply_palette(app, new_settings.theme),
        )
        tray.setToolTip(f"速拾（{hotkey.display_name}）")
        return None

    def save_category_layout(categories: tuple[Category, ...]) -> None:
        error = validate_category_layout(config.categories, categories)
        if error:
            window.apply_config(config)
            window.show_error(error)
            return
        if not save_runtime_config(replace(config, categories=categories), "分类顺序已保存。"):
            window.apply_config(config)

    def save_window_position(position: QPoint) -> None:
        nonlocal config
        if not config.settings.remember_window_position:
            return
        candidate = replace(
            config,
            settings=replace(config.settings, window_x=position.x(), window_y=position.y()),
        )
        try:
            store.save(candidate)
        except OSError as exc:
            window.show_error(f"保存窗口位置失败：{exc}")
            return
        config = candidate

    def preview_theme(theme: str) -> None:
        window.preview_theme(theme, prepare=lambda: apply_palette(app, theme))

    def toggle_theme() -> None:
        next_theme = "dark" if config.settings.theme == "light" else "light"
        apply_settings(replace(config.settings, theme=next_theme), config.categories)

    def open_settings() -> None:
        SettingsDialog(
            config,
            apply_settings,
            window,
            preview_icon_size=window.preview_icon_size,
            preview_theme=preview_theme,
            preview_window_opacity=window.preview_window_opacity,
        ).exec()

    window.settings_requested.connect(open_settings)
    window.categories_reordered.connect(save_category_layout)
    window.position_changed.connect(save_window_position)
    window.theme_toggle_requested.connect(toggle_theme)
    tray = _create_tray(app, controller, window, open_settings, hotkey.display_name)
    if not registered and hotkey_error:
        tray.showMessage("快捷键不可用", hotkey_error, QSystemTrayIcon.MessageIcon.Warning)

    def cleanup() -> None:
        hot_corner.stop()
        hotkey.unregister()
        tray.hide()
        instance.release()

    app.aboutToQuit.connect(cleanup)
    tray.show()
    return app.exec()


def _create_tray(
    app: QApplication,
    controller: PanelController,
    window: LauncherWindow,
    open_settings: Callable[[], None],
    hotkey_name: str,
) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(
        bundled_icon(
            "sushi-organizer-tray.ico",
            app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
        ),
        app,
    )
    tray.setToolTip(f"速拾（{hotkey_name}）")
    menu = QMenu()
    show_action = QAction("显示启动器", menu)
    show_action.triggered.connect(controller.show)
    menu.addAction(show_action)
    settings_action = QAction("设置", menu)
    settings_action.triggered.connect(open_settings)
    menu.addAction(settings_action)
    menu.addSeparator()
    exit_action = QAction("退出", menu)

    def quit_app() -> None:
        window.allow_quit()
        app.quit()

    exit_action.triggered.connect(quit_app)
    menu.addAction(exit_action)
    tray.setContextMenu(menu)

    def tray_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            controller.toggle()

    tray.activated.connect(tray_activated)
    return tray


def _apply_matcha_palette(app: QApplication) -> None:
    """Keep native child widgets from inheriting a dark Windows palette."""
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F4F8EE"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#2F3D2A"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#E8F2DD"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#2F3D2A"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#E8F2DD"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#2F3D2A"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#789A63"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
