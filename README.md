# Better Hall Aircon · 宿舍空调工作台

## 0.2.0：更新与语言

v0.2.0 发布日期：2026-10-17。下载见 [最新 Release](https://github.com/QR-Not-Code/Better-Hall-Aircon/releases/latest)。

- 启动后在后台读取 `QR-Not-Code/Better-Hall-Aircon` 的最新正式 Release；没有新版或临时无法联网时不会打断启动。左侧也可手动“检查更新”。检查使用公开接口，不发送 Token、房间编号或其他账号数据。
- 有可安装的新版才弹窗；“跳过本次”只跳过本次检查，下次启动会再次检查。确认更新后下载便携 ZIP，核对 GitHub 提供的 SHA-256、配套校验文件和实际下载内容；校验不通过不会替换程序。
- 下载完成后把当前未保存脚本存成“更新前草稿”副本，然后停止脚本与抓包，退出程序，由独立 Windows 助手替换整个安装文件夹并重启。安装文件夹同级保留 `.previous-...` 旧版备份；替换或启动请求失败会尝试回退。新版进程启动后的运行异常无法自动判定，必要时手动使用旧版备份。
- 电脑需要能访问 GitHub，安装目录的上级目录需要写入权限和足够空间。取消下载或发生网络、校验、权限错误时，原程序可继续使用。旧版备份和失败的临时更新目录可在确认不再需要后手动清理。
- 账号、Token、脚本、连接器、语言和证书仍使用 `%LOCALAPPDATA%\HallAirconStudio`，升级不覆盖它们。空调保持最后状态；手机 WireGuard 隧道需自行关闭。
- 左侧“语言 / Language”可在简体中文与 English 之间切换并保存选择。覆盖导航、控制页、连接向导、教程、脚本编辑器、Blockly 标准积木、自定义积木、云端导出界面和主要错误提示；用户编写的脚本名称、变量、文字、代码和外部返回数据保持原文。随附 Markdown 技术文档仍以中文为主。
- 源码运行时可检查版本，但不会用便携包替换源码。自动更新适用于 Windows 打包版；旧的 v0.1.0 本身没有更新检查功能，需要先手动换用带此功能的版本。

Windows 桌面程序：连接向导、手机抓包教程、授权自动提取、房间校验、空调控制和 Blockly 拼图脚本。
程序不附带任何人的账号、Token、房间编号、抓包文件或第三方连接配置。

## 下载已发布版本

[GitHub Releases](https://github.com/QR-Not-Code/Better-Hall-Aircon/releases/latest) 提供已发布便携包。最新 v0.2.0 包含自动更新检查和中英文切换。

## 启动

使用打包版：解压整个 `HallAirconStudio-Windows.zip`，打开目录中的 `HallAirconStudio.exe`。
保留同目录的 `_internal` 文件夹，不要单独移动 exe。程序不要求预先安装 Python、Node 或 Reqable。

从源码运行（Python 3.12–3.14，Windows）：

```powershell
python -m pip install -r requirements.txt
python main.py
```

只看界面、不连接真实设备：`python main.py --demo`，或打包版 `HallAirconStudio.exe --demo`。
演示模式使用单独目录和固定示例值，所有设备操作都为模拟。

## 第一次连接

连接页提供两个独立入口：

- **第一次使用：获取 Token**：页面下方“操作向导”覆盖电脑与手机完整的 12 步。每一步说明位置、操作、完成标志和卡住时的处理方式；已保存房号、二维码已准备、防火墙成功、引擎就绪等由程序检测，其余步骤由用户确认。可点击“定位对应控件”找到按钮。
- **已有 Token：直接连接**：直接粘贴 Token 并验证，不需要填写房号、热点、抓包、WireGuard 或证书。程序从 `/me` 自动读取该 Token 绑定的 `aircon_code` 并核对状态。未绑定或授权失效会提示，失败时保留之前的账号。

两条路径验证成功都会弹出结果窗口，显示绑定房间与完整 Token。点击 Token 文本或“复制完整 Token”会通过系统剪贴板复制纯 Token；关闭窗口后清除显示内容。控制面板也有“查看 / 复制本机 Token”入口，按需查看已保存凭据。

1. 先在官方 Hall Aircon App 登录自己的账号，并扫码绑定自己的房间。确认 App 可以正常控制。
2. 打开“连接向导”，粘贴设备编号，或选择房间二维码照片。本机识别后核对并保存。
3. 手机和电脑需要能互相访问。电脑有线联网时，可在 Windows 设置 / 网络和 Internet / 移动热点中共享以太网；手机连接电脑热点。
4. 选择热点 IPv4 地址，点击“准备连接二维码”。通常热点地址为 `192.168.137.1`，程序从本机网卡列表选择，不写死用户网络。
5. 点击“配置防火墙”，在 Windows 管理员提示中允许。规则只开放所选本地地址的 UDP 51820，并限制来源为同一 /24 子网。它不会开启电脑系统代理。
6. 点击“启动并等待授权”。手机停止其他抓包 VPN，安装免费的官方 WireGuard，选择 ＋ / Create from QR code，扫描程序二维码，允许 VPN 并开启隧道。
7. iPhone Safari 打开 `http://mitm.it`，下载 iOS 证书，点 Allow。到 Settings / General / VPN & Device Management 安装 mitmproxy 描述文件；再到 General / About / Certificate Trust Settings 开启 mitmproxy 完全信任。
8. 完全退出再打开 Hall Aircon，刷新空调状态。程序会提取 Bearer Token，通过 `/me` 校验设备编号，匹配后加密保存，停止抓包并显示授权结果，可点击进入面板。
9. 关闭手机 WireGuard 隧道以恢复正常联网。临时 mitmproxy 证书可移除，控制空调不依赖抓包持续开启。

如果已有 Token，直接使用连接页顶部的快捷入口。Token 在本机连接页以省略形式持续显示，点击可复制完整内容，完整内容也可在结果窗口显示，不把授权头写入日志或随程序分发。

## 空调控制和参数

- 控制前查询并核对房间身份，控制后轮询后端状态。失败和结果未知会明确提示，不把 HTTP 200 单独作为执行成功证据。
- 电源：表单 `power=1/0`。摆风：`flap=S/N`。这两种动作沿用已实测的接口协议。
- 面板显示后端返回的运行字段：电源、当前温度、设定温度、摆风、风速、模式、通信、维护、设备状态、类型。
- 不显示姓名、学号、钱包、余额和完整账号响应。“当前温度”是服务器字段，不保证等同于独立温度计；也不能判断压缩机转速、功率或实际能耗。
- 温度、风速、模式需要在“录制官方操作”中学习。选择“学习参数”模式，重新连接手机并在官方 App 操作，点击停止抓包保存已被服务器接受的取值。随后可从面板选择这些取值。
- 不提供猜测参数、任意房间控制、解除绑定、充值或计费修改。
- Token 如含 `exp` 时间会在界面显示，属于未验证的 JWT 元信息。服务器可能提前撤销；登录和自动刷新接口仍未知，到期后重新获取授权。

## 脚本、模块和代码

新建空白脚本后先命名，保存到本机脚本库。支持重命名、另存副本、打开、删除、JSON 导入导出；空调控制页可快速选择并执行保存的脚本。

内置模板已全部清空，等待用户自行制作。旧版画布会迁移到脚本库，保留原文件。

13 类、123 个模块入口覆盖设备、条件、流程、状态事件、抗干扰、变量与持久存储、计算与随机、文本、列表与 JSON、时间日历、HTTP/MQTT 和用户代码。变量、文本、连接和路径均使用通用默认文字。

Python 代码模式支持本机 .py 文件，自定义接口可返回数据供其他积木使用。无法无损转换的代码完整显示为用户自定义模块。Python 拥有当前用户权限，不是沙箱；正式执行需选择信任，试运行仅检查代码语法，不执行 Python。停止可取消独立代码进程。

状态事件包括电源、摆风、设定温度、风速、模式。“疑似外部操作”是根据已观察变化与本程序指令匹配得到的推断，不能确定操作者，也不能保证捕获轮询间隔中的短暂变化。温度和通信波动单独归为遥测。

分支分类直接提供 if/elif/else、switch/case/default 和条件取值。循环分类明确列出 break、continue、范围 for 与循环 else；逻辑分类补充异或、同或、与非、或非、all/any、成员判断、类型与空值检查。运行前检查会阻止循环外的 break/continue。

完整模块说明、抗干扰搭建方法和代码 SDK 见 [模块与代码指南](MODULES.md)。程序内“零基础教程”也有操作说明。

HTTP 连接支持 GET/POST/PUT/PATCH/DELETE/HEAD、JSON 请求体和返回路径；MQTT 订阅读取 JSON；ICS 日历支持重复事件。连接地址和凭据以名称引用、加密保存，不随脚本分发。

本地脚本需要程序和电脑保持运行；停止不会自动改变空调状态。正式运行有最大时长和步数限制，已发出的请求不能撤回。

脚本页新增“导出 GitHub Actions”：兼容的积木脚本可以保存断点，由 GitHub 定时恢复，电脑关闭后仍可执行；有限 Python/写入型接口脚本可导出为云端单次作业。导出只生成 ZIP，不自动发布或执行。上传仓库、配置 Secrets 后，先选 test、status，再 start。详见 [GitHub 云端指南](CLOUD.md)。

## 本地数据与清理

正式用户数据保存在 `%LOCALAPPDATA%\HallAirconStudio`：

- `vault.bin`：Windows DPAPI 加密的空调 Token 和连接器配置，只能由当前 Windows 用户解密。
- `settings.json`：本机房间编号、时区、IP 和学习到的参数。房间编号不随程序和脚本分发。
- `scripts.json`：命名脚本库（积木与代码），支持多个脚本。
- `workspace.aircon.json`：旧版文件，只用于首次迁移，不删除原件。
- `capture`：本次电脑生成的 CA 证书私钥、WireGuard 密钥和必要诊断信息。二维码含隧道私钥，不要分享。

界面不加载 CDN，Blockly 离线打包，浏览器内核禁止访问远程页面；外部连接由 Python 按显式配置访问。
抓包只解密空调域名和本机证书页；不保存完整流量、账号响应或授权头。运行日志只在界面内存保留。
DPAPI 保护磁盘上的凭据，不能抵御已控制同一 Windows 用户会话的程序。

退出会停止脚本和子进程。手机 WireGuard 需自行关闭。“零基础教程 / 本地设置”可请求移除本程序防火墙规则。
“退出当前账号”删除空调授权和设备编号，保留连接器、脚本。卸载时删除用户数据目录，并在 iPhone 移除临时证书与隧道。

## 验证与限制

已对原 API 框架完成真实电源和摆风验证。本 GUI 用隔离演示账号测试，未替用户重新切换真实空调。
后端测试覆盖加密、身份阻断、请求编码、脚本库迁移、试运行、停止、逻辑循环、ICS 重复事件、HTTP/MQTT 模拟、摆风事件、来源匹配、抗干扰和 Python 子进程。
传感器硬件和真实订阅日历需要用户自己的地址与凭据；没有把模拟测试描述为这些外部服务已联调。
手机证书固定、IPv6 路由、校园网络策略等可能影响抓包，向导不能保证所有 App 版本均可解密。

本地运行依赖电脑；云端导出部署后由 GitHub 托管 runner 执行。断点模式按至少 5 分钟的触发恢复，可能延迟，不能代替秒级常驻服务器。原先的 GitHub Actions 工程仍单独保留。当前 GUI 提供离线导出与教程，不自动向仓库发布或设置 Secrets。

开发检查：`python -m pytest tests -q`；GUI 冒烟：`python main.py --demo --smoke`；构建：`python -m pip install pyinstaller` 后 `python build.py`。

参考与第三方资料：

- Blockly：[离线获取](https://docs.blockly.com/guides/get-started/get-the-code/)、[序列化](https://docs.blockly.com/guides/configure/serialization/)
- mitmproxy：[WireGuard 模式](https://docs.mitmproxy.org/stable/concepts/modes/#wireguard)
- WireGuard：[官方客户端](https://www.wireguard.com/install/)
- Qt：[PySide6](https://doc.qt.io/qtforpython-6/)
