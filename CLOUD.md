# 在 GitHub Actions 运行空调脚本

本导出包不含账号、房间编号、连接器凭据或现有桌面脚本存档。它包含当前选择的脚本、无 GUI 的 Python 运行器和工作流文件。电脑关闭后由 GitHub 托管 runner 执行，不依赖本机抓包或本机常驻程序。

## 两种模式

| 模式 | 用途 | 重要边界 |
| --- | --- | --- |
| 断点定时执行 | 长期积木脚本、每天按时间判断、带等待的顺序动作和循环 | 定时恢复进度，不是连续常驻；最短 5 分钟，可能延迟或漏触发 |
| 云端单次执行 | 有限时长的积木脚本、包含 Python/自定义写入接口的脚本 | 人工触发一次，从头执行；不能跨作业恢复任意 Python 栈或等待进度 |

断点模式中“开 → 等待两小时 → 关”会先开机并保存唤醒时间，退出作业释放 runner；之后的触发若未到时间就退出，到时间后继续关机。不会每五分钟从头开机。长时间等待不占用 runner 持续睡眠。实际动作只能在某次触发时执行，因此两小时是“至少两小时”，不保证精确到秒。

原生积木的变量、循环、break/continue、if/elif/else、switch、try/catch/finally、重试、持久数据、观察基线、去抖和冷却均可恢复。长期循环按触发分批运行；精确的 `HH:MM == 23:00` 可能错过，宜改为时间区间加“当天一次”。

任意 Python 代码无法自动恢复解释器执行栈，写入型自定义 HTTP 请求无法保证断点重放语义，因此此类脚本需用单次模式。导出前会显示阻止原因。Python 在 Linux 执行，本机文件、Windows API 和局域网地址不能直接沿用。单个 Python 进程最长 1 小时；额外第三方包需自行添加到导出目录的 requirements.txt。动态拼接的连接名称无法全部静态分析，需手动补齐连接器 Secret。

## 零基础部署步骤

1. 桌面中先保存脚本。点击“导出 GitHub Actions”，选择模式、定时频率和时限，先查看兼容检查，再导出 ZIP。
2. 在 GitHub 创建自己的仓库，建议使用私有仓库。解压导出包，把 **`.github` 和 `aircon` 两个目录完整上传到默认分支**；`.github/workflows/aircon-标识.yml` 必须存在。不要仅上传 ZIP 本身。
3. 打开仓库 **Settings → Secrets and variables → Actions → New repository secret**，设置下面的 Secrets。它们不会写进代码文件。
4. 打开仓库 **Actions**，选择对应的 **Hall Aircon Cloud** 工作流，点 **Run workflow**，先选择 `test`。此项不发真实设备或外部接口请求，不执行自定义 Python，只检查语法与模拟流程。
5. 检查通过后，配置好自己的有效 Token 和房间，先选择 `status` 在云端只读核对连接；确认通过后再选择 `start`。启动会读取设备状态并核对房间；只有之后的正式脚本动作才控制设备。断点模式的定时触发在第一次 start 前不会控制设备。
6. 断点模式启动成功后，可关闭桌面程序和电脑。去 GitHub Actions 查看运行记录；定时触发会继续恢复脚本。
7. 暂停时手动运行 `pause`，保留进度和当前设备状态；之后 `resume` 继续。暂停不冻结已记录的唤醒时间，恢复时若已到期就继续后续动作。`reset` 会清空脚本进度并暂停，不自动开关空调；再选 `start` 才从头执行。已完成的脚本也需明确 reset 后重新启动。

工作流不接受 pull request 触发，不提供远程上传/发布或自动填写凭据。导出后上传的代码及任何 Python 都由你自行审阅、信任。

## 必需的 Secrets

| 名称 | 内容 |
| --- | --- |
| `AIRCON_TOKEN` | 本人的有效 Bearer Token；可在桌面连接页点击复制。不要带引号或换行 |
| `AIRCON_EXPECTED_ROOM` | 本人的完整房间二维码设备编号；用于身份核对 |
| `AIRCON_STATE_KEY` | 仅断点模式需要，Fernet 加密密钥，不能随意更换 |
| `AIRCON_CONNECTIONS_JSON` | 用到外部连接器时填写 JSON，键名与积木引用名称一致 |

`GITHUB_TOKEN` 由 GitHub 自动提供，不需要自己创建 PAT。断点模式需要工作流拥有 **contents: write** 权限；生成的 YAML 已声明。若仓库/组织策略禁止写入，或分支保护阻止创建 `aircon-state`，会明确失败并停止后续控制。

