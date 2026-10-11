# LanShot

LanShot 是一款轻量的 Windows 局域网截图工具。程序常驻系统托盘，不占用任务栏；按下 **Ctrl + Alt + A** 后，它会立即截取整个桌面，并把截图发送到同一局域网内已配对的手机浏览器。

## 功能特点

- **全桌面截图**：一次截取整个桌面，多显示器环境会包含所有显示器。
- **快捷键发送**：按 `Ctrl + Alt + A` 即可截图，无需手动框选。
- **手机自动接收**：手机页面保持打开时，新截图会自动显示。
- **二维码配对**：首次启动显示二维码，手机扫码即可连接。
- **系统托盘运行**：像 QQ 一样驻留在右下角托盘，不显示普通任务栏窗口。
- **同步到剪贴板**：发送手机的同时，将截图复制到 Windows 剪贴板。
- **本地局域网传输**：不依赖云端服务，不需要公网服务器。
- **访问保护**：配对地址包含随机令牌，未持有令牌的设备不能读取截图。
- **开机启动**：可通过托盘菜单开启或关闭。

## 环境要求

- Windows 10 或 Windows 11
- Python 3.10 或更高版本（仅源码运行和构建需要）
- 手机与电脑连接同一个局域网或 Wi-Fi

## 从源码运行

```powershell
# 1. 克隆仓库后进入项目目录
cd LanShot

# 2. 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 安装固定版本依赖
python -m pip install -r requirements.txt

# 4. 启动程序
pythonw main.py
```

程序启动后会出现在 Windows 右下角系统托盘。首次运行将显示二维码配对窗口。

## 使用方法

1. 确保手机和电脑连接同一个 Wi-Fi。
2. 启动 LanShot，使用手机扫描首次启动时显示的二维码。
3. 保持手机接收页面打开。
4. 在电脑按 `Ctrl + Alt + A`。
5. 整个桌面截图会自动显示在手机上，并复制到电脑剪贴板。

关闭二维码窗口不会退出程序。若要退出，请右键单击托盘图标并选择“退出 LanShot”。

## 托盘菜单

- 截取整个桌面
- 手机配对（二维码）
- 复制配对地址
- 打开截图文件夹
- 开机自动启动
- 退出 LanShot

## 构建 Windows EXE

安装依赖后运行：

```powershell
.\build.bat
```

构建结果位于 `dist\LanShot.exe`。构建目录、虚拟环境和 EXE 不提交到源码仓库。

也可以直接执行：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name LanShot `
  --icon assets\lanshot.ico `
  --hidden-import pystray._win32 `
  main.py
```

## 运行测试

```powershell
python -m unittest -v
```

测试覆盖配置读写、截图存储与清理、手机接收页面、接口鉴权和图片读取。

## Windows 防火墙

首次运行时，Windows 可能询问是否允许网络访问。请选择“专用网络”并允许访问，否则手机无法连接电脑上的接收服务。

LanShot 只在本机启动局域网 HTTP 服务，不会自动开放公网端口。请勿把带有随机令牌的配对地址分享给不信任的人。公共 Wi-Fi、访客网络或启用了设备隔离的路由器可能会阻止手机访问电脑。

## 数据位置

配置和截图保存在：

```text
%LOCALAPPDATA%\LanShot
```

默认最多保留最近 30 张截图。删除该目录可以清除本机配对令牌、配置和历史截图。

## 项目结构

```text
LanShot/
├─ assets/lanshot.ico     # 托盘和程序图标
├─ lanshot/
│  ├─ app.py              # 托盘、快捷键、二维码和应用生命周期
│  ├─ capture.py          # Windows 剪贴板写入
│  ├─ config.py           # 本地配置与开机启动命令
│  ├─ server.py           # 局域网 HTTP 服务和手机接收页面
│  └─ store.py            # 截图保存与历史清理
├─ main.py                # 程序入口
├─ test_lanshot.py        # 自动测试
├─ requirements.txt       # 固定版本依赖
└─ build.bat              # Windows 打包脚本
```

## 技术栈

- Python / Tkinter
- Pillow
- pystray
- qrcode
- Python 标准库 `http.server`
- PyInstaller

## 当前限制

- 仅支持 Windows。
- 手机必须能直接访问电脑的局域网 IP。
- 快捷键目前固定为 `Ctrl + Alt + A`。
- 当前使用局域网 HTTP；请只在可信的家庭或办公专用网络中使用。

## License

本项目暂未指定开源许可证。在添加许可证前，代码默认保留所有权利。
