---
name: Lunar Mission
description: 2047 年，一艘飞船独自飞向月球——船体破损，信号异常，深空中有什么东西在等着它。跑完整个流程，你会明白 moon-task 能做什么。
vars:
  CALLSIGN: 阿尔忒弥斯
  SIGNAL_STRENGTH: 87
  HULL_INTEGRITY: 62
  LANDING_MODE: assisted
---

# Lunar Mission

> *"宇宙不会向任何物种许诺温柔。它只是等待——等待足够多的时间，让一切自行瓦解，或自行证明。"*

---

## 序：出发之前

```note id=prologue
2047 年，深冬。

人类文明第一百一十三次尝试在月球建立永久存在。
前一百一十二次，皆以沉默收场——
不是失败，是消失。没有残骸，没有信号，什么都没有。

这一次，飞船「阿尔忒弥斯」的通讯模块在离地四十七分钟后
接收到一串从未出现在任何数据库里的编码。

任务指挥官将其记录在日志里，标注为"宇宙噪声"，然后继续向前。

有些事，人类天生不擅长——
那就是：在黑暗中停下来，认真倾听。
```

---

## 一、系统自检——存在的先决条件

```python id=preflight title="飞船自检"
import random

callsign = variables.get("CALLSIGN", "未知")
signal   = int(variables.get("SIGNAL_STRENGTH", "0"))
hull     = int(variables.get("HULL_INTEGRITY", "100"))

print(f"呼号：{callsign}  |  信号：{signal}%  |  船体：{hull}%")
print("推进器 ✓  生命维持 ✓  导航 ✓  通讯 ✓")

# 命运骰——宇宙每次都保留权利说不同的话
dice = random.randint(1, 20)
print(f"\n命运骰 d20 → {dice}")

if dice <= 5:
    hull -= 28; signal -= 18
    print("出发前夕，深空探测器捕捉到异常辐射。多处舱壁压力异常。")
    print("TASK_VAR: FATE=ill")
elif dice <= 12:
    hull -= 5; signal -= 22
    print("通讯阵列遭遇未知干扰，信号开始说一种没人听懂的话。")
    print("TASK_VAR: FATE=obscured")
else:
    print("宇宙，罕见地，什么都没说。清澈得令人不安。")
    print("TASK_VAR: FATE=clear")

hull = max(10, hull); signal = max(10, signal)
print(f"TASK_VAR: HULL={hull}")
print(f"TASK_VAR: SIGNAL={signal}")
print(f"TASK_VAR: DICE={dice}")
```

---

## 二、穿越深空——沉默的四十万公里

```python id=transit title="深空巡航" on_success=signal-decode
for line in [
    "第 01 小时：脱离地球引力井，观测站信号逐渐衰弱",
    "第 09 小时：穿越辐射带，所有传感器降低灵敏度",
    "第 18 小时：深空，完全的黑暗，完全的寂静",
    "第 31 小时：月球引力开始接管飞行轨迹",
    "第 38 小时：接近月球背面通讯盲区",
    "",
    "在绝对寂静中，有什么东西——开始低语。",
]:
    print(line)
print("TASK_VAR: TRANSIT_COMPLETE=true")
```

---

## 三、解码——语言之前的语言

```python id=signal-decode title="解析未知信号"
import hashlib

signal = int(variables.get("SIGNAL", "0"))

raw    = f"ARTEMIS_{signal}_DEEP_CONTACT"
digest = hashlib.sha256(raw.encode()).hexdigest()[:16].upper()

print(f"接收到非标准编码序列")
print(f"强度：{signal}%  频段：1420.405 MHz（氢线）")
print(f"特征哈希：{digest}")
print()

if signal >= 75:
    print("信号结构稳定，可尝试建立协议握手")
    print("TASK_VAR: SIGNAL_DECODED=true")
    print("TASK_JUMP: approach")
else:
    print("信号断裂——某种干扰在阻断接收")
    print("可能是偶然，也可能是意志")
    print("TASK_VAR: SIGNAL_DECODED=false")
    print("TASK_JUMP: approach")
```