生成进度密钥：在已安装 Python 的机器执行 `python -m pip install cryptography`，再执行：

```text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将结果作为 `AIRCON_STATE_KEY` Secret 保存，不要提交到仓库。丢失/更换密钥后无法读取旧进度，应恢复原密钥；若决定放弃旧进度，需自行移除对应的加密进度文件后重建。

连接器 JSON 结构示意（所有值由你填写为可从公网访问的本人服务）：

```json
{
  "连接名称": {
    "kind": "http",
    "url": "https://your-own-service.example/api",
    "token": "your-own-service-token"
  }
}
```

日历使用 `kind: calendar` 与 HTTPS ICS URL；MQTT 使用 `kind: mqtt`、`host`、`port`、`topic`、`username`、`token` 和 `tls`。家中 192.168.*、10.*、localhost、`.local` 等服务不能被 GitHub 托管 runner 直接访问。连接器必须自行开放合适的公网接口或另行配置安全网络；导出器不自动配置 VPN。

## 进度、异常与更新

断点模式在 `aircon-state` 分支保存 Fernet 加密的进度，包含变量、控制流程位置和状态基线；运行器不自动把 Token、连接器配置复制到进度中。公开仓库的进度文件也是密文，但仍建议私有仓库。不要在脚本源码/文字积木硬编码凭据或房间，导出器会阻止已知凭据，但不能识别所有用户自行输入的秘密。

控制前先提交“待确认”记录，成功核对后再提交完成状态。如果中断发生在命令与确认之间，下次先读设备状态；目标已达到则继续，无法确认则暂停等待人工核对，不自动重发。日志会显示待确认字段与目标。核对 `status` 和官方 App 后，如果明确需要再次设置该目标，可人工选择 `retry_pending`：它先检查状态，仍未达到目标才重新设置。也可选择 reset 重置流程；普通 resume 不会自动重发。接口没有服务端事务 ID，无法保证任意崩溃时严格执行且仅执行一次。GitHub 写入失败会阻止继续控制。

每轮最多处理有限步骤和 6 条空调控制，避免没有停顿的循环持续轰炸服务。轮次之间的观察空档可能漏掉短暂开关；去抖和“稳定”只反映已观察值，不是连续的物理采样。命名冷却、当天一次和持久变量会跨轮次保留。

断点模式不采用桌面单次“最长运行小时数”，而是每轮限步、限时，持续循环直到完成、暂停或失败。设备控制结果未知与进度写入失败会优先暂停，脚本中的 try/retry 不会覆盖此保护；普通读取失败仍可进入错误处理和重试分支。GET/HEAD 按读取接口处理，若服务端实际用它们执行有副作用的操作，请自行选择单次模式。

替换脚本并重新上传后，旧进度的内容指纹不一致会停止执行。先 `pause`，确认新逻辑，再 `reset` 和 `start`。不要同时让旧仓库、多个云端脚本和本机脚本争抢同一空调；同仓库导出的工作流共享串行并发组，不会取消正在执行的作业，但排队可能延迟。

Token 到期或撤销时，更新 `AIRCON_TOKEN` Secret 后手动恢复；没有自动刷新接口。脚本异常、设备结果不确定和持久化失败均需查看 Actions 日志并处理。网页上的“暂停”也是一次排队作业，若要立即阻止当前作业，请在 Actions 中取消运行；已经发出的控制无法撤回。

## GitHub 的限制

- 标准 GitHub 托管 runner 单个作业最多 6 小时。本导出器单次脚本最多配置 330 分钟，另留安装和退出时间；断点模式每轮为短作业。
- schedule 最短 5 分钟，只在默认分支运行，高负载时可能延迟甚至丢弃；不适合秒级控制或严格准点保障。
- 私有仓库的免费分钟数/存储取决于账号方案。请在 GitHub Billing 查看配额，不保证免费无限运行。
- 公开仓库长时间无活动时，定时工作流可能自动停用；需要定期查看工作流状态。GitHub 故障、额度、权限、Token 有效期等也会中断自动化。

此功能不把 GitHub Actions 变成永不停机的服务器，也不依赖自托管在你电脑上的 runner。

官方参考：

- https://docs.github.com/en/actions/reference/limits
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- https://docs.github.com/en/actions/concepts/billing-and-usage
