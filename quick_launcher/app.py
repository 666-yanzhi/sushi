from __future__ import annotations

import sys

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction, QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from .config import AppPaths, ConfigError, ConfigStore
from .hotcorner import HotCorner
from .icon_service import IconService
from .launcher import LaunchError, TargetLauncher
from .models import AppEntry
from .single_instance import SingleInstance
from .window import LauncherWindow
from .windows_hotkey import WindowsHotkey


class PanelController:
    def __init__(self, window: LauncherWindow) -> None:
        self._window = window

    def toggle(self) -> None:
        if self._window.isVisible():
            self._window.hide_launcher()
        else:
            self.show()

    def show(self) -> None:
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            self._window.prepare_to_show(QPoint(80, 80))
            return
        area = screen.availableGeometry()
        x = area.x() + max(0, (area.width() - self._window.width()) // 2)
        y = area.y() + max(0, (area.height() - self._window.height()) // 2)
        self._window.prepare_to_show(QPoint(x, y))


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Quick Launcher")
    app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    if not instance.acquire():
        QMessageBox.information(None, "Quick Launcher", "Quick Launcher 已在运行。")
        return 0

    paths = AppPaths.for_current_user()
    try:
        config = ConfigStore(paths).load_or_create()
    except (ConfigError, OSError) as exc:
        QMessageBox.critical(None, "Quick Launcher 配置错误", str(exc))
        instance.release()
        return 1

    window = LauncherWindow(config, IconService(paths.icon_cache_dir, app.style()))
    controller = PanelController(window)
    target_launcher = TargetLauncher()

    def launch_selected(entry: AppEntry) -> None:
        try:
            target_launcher.open(entry)
        except LaunchError as exc:
            window.show_error(str(exc))
        else:
            window.hide_launcher()

    window.app_requested.connect(launch_selected)

    tray = _create_tray(app, controller, window)
    hot_corner = HotCorner()
    hot_corner.activated.connect(controller.show)
    window.launcher_hidden.connect(hot_corner.launcher_hidden)
    hot_corner.start()

    hotkey = WindowsHotkey(controller.toggle)
    app.installNativeEventFilter(hotkey.native_filter)
    registered, hotkey_error = hotkey.register()
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
    app: QApplication, controller: PanelController, window: LauncherWindow
) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), app)
    tray.setToolTip("Quick Launcher（Win + Alt + Space）")
    menu = QMenu()
    show_action = QAction("显示启动器", menu)
    show_action.triggered.connect(controller.show)
    menu.addAction(show_action)
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
