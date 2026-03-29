---
name: Hello World
description: moon-task 跨平台入门示例：OS 检测、条件跳转、变量传递、LAST_* 内置变量
vars:
  GREETING: Hello
---

# Hello World

演示：OS 检测 → 条件 `TASK_JUMP` → 平台分支（PowerShell / Shell）→ 变量传递 → LAST_* 自动注入 → 汇总。

---

## 1. 检测操作系统

```python id=check-env title="检测操作系统"
import platform

os_type = "windows" if platform.system() == "Windows" else "unix"
print(f"当前平台：{platform.system()}")
print(f"TASK_VAR: OS_TYPE={os_type}")
if os_type == "windows":
    print("TASK_JUMP: run-powershell")
else:
    print("TASK_JUMP: run-shell")
```

## 2. Windows：PowerShell 打印环境变量

```powershell id=run-powershell title="PowerShell 打印环境变量" on_success=verify-last
$msg = "PowerShell | OS=$env:OS | User=$env:USERNAME | ComputerName=$env:COMPUTERNAME"
Write-Output $msg
Write-Output "TASK_VAR: BRANCH_MSG=$msg"
```

## 3. macOS/Linux：Shell 打印环境变量

```shell id=run-shell title="Shell 打印环境变量" on_success=verify-last
MSG="Shell | OS=$(uname -s) | User=$(whoami) | Host=$(hostname)"
echo "$MSG"
echo "TASK_VAR: BRANCH_MSG=$MSG"
```

## 4. 验证 LAST_* 内置变量

上一格执行后，runner 自动将退出码/输出注入 LAST_* 变量，可在任意格中使用 `{{LAST_RC}}` 或通过 `variables` 字典访问。

```python id=verify-last title="验证 LAST_* 内置变量" on_success=show-result
last_cell   = variables.get("LAST_CELL", "")
last_rc     = variables.get("LAST_RC",   "")
last_stdout = variables.get("LAST_STDOUT", "")

print(f"上一格 id    : {last_cell}")
print(f"上一格退出码 : {last_rc}  ({{LAST_RC}} = {{LAST_RC}})")

assert last_rc == "0", f"期望退出码=0，实际={last_rc}"
assert last_cell in ("run-powershell", "run-shell"), f"异常的 LAST_CELL: {last_cell}"
print("LAST_* 验证通过 ✓")
```

## 5. 汇总两个分支设置的变量

```python id=show-result title="汇总结果"
greeting   = variables.get("GREETING",   "Hello")
os_type    = variables.get("OS_TYPE",    "unknown")
branch_msg = variables.get("BRANCH_MSG", "(未设置)")

print(f"{greeting}！你在 {os_type} 上运行。")
print(f"来自平台分支的消息：")
print(f"  {branch_msg}")
print("TASK_STOP:")
```

## 6. 不可达：若上一格未 TASK_STOP 则报错

```python id=unreachable
print("TASK_FAIL: show-result 应已 TASK_STOP，此格不应执行")
```
