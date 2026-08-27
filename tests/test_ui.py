import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QMimeData,
    QPoint,
    QPointF,
    QSize,
    Qt,
    QUrl,
)
from PySide6.QtGui import QColor, QDropEvent, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QProgressBar, QSlider, QToolButton, QWidget

from quick_launcher.icon_service import IconService
from quick_launcher.models import AppEntry, Category, LauncherConfig, LauncherSettings
from quick_launcher.settings import SettingsDialog
from quick_launcher.ui_theme import bundled_icon
from quick_launcher.window import (
    AppCard,
    BottomLeftResizeGrip,
    CategorySidebar,
    DragBar,
    LauncherWindow,
)


class LauncherUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = LauncherConfig(
            schema_version=1,
            categories=(Category("dev", "开发"), Category("study", "学习")),
            apps=(),
            settings=LauncherSettings(),
        )
        self.icon_service = IconService(Path(self.temp_dir.name), self.qt_app.style())
        self.window = LauncherWindow(self.config, self.icon_service)
        self.window.move(100, 100)
        self.window.show()
        self.qt_app.processEvents()

    def tearDown(self) -> None:
        self.window.allow_quit()
        self.window.close()
        self.temp_dir.cleanup()

    def test_application_area_renders_matcha_instead_of_black(self) -> None:
        viewport = self.window.findChild(QWidget, "appViewport")
        self.assertIsNotNone(viewport)
        image = self.window.grab().toImage()
        local_point = viewport.mapTo(
            self.window,
            QPoint(max(1, viewport.width() // 2), max(1, viewport.height() // 2)),
        )
        color = image.pixelColor(local_point)
        self.assertGreater(color.red(), 180)
        self.assertGreater(color.green(), 180)
        self.assertGreater(color.blue(), 170)

    def test_window_uses_translucent_antialiased_corners_without_pixel_mask(self) -> None:
        self.assertTrue(
            self.window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        )
        self.assertTrue(self.window.mask().isEmpty())
        surface = self.window.findChild(QFrame, "surface")
        self.assertIsNotNone(surface)

    def test_visible_branding_and_minimize_button(self) -> None:
        self.assertEqual(self.window.windowTitle(), "速拾")
        title = self.window.findChild(QWidget, "title")
        self.assertEqual(title.text(), "速拾")
        minimize = self.window.findChild(QToolButton, "minimizeButton")
        self.assertIsNotNone(minimize)
        minimize.click()
        self.qt_app.processEvents()
        self.assertFalse(self.window.isVisible())

    def test_local_drop_paths_rejects_non_local_urls(self) -> None:
        mime_data = QMimeData()
        mime_data.setUrls(
            [QUrl.fromLocalFile("C:/Tools/App.exe"), QUrl("https://example.com/App.exe")]
        )
        self.assertEqual(self.window._local_drop_paths(mime_data), ("C:/Tools/App.exe",))

    def test_drop_emits_all_local_paths_with_current_category(self) -> None:
        captured = []
        self.window.files_dropped.connect(
            lambda paths, category_id: captured.append((paths, category_id))
        )
        self.window._select_category("dev")
        mime_data = QMimeData()
        mime_data.setUrls(
            [QUrl.fromLocalFile("C:/Tools/One.exe"), QUrl.fromLocalFile("C:/Tools/Two.lnk")]
        )
        event = QDropEvent(
            QPointF(20, 20),
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.window.dropEvent(event)

        self.assertEqual(
            captured,
            [(("C:/Tools/One.exe", "C:/Tools/Two.lnk"), "dev")],
        )

    def test_title_bar_drag_moves_frameless_window(self) -> None:
        drag_bar = self.window.findChild(DragBar, "moveHandle")
        self.assertIsNotNone(drag_bar)
        self.assertEqual(drag_bar.size(), QSize(34, 30))
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(10, 10),
            QPointF(110, 110),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        drag_bar.mousePressEvent(press)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(60, 50),
            QPointF(60, 50),
            QPointF(160, 150),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        drag_bar.mouseMoveEvent(move)
        self.assertEqual(self.window.pos(), QPoint(150, 140))

    def test_bottom_left_grip_resizes_and_keeps_right_edge_fixed(self) -> None:
        grip = self.window.findChild(BottomLeftResizeGrip, "bottomLeftResizeGrip")
        self.assertIsNotNone(grip)
        original = self.window.geometry()
        press_global = original.bottomLeft()
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 20),
            QPointF(5, 20),
            QPointF(press_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        grip.mousePressEvent(press)
        move_global = press_global + QPoint(-40, 30)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(-35, 50),
            QPointF(-35, 50),
            QPointF(move_global),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        grip.mouseMoveEvent(move)
        self.assertEqual(self.window.geometry().right(), original.right())
        self.assertEqual(self.window.width(), original.width() + 40)
        self.assertEqual(self.window.height(), original.height() + 30)
        self.assertFalse(grip.findChildren(QWidget))

    def test_app_card_requests_context_menu(self) -> None:
        entry = AppEntry("tool", "Tool", "dev", "Tool.exe")
        self.window.apply_config(
            LauncherConfig(1, self.config.categories, (entry,), self.config.settings)
        )
        card = self.window.findChild(AppCard, "appCard")
        captured = []
        self.window.app_context_requested.connect(
            lambda app, point: captured.append((app, point))
        )

        card.customContextMenuRequested.emit(QPoint(4, 4))

        self.assertEqual(captured[0][0], entry)
        self.assertIsInstance(captured[0][1], QPoint)

    def test_downloaded_web_icon_is_cached_and_reused(self) -> None:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor("#789A63"))
        self.assertTrue(pixmap.save(buffer, "PNG"))
        target = "https://example.com/"

        self.assertTrue(self.icon_service.save_icon_data(target, bytes(data)))

        cache_file = self.icon_service.cache_file_for(target)
        self.assertTrue(cache_file.exists())
        icon = self.icon_service.icon_for(AppEntry("web", "Example", "dev", target))
        self.assertFalse(icon.isNull())

    def test_apply_config_rebuilds_flat_category_tree(self) -> None:
        updated = LauncherConfig(
            schema_version=1,
            categories=(
                Category("custom", "自定义"),
                Category("dev", "开发工具"),
                Category("python", "Python", "dev"),
            ),
            apps=(),
            settings=LauncherSettings(),
        )
        self.window.apply_config(updated)
        sidebar = self.window.findChild(CategorySidebar, "categoryTree")
        self.assertEqual(
            [sidebar.topLevelItem(index).text(0) for index in range(sidebar.topLevelItemCount())],
            ["全部", "自定义", "开发工具"],
        )
        self.assertEqual(sidebar.topLevelItem(2).child(0).text(0), "Python")

    def test_settings_keeps_category_drag_order_on_save(self) -> None:
        captured = []

        def apply(settings, categories):
            captured.append((settings, categories))
            return None

        dialog = SettingsDialog(self.config, apply, self.window)
        self.assertEqual(dialog.windowTitle(), "速拾设置")
        moved = dialog._category_tree.takeTopLevelItem(1)
        dialog._category_tree.insertTopLevelItem(0, moved)
        dialog._save()
        self.assertEqual([category.id for category in captured[0][1]], ["study", "dev"])

    def test_settings_allows_deleting_category_with_apps(self) -> None:
        config = LauncherConfig(
            1,
            self.config.categories,
            (AppEntry("tool", "Tool", "dev", "Tool.exe"),),
            self.config.settings,
        )
        dialog = SettingsDialog(config, lambda settings, categories: None, self.window)
        dialog._category_tree.setCurrentItem(dialog._category_tree.topLevelItem(0))

        dialog._delete_category()

        self.assertEqual(dialog._category_tree.topLevelItemCount(), 1)
        self.assertEqual(dialog._category_tree.topLevelItem(0).text(0), "学习")

    def test_category_tree_nesting_keeps_both_items(self) -> None:
        dialog = SettingsDialog(self.config, lambda settings, categories: None, self.window)
        tree = dialog._category_tree
        parent = tree.topLevelItem(0)
        child = tree.takeTopLevelItem(1)
        parent.addChild(child)

        categories = dialog._categories()

        self.assertEqual(len(categories), 2)
        self.assertEqual(categories[1].parent_id, categories[0].id)
        self.assertFalse(tree.dragDropOverwriteMode())

    def test_settings_saves_focus_behavior_and_icon_size_progress(self) -> None:
        captured = []

        def apply(settings, categories):
            captured.append(settings)
            return None

        dialog = SettingsDialog(self.config, apply, self.window)
        dialog._focus_checkbox.setChecked(False)
        dialog._icon_size_slider.setValue(72)
        progress = dialog.findChild(QProgressBar)
        self.assertEqual(progress.value(), 72)
        self.assertIsNotNone(dialog.findChild(QSlider))
        dialog._save()
        self.assertFalse(captured[0].hide_on_focus_lost)
        self.assertEqual(captured[0].icon_size, 72)

    def test_parent_category_includes_child_apps_and_applies_icon_size(self) -> None:
        categories = (Category("dev", "开发"), Category("python", "Python", "dev"))
        child_app = AppEntry("py", "Python", "python", "python.exe")
        config = LauncherConfig(
            1,
            categories,
            (child_app,),
            LauncherSettings(icon_size=72),
        )
        self.window.apply_config(config)
        self.window._select_category("dev")
        cards = self.window.findChildren(AppCard)
        self.assertEqual([card.app for card in cards], [child_app])
        self.assertEqual(cards[0].iconSize(), QSize(72, 72))

    def test_cards_reflow_when_window_width_changes(self) -> None:
        apps = tuple(
            AppEntry(f"app-{index}", f"App {index}", "dev", f"app-{index}.exe")
            for index in range(8)
        )
        self.window.apply_config(
            LauncherConfig(1, self.config.categories, apps, self.config.settings)
        )
        self.window.resize(720, 520)
        self.qt_app.processEvents()
        narrow_columns = max(
            self.window._grid.getItemPosition(index)[1]
            for index in range(self.window._grid.count())
        )
        self.window.resize(1100, 520)
        self.qt_app.processEvents()
        wide_columns = max(
            self.window._grid.getItemPosition(index)[1]
            for index in range(self.window._grid.count())
        )
        self.assertGreater(wide_columns, narrow_columns)

    def test_sidebar_uses_category_context_signals_not_web_background_signal(self) -> None:
        category_events = []
        background_events = []
        self.window.category_context_requested.connect(
            lambda point, category_id: category_events.append(category_id)
        )
        self.window.background_context_requested.connect(
            lambda point, category_id: background_events.append(category_id)
        )
        sidebar = self.window.findChild(CategorySidebar, "categoryTree")
        dev_item = sidebar.topLevelItem(1)
        sidebar._show_context(sidebar.visualItemRect(dev_item).center())
        self.assertEqual(category_events, ["dev"])
        self.assertEqual(background_events, [])

    def test_theme_button_emits_and_applies_dark_theme(self) -> None:
        captured = []
        self.window.theme_toggle_requested.connect(lambda: captured.append(True))
        self.window.findChild(QToolButton, "themeButton").click()
        self.assertEqual(captured, [True])
        self.window.apply_theme("dark")
        self.assertEqual(self.window.property("theme"), "dark")

    def test_visible_theme_transition_cleans_up_snapshot(self) -> None:
        self.window.apply_theme("dark", animated=True)
        self.assertIsNotNone(self.window._theme_transition._overlay)
        overlay = self.window._theme_transition._overlay
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertEqual(overlay._corner_radius, 20.0)
        self.window.apply_theme("light", animated=True)
        self.assertIsNotNone(self.window._theme_transition._overlay)
        QTest.qWait(240)
        self.assertIsNone(self.window._theme_transition._overlay)

    def test_window_uses_packaged_main_icon(self) -> None:
        self.assertFalse(bundled_icon("sushi-organizer.exe.ico").isNull())
        self.assertFalse(bundled_icon("sushi-organizer-tray.ico").isNull())
        self.assertFalse(self.window.windowIcon().isNull())

    def test_settings_has_three_tabs_and_restores_live_previews_on_cancel(self) -> None:
        icon_previews = []
        theme_previews = []
        opacity_previews = []
        dialog = SettingsDialog(
            self.config,
            lambda settings, categories: None,
            self.window,
            preview_icon_size=icon_previews.append,
            preview_theme=theme_previews.append,
            preview_window_opacity=opacity_previews.append,
        )
        self.assertEqual([dialog._tabs.tabText(index) for index in range(dialog._tabs.count())],
                         ["启动与窗口", "外观", "分类"])
        self.assertFalse(dialog._autostart_checkbox.isChecked())
        dialog._icon_size_slider.setValue(72)
        dialog._theme_combo.setCurrentIndex(dialog._theme_combo.findData("dark"))
        dialog._opacity_slider.setValue(65)
        dialog.reject()
        self.assertEqual(icon_previews, [72, 48])
        self.assertEqual(theme_previews, ["dark", "light"])
        self.assertEqual(opacity_previews, [0.65, 1.0])

    def test_window_applies_and_previews_opacity(self) -> None:
        self.window.apply_config(LauncherConfig(
            1, self.config.categories, (), LauncherSettings(window_opacity=0.72)
        ))
        self.assertAlmostEqual(self.window.windowOpacity(), 0.72, places=2)
        self.window.preview_window_opacity(0.6)
        self.assertAlmostEqual(self.window.windowOpacity(), 0.6)


if __name__ == "__main__":
    unittest.main()
