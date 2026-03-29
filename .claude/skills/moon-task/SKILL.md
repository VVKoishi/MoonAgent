---
name: moon-task
description: >
  Lightweight TASK.md workflow orchestrator — "Jupyter Notebook for the terminal".
  编排多步工作流：shell、python、AI 单元格顺序执行，通过 stdout 指令控制跳转和分支。
  当用户需要创建、编辑或运行 TASK.md 工作流时使用。
---

# moon-task

将 Markdown 变成可执行工作流。每个围栏代码块是一个**单元格**，按顺序执行；单元格向 stdout 输出控制指令，实现跳转、变量传递、条件分支。

```bash
python scripts/task_runner.py workflow.TASK.md               # 运行
python scripts/task_runner.py workflow.TASK.md --list        # 列出所有格
python scripts/task_runner.py workflow.TASK.md --dry-run     # 演练
python scripts/task_runner.py workflow.TASK.md --from setup  # 从指定格开始运行
python scripts/task_runner.py workflow.TASK.md --cell setup  # 只运行这一个格，运行完即退出
python scripts/task_runner.py workflow.TASK.md --var K=V     # 传入变量（可重复）
python scripts/task_runner.py workflow.TASK.md --quiet       # 静默：不输出任何内容，退出码反映成败
python scripts/test_examples.py                              # 测试示例
```

---

## 单元格语法

````
```<lang> id=my-step title="说明" on_fail=skip cond={{ENV}}==prod timeout=60
代码内容
```
````

| 属性 | 默认 | 说明 |
|------|------|------|
| `id` | `cell-N` | 唯一标识，供跳转引用 |
| `title` | — | 显示名称 |
| `on_fail` | `stop` | 失败时：`stop` \| `skip` \| `<cell-id>` |
| `on_success` | `next` | 成功时：`next` \| `stop` \| `<cell-id>` |
| `cond` | — | 执行条件，使用 `{{KEY}}` 语法；为假时跳到下一格，不触发 on_fail/on_success，不更新 LAST_* |
| `timeout` | `300` | 超时秒数；超时视为失败（rc=124），触发 `on_fail` |

**支持的 lang：**

| lang | 说明 |
|------|------|
| `shell` / `bash` / `sh` | 系统 shell 脚本 |
| `powershell` / `ps1` | PowerShell 脚本 |
| `cmd` | Windows CMD 批处理 |
| `python` / `py` | Python 脚本（共享 `variables` 字典） |
| `ai` | AI 提示词（自动检测 claude / gemini / moon，不可用时触发 `on_fail`） |
| `note` / `md` / `markdown` / `text` | 仅打印内容，不执行，rc=0 |
| 其他 | 跳过并输出警告 |

---

## 变量系统

moon-task 维护一个统一的**变量字典**，三种引用方式对应不同场景，访问的是同一份数据：

| 语法 | 场景 | 求值时机 |
|------|------|---------|
| `{{KEY}}` | 代码体（所有 lang）和 `cond=` 属性 | 执行前模板替换，不影响宿主语言语法（shell `$VAR` 不冲突） |
| `variables["KEY"]` | Python 单元格内部 | exec 运行时，适合动态 key 或 `variables.get("KEY", default)` |

### 定义变量

**Frontmatter 默认值**（文件级初始状态，可被 CLI 覆盖）：
```yaml
---
vars:
  BASE_DIR: /tmp/work
  ENV: dev
---
```

**CLI 覆盖**（优先级高于 frontmatter）：
```bash
python scripts/task_runner.py file.TASK.md --var ENV=prod --var VERSION=1.2
```

**单元格内通过 stdout 指令**（动态设置，后续格可立即使用）：
```
TASK_VAR: KEY=VALUE
```

### 内置变量

| 变量 | 说明 |
|------|------|
| `TASK_FILE` | 当前 TASK.md 文件绝对路径 |
| `TASK_DIR` | 当前 TASK.md 文件所在目录 |
| `LAST_CELL` | 上一个已执行单元格的 id |
| `LAST_RC` | 上一个单元格的退出码（字符串，如 `"0"` / `"1"` / `"124"`） |
| `LAST_STDOUT` | 上一个单元格的标准输出（已剥离 `TASK_*` 指令行） |
| `LAST_STDERR` | 上一个单元格的标准错误 |

> **注意：** `LAST_*` 在每格**实际执行后**自动更新。被 `cond` 条件跳过或输出 `TASK_SKIP:` 的格不更新 `LAST_*`。初始值均为空字符串 `""`。

---

