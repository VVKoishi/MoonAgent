---
name: moon-cron
description: 跨平台定时任务管理。Linux/macOS 使用 cron，Windows 使用 SCHTASKS。支持两种模式：Mode A 定时执行任意系统命令，Mode B 通过 `-p` headless 模式定时触发 AI Agent 执行 prompt（默认 claude，可用 MOON_AI 环境变量替换为 gemini/moon 等）。当用户需要创建、查看、删除定时任务，或定时触发 Agent 执行某个任务时使用。
---

# moon-cron

- **Windows** → SCHTASKS
- **Linux/macOS** → cron（`crontab -e`）

cron 时间格式：`分 时 日 月 周`，`*` 表示任意值。示例 `0 9 * * *` = 每天 09:00。

---

## 命名约定

所有由 moon-cron 创建的任务，**任务名称必须以 `Moon` 开头**（如 `MoonDailyReport`、`MoonSvnCheck`），便于与系统或第三方任务区分、统一管理和查询。

---

## Mode A：定时执行命令

**Linux/macOS** — 写入 `crontab -e`：
```
0 9 * * * /bin/bash -c "命令"
```

**Windows:**
```powershell
SCHTASKS /Create /SC DAILY /TN "TaskName" /TR "命令" /ST 09:00
```

---

## Mode B：定时触发 AI Agent

通过 `-p` headless 模式向 AI CLI 发送 prompt。默认 `claude`，`MOON_AI` 可覆盖为 `gemini`、`moon` 等。

**Linux/macOS** — 写入 `crontab -e`：
```
0 9 * * * /bin/bash -c '${MOON_AI:-claude} -p "每日任务提示"'
```

**Windows:**
```powershell
$ai = if ($env:MOON_AI) { $env:MOON_AI } else { "claude" }
SCHTASKS /Create /SC DAILY /TN "AgentTask" /TR "$ai -p `"每日任务提示`"" /ST 09:00
```

---

## 管理命令

| 操作 | Linux/macOS | Windows |
|------|-------------|---------|
| 查看所有 | `crontab -l` | `SCHTASKS /Query /FO LIST` |
| 查看 Moon 任务 | 见下方代码块 | 见下方代码块 |
| 查看指定 | — | `SCHTASKS /Query /TN "Name"` |
| 立即运行 | 直接执行命令 | `SCHTASKS /Run /TN "Name"` |
| 删除 | `crontab -e` 删除对应行 | `SCHTASKS /Delete /TN "Name" /F` |

**查看所有 Moon 任务状态（含上次结果、下次执行时间）：**

```powershell
# Windows
Get-ScheduledTask "Moon*" | ForEach-Object {
    $i = Get-ScheduledTaskInfo $_.TaskName
    [PSCustomObject]@{ Task=$_.TaskName; State=$_.State; LastRun=$i.LastRunTime; Result=$i.LastTaskResult; NextRun=$i.NextRunTime }
} | Format-Table -AutoSize
```

```bash
# Linux/macOS
crontab -l | grep Moon
```

---

## 与 moon-task 配合（推荐）

使用 `pythonw.exe`（无控制台窗口版 Python）直接调用 `task_runner.py`，无弹窗、无密码提示。

```powershell
SCHTASKS /Create /SC DAILY /TN "MoonDesyncLog" /ST 09:00 /TR "C:\Users\Admin\AppData\Local\Programs\Python\Python314\pythonw.exe F:\MoonAgent\.claude\skills\moon-task\scripts\task_runner.py F:\MoonAgent\.claude\skills\moon-task\tasks\desync-log.TASK.md"
```

要点：
- 建议使用绝对路径的 `pythonw.exe`，避免因 Task Scheduler PATH 不含 Python 而失败。
- `task_runner.py` 与 `*.TASK.md` 使用绝对路径。
- 注册后立即 `SCHTASKS /Run /TN "任务名"` 验证。
