# Quick Launcher V1

一个 Windows 常驻式应用启动器原型：使用抹茶绿界面，通过 `Win + Alt + Space` 或右上角热角唤出，搜索或选择应用后立即启动并隐藏。

## 当前功能

- PySide6 无边框、置顶、抹茶绿启动面板
- 系统托盘：显示启动器或安全退出
- `Win + Alt + Space` 全局快捷键（Windows 原生 `RegisterHotKey`）
- 所有显示器右上角 `8×8 px` 热角，停留约 250 ms 唤出；关闭后必须移出热区才能再次触发
- 分类、实时搜索、`Esc` 隐藏、搜索框中 `Enter` 启动第一个结果
- `.exe` 与 `.lnk` 启动；可为 `.exe` 传递参数和工作目录
- 用户目录中的 JSON 配置与按需图标缓存
- 单实例保护，避免多个托盘图标和热键竞争
- 设置窗口：修改全局快捷键、开关右上角热角，保存后即时生效
- 分类树：直接拖拽排序、一级/二级分类转换，并在保存失败时自动恢复
- 设置窗口：在“启动与窗口 / 外观 / 分类”三栏中管理快捷键、热角、窗口行为、主题和分类
- 热角可配置四个角落、区域大小与停留时间；可选记住窗口位置
- 抹茶亮色与 VS Code 风格暗色主题，切换时平滑淡入淡出；图标大小与窗口透明度可在设置中实时预览
- 热角设置弹窗会实时标出每个显示器上的触发区域

## 运行

在 Windows 上使用 Python 3.14.4：

```powershell
uv sync
uv run python main.py
```

首次启动会创建：`%LOCALAPPDATA%\QuickLauncher\shortcuts.json`。
该文件是用户可编辑配置；不要编辑安装目录里的 `quick_launcher/resources/default_shortcuts.json`，它仅作为首次启动模板。

## 配置示例

```json
{
  "schema_version": 1,
  "categories": [{"id": "development", "name": "开发"}],
  "apps": [
    {
      "id": "vscode",
      "name": "Visual Studio Code",
      "category_id": "development",
      "target": "C:\\Users\\name\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
      "args": [],
      "cwd": null
    }
  ]
}
```

`target` 可以是可执行文件名（例如 `notepad.exe`）、绝对 `.exe` 路径，或 `.lnk` 快捷方式路径。应用仍通过 JSON 编辑；分类栏和启动方式可以在程序“设置”中修改并立即生效。

## 验证

核心配置与搜索逻辑不依赖 Windows 或 GUI，可运行：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
uv run python -m unittest discover -s tests -v
```

Windows 手工验收：确认背景不再为黑色、托盘存在、快捷键能唤出、热角在副屏也可用；检查点击其他应用时自动隐藏、记忆位置越界后仍会显示在可见区域、暗色主题对比度，以及分类拖拽、图标预览与不同窗口尺寸下的自动重排。