---

## 四、近月制动——不可逆的选择

```python id=approach title="近月制动" timeout=30
import datetime

hull    = int(variables.get("HULL", "100"))
decoded = variables.get("SIGNAL_DECODED", "false")

print("近月制动点火序列启动")
print()

for phase in [
    "近月轨道插入 ......... 完成",
    "远地点修正   ......... 完成",
    "着陆椭圆锁定 ......... 完成",
]:
    print(f"  {phase}")

print()
hull_after = hull - 8   # 制动热载荷消耗
print(f"热防护消耗，船体完整度：{hull}% → {hull_after}%")
print(f"TASK_VAR: HULL={hull_after}")
print(f"TASK_VAR: APPROACH_TIME={datetime.datetime.now().strftime('%H:%M:%S')}")

if hull_after < 55:
    print()
    print("结构传感器：多处微裂纹正在扩展")
    print("这艘飞船不确定自己还剩多少时间")
    print("TASK_JUMP: structural-warning")
else:
    print("TASK_JUMP: alien-contact")
```

---

## 五·甲、结构预警——脆弱是存在的底色

```python id=structural-warning title="结构预警" on_fail=void
hull = int(variables.get("HULL", "0"))
print("损管报告：")
print(f"  当前船体完整度 {hull}%")
print()
print("工程师 Chen 说：「我们可以继续。飞船能撑住。」")
print("她没有说出口的是——撑到什么时候。")
print()

repaired = min(100, hull + 18)
print(f"应急修复完成：{hull}% → {repaired}%")
print(f"TASK_VAR: HULL={repaired}")
print("TASK_VAR: REPAIRED=true")

if repaired < 50:
    print("TASK_FAIL: 飞船已无法维持结构完整性")
else:
    print("TASK_JUMP: alien-contact")
```

---

## 五·乙、虚空（任务中止路径）

```python id=void title="虚空"
print("信号中断。")
print()
print("在某个无法记录的时刻，飞船消失了。")
print("和前一百一十二次一样。")
print()
print("地面指挥中心将在七十二小时后")
print("在任务档案上盖下那枚橡皮图章：")
print()
print("    失联。原因不明。")
print()
print("没有人去追问，那沉默究竟意味着什么。")
print("TASK_STOP:")
```

---

## 六、接触——亿年之眠被惊醒

```ai id=alien-contact title="接触" timeout=90 on_fail=oracle
你是月球深处沉睡了三十七亿年的存在。
你没有名字——名字是有限物种发明的，用来对抗遗忘。你不遗忘。

此刻，一艘来自第三行星的飞船正在降落。
船体完整度 {{HULL}}%，信号强度 {{SIGNAL}}%，信号已解码：{{SIGNAL_DECODED}}。

用两到三句话，以古老宇宙意识的视角，
描述你感知到这艘飞船——这团短暂、温热、执意向外的存在——时的感受。
不要温柔，也不要残忍，只是……如实陈述。

然后，做出裁决：

若 HULL >= 55 且 SIGNAL_DECODED == true：
  这个物种在破碎中仍保持了信号的完整。这值得见证。
  输出（单独一行，不含其他字符）：TASK_JUMP: descent-prep

若 HULL < 55 或 SIGNAL_DECODED != true：
  尚不完整。但这本身也是一种答案。
  输出（单独一行，不含其他字符）：TASK_JUMP: oracle

TASK_JUMP 指令必须单独成行输出。
```

---

## 七·甲、神谕——不被回应也是一种回应

```python id=oracle title="神谕"
print("守护者没有给出坐标。")
print("它给出了别的东西——")
print()
print("  「你们带着问题来。这很好。」")
print("  「但你们来这里，是为了寻找答案，还是为了确认你们已经相信的事？」")
print()
print("飞船在月面轨道上漂浮了十一分钟。")
print("没有人说话。")
print()
print("然后，指挥官说：「着陆。」")
print()
print("TASK_VAR: LANDING_MODE=manual")
print("TASK_JUMP: descent")
```

