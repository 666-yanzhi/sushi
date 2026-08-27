# 速拾

> 一款为 Windows 设计的常驻式应用与网页启动器。按下快捷键、移动到热角，或点击托盘图标，即可搜索并打开常用内容。

速拾把零散的桌面应用、快捷方式和常用网页放进一个可搜索、可分类的小面板中。它尽量不打扰：启动后驻留在系统托盘，打开目标后自动隐藏。

## 功能一览

- **随时唤出**：默认按 <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>Space</kbd>；也可以用任意屏幕的鼠标热角或系统托盘唤出。
- **快速查找**：按应用名称实时搜索，<kbd>Enter</kbd> 打开第一项，<kbd>Esc</kbd> 隐藏面板。
- **管理应用与网页**：拖入 `.exe` 或 `.lnk` 快捷方式即可添加；右键可重命名、移动、删除或添加网页。网页会在后台尝试获取网站图标。
- **清晰的分类**：支持一级、二级分类和拖拽排序；删除分类时，其中的应用会自动放入“未分类”，不会丢失。
- **按习惯定制**：在设置中修改快捷键、热角位置与停留时间、窗口位置、图标大小、透明度、主题、失焦隐藏及开机自启动。
- **可靠地常驻**：单实例保护避免重复运行；启动需要管理员权限的程序时，会在 Windows 要求时发起 UAC 授权。

## 使用

### 直接运行发布版

1. 从项目的 [Releases](../../releases) 下载最新的 Windows 压缩包并解压。
2. 双击解压目录中的 `速拾.exe`。
3. 首次运行后，使用默认快捷键 <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>Space</kbd> 打开面板。
4. 将应用的 `.exe` 或 `.lnk` 文件拖到面板中，选择分类后即可添加；也可右键面板空白处添加网页。

程序关闭面板后不会退出，而是继续显示在系统托盘。右键托盘图标可重新打开速拾或安全退出。

### 常用操作

| 操作 | 方法 |
| --- | --- |
| 打开速拾 | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>Space</kbd>（默认），鼠标热角，或托盘图标 |
| 搜索并启动 | 输入名称，按 <kbd>Enter</kbd> 启动首个结果 |
| 隐藏面板 | 按 <kbd>Esc</kbd>、启动一个项目，或切换到其他窗口（默认） |
| 添加桌面应用 | 将 `.exe` / `.lnk` 拖进面板 |
| 添加网页 | 右键面板空白处或应用卡片，选择“添加网页” |
| 编辑应用 | 右键应用卡片，可打开、重命名、移动或删除 |
| 调整行为与外观 | 打开“设置”，保存后立即生效 |

> 删除应用或分类只会移除速拾中的记录，不会删除电脑上的原始文件。热角默认位于每块显示器的右上角；在设置中可关闭或调整它。

## 数据与配置

速拾不会把个人配置写入安装目录。首次启动时，会在当前用户目录创建：

```text
%LOCALAPPDATA%\QuickLauncher\
├── shortcuts.json   # 分类、应用和设置
└── cache\icons\      # 应用与网页图标缓存
```

通常建议在程序的设置界面中修改选项。若需要批量维护，可先退出速拾，再编辑 `shortcuts.json`；下次启动会校验格式。项目内的 `quick_launcher/resources/default_shortcuts.json` 只是首次启动模板，修改它不会覆盖已有用户配置。

一个应用条目的最小示例：

```json
{
  "id": "vscode",
  "name": "Visual Studio Code",
  "category_id": "development",
  "target": "C:\\Users\\name\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
  "args": [],
  "cwd": null
}
```

`target` 支持可执行文件名（如 `notepad.exe`）、绝对 `.exe` 路径、`.lnk` 快捷方式，以及 `http` / `https` 网页地址。`args` 用于传递启动参数，`cwd` 用于指定工作目录。

## 从源码运行

### 环境要求

- Windows 10 / 11
- Python `3.14.4`
- [uv](https://docs.astral.sh/uv/)

```powershell
git clone <你的仓库地址>
cd sushi
uv sync
uv run python main.py
```

也可以在完成同步后运行已注册的命令：

```powershell
uv run quick-launcher
```

全局快捷键、系统托盘、Windows 自启动和实际启动应用等能力依赖 Windows；在其他系统中仅适合运行部分非界面逻辑测试。

## 测试与构建

运行测试时使用 Qt 的无界面平台：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
uv run python -m unittest discover -s tests -v
```

生成 Windows 可执行发布目录：

```powershell
uv run pyinstaller 速拾.spec --noconfirm
```

构建产物默认位于 `dist\速拾\`；分发时请保留整个目录，不要只复制其中的 `速拾.exe`。

## 项目结构

```text
quick_launcher/
├── app.py              # 应用装配、托盘菜单和交互流程
├── window.py           # 主启动面板
├── settings.py         # 设置与分类编辑界面
├── config.py           # 用户配置读写与校验
├── launcher.py         # 应用、快捷方式和网页启动
├── hotcorner.py        # 多显示器热角
├── windows_hotkey.py   # Windows 全局快捷键
└── resources/          # 默认配置和图标资源
tests/                  # 配置、搜索、启动和界面行为测试
```

## 许可证

本项目使用 [MIT License](LICENSE)。