## 控制指令（stdout 特殊行，被解释器拦截，不出现在终端输出中）

| 指令 | 效果 |
|------|------|
| `TASK_VAR: KEY=VALUE` | 设置变量。可多行，每行一个 |
| `TASK_JUMP: cell-id` | 无条件跳转到指定格（覆盖 on_fail/on_success） |
| `TASK_STOP: 消息` | 立即停止整个工作流，视为成功；消息可选，打印后不再执行 |
| `TASK_FAIL: 消息` | 立即停止整个工作流，视为失败，打印消息 |
| `TASK_SKIP:` | 标记本格为 skipped，继续下一格（不更新 LAST_*） |

---

## AI 单元格

`ai` 块的内容作为 prompt 发送给 AI 后端，**响应中的 `TASK_*` 指令同样生效**——让 AI 直接参与路由决策。

代码体支持 `{{KEY}}` 替换，包括 `LAST_*` 内置变量：

> ⚠️ **重要限制：`ai` 块内容不允许使用三反引号（` ``` `）语法。**
> 三反引号会被 TASK.md 解析器识别为单元格结束标记，提前截断 `ai` 块，导致之后的内容丢失。
> 若需在 prompt 中展示代码格式，改用缩进（4 空格）或单/双反引号行内格式。

````
```ai id=triage cond={{LAST_RC}}!=0
命令失败，退出码：{{LAST_RC}}
错误信息：
{{LAST_STDERR}}

根据错误原因输出以下之一（单独一行，不含其他字符）：
- 网络超时 → TASK_JUMP: retry
- 权限不足 → TASK_FAIL: 检查凭据
- 其他      → TASK_FAIL: 请人工介入
```
````

**AI 后端解析顺序：**

1. `MOON_AI` 环境变量（`claude` / `gemini` / `moon` / 自定义路径）
2. 自动探测：`claude` → `gemini` → `moon`


```bash
export MOON_AI=gemini   # 切换后端
export MOON_AI=moon     # MoonAgent headless
```

---

## 异常处理

| 场景 | 默认行为 | 调整方式 |
|------|----------|----------|
| 退出码 ≠ 0 | 停止工作流（stop） | `on_fail=skip` 跳过 · `on_fail=<id>` 跳转 |
| 超时（rc=124） | 视为失败，触发 on_fail | `timeout=N`（秒） |
| `cond=` 条件为假 | 跳到下一格 | 不触发 on_fail/on_success，不更新 LAST_* |
| `{{VAR}}` 未定义 | 保留占位符 + 打印警告 | 提前在 frontmatter 或前置格中设置 |
| 跳转目标不存在 | 报错停止 | — |

**退出码**：`0` 全部成功 · `1` 有格失败 · `2` 配置错误 · `130` Ctrl+C

---

## 常用模式速查

**变量传递**
```python
# cell-A
print("TASK_VAR: FILE=/tmp/data.json")
```
```python
# cell-B：{{FILE}} 已替换为 /tmp/data.json
import json
with open("{{FILE}}") as f:
    data = json.load(f)
```

**失败重试**

```shell id=fetch on_fail=retry
wget {{URL}} -O /tmp/data.zip
```
```shell id=retry on_fail=stop
sleep 5 && wget {{URL}} -O /tmp/data.zip
```

**条件跳过**

```python id=process cond={{SKIP_PROCESS}}!=true
# 仅当 SKIP_PROCESS 不等于 "true" 时执行
...
```

**AI 故障分析 + 流程控制**

```ai id=analyze args="--allowedTools Bash,Read" on_success=stop on_fail=stop
上一步（{{LAST_CELL}}）失败，退出码 {{LAST_RC}}。

读取任务文件 `{{TASK_FILE}}`，找到 id=`{{LAST_CELL}}` 单元格的完整代码，结合以下错误分析失败原因：
{{LAST_STDERR}}

- 如果可以修复，直接执行修复并重试；修复成功后单独输出一行：`TASK_STOP: <修复结论>`
- 无法修复则单独输出一行：`TASK_FAIL: <简短原因>`
```

---

## 示例文件

| 文件 | 内容 |
|------|------|
| `examples/hello-world.TASK.md` | 跨平台入门：OS 检测、TASK_JUMP 分支、PowerShell/Shell、变量传递、LAST_RC 验证 |
| `examples/lunar-mission.TASK.md` | 2047 年，一艘飞船独自飞向月球——船体破损，信号异常，深空中有什么东西在等着它。跑完整个流程，你会明白 moon-task 能做什么。 |