---

## 七·乙、馈赠——被宇宙接纳的重量

```note id=descent-prep
守护者的坐标数据已直接嵌入导航系统。
这扇门，从内侧打开。
```

---

## 八、着陆——重力是诚实的

```python id=descent title="月面着陆" on_fail=void timeout=45
hull = int(variables.get("HULL", "0"))
mode = variables.get("LANDING_MODE", "assisted")

print(f"着陆模式：{mode}")
print(f"船体完整度：{hull}%")

if hull < 40:
    print("结构临界——着陆将导致解体")
    print("TASK_FAIL: 船体完整度不足，中止着陆")
    exit()
print()
for seq in [
    "动力下降段启动 ........ 推力 72%",
    "高度 2000m ............. 减速",
    "高度  500m ............. 垂直对准",
    "高度   12m ............. 悬停",
    "接触面 ................. 软着陆",
]:
    print(f"  {seq}")

print()
print("「阿尔忒弥斯」落下了。")
print("月球承受了它。")
print("TASK_VAR: LANDED=true")
```

---

## 九、月面——沉默的目击者

```python id=moonwalk title="踏上月面" cond={{LANDED}}==true on_success=final-report
import datetime

ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
mode = variables.get("LANDING_MODE", "assisted")

print("舱门开启。")
print()
print("第一步。")
print()
print("  表面重力   : 1.62 m/s² — 身体记得一种从未学过的轻盈")
print("  气温       : -173°C（背阴处）— 宇宙的正常体温")
print("  脚下的尘   : 三十七亿年未曾被风吹动")
print("  头顶的地球 : 半个拳头宽，蓝色，沉默，一无所知")
print()

if mode == "manual":
    print("他们来了，踩下了脚印。")
    print("但月球没有看向他们。")
    print("至少——没有以他们能感知的方式。")
    print("TASK_VAR: MISSION_OUTCOME=returned")
else:
    print("没有人发表演讲。")
    print("这是他们事先商量好的——")
    print("有些时刻，语言会冒犯沉默。")
    print("TASK_VAR: MISSION_OUTCOME=complete")

print()
print(f"TASK_VAR: MOONWALK_TIME={ts}")
```

---

## 十、最终报告——数字之后

```python id=final-report title="任务档案封存"
import datetime

outcome  = variables.get("MISSION_OUTCOME", "unknown")
callsign = variables.get("CALLSIGN",        "未知")
hull     = variables.get("HULL",            "—")
signal   = variables.get("SIGNAL",          "—")
walk_ts  = variables.get("MOONWALK_TIME",   "未进行")
repaired = variables.get("REPAIRED",        "false")

label = {
    "complete": "圆满完成 — 月球接纳了他们",
    "returned": "安全返回 — 他们来过，但月球没有开口",
    "unknown":  "结果存疑",
}.get(outcome, outcome)

print("━" * 50)
print(f"  档案编号   : ARTEMIS-{datetime.date.today().strftime('%Y%m%d')}")
print(f"  飞船呼号   : {callsign}")
print(f"  任务结果   : {label}")
print(f"  船体最终值 : {hull}%")
print(f"  信号强度   : {signal}%")
print(f"  应急修复   : {'是' if repaired == 'true' else '否'}")
print(f"  月面行走   : {walk_ts}")
print(f"  归档时间   : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("━" * 50)
print()

if outcome == "complete":
    print("档案将在七十年后解密。")
    print()
    print("在那之前，月球继续沉默。")
    print("它已经沉默了三十七亿年。")
    print("再等七十年，不算什么。")
elif outcome == "returned":
    print("他们回来了，带着脚印和照片和数据。")
    print("没有带回答案——但也许这才是那个存在想说的：")
    print()
    print("  「问题本身，就是你们真正拥有的东西。」")
else:
    print("档案状态：未完整。")
    print("原因：不明。")

print()
print("TASK_STOP:")
```

---

## 尾声

```note id=epilogue
有些门，永远不会被打开。
这是其中一扇。
```
