---
name: lark-message
description: 通过飞书/Lark 开放平台 API 向指定群或用户发送消息。支持文本、Markdown（卡片）、图片、文件、视频、语音、表情包等类型。需要 LARK_APP_ID 和 LARK_APP_SECRET 环境变量。当用户需要主动向飞书发送通知、结果或文件时使用。
---

# Lark Message Skill

向飞书群组或用户发送消息，支持文本、Markdown（卡片）、图片、文件类型。

## 环境变量

| 变量 | 说明 |
|------|------|
| `LARK_APP_ID` | 飞书应用 App ID |
| `LARK_APP_SECRET` | 飞书应用 App Secret |

## Step 1：获取 tenant_access_token

每次发送前先获取 token（有效期 2 小时，无需缓存）：

```bash
TOKEN=$(curl -s -X POST 'https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json' \
  -d "{\"app_id\":\"$LARK_APP_ID\",\"app_secret\":\"$LARK_APP_SECRET\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['tenant_access_token'])")
```

---

## Step 2：发送消息

> ⚠️ **编码注意：构造消息体时，必须用 Python `json.dumps`，禁止手拼 shell 字符串**，否则换行、反斜杠、双引号等字符无法正确转义。

所有发送接口：

```
POST https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=<type>
Authorization: Bearer <tenant_access_token>
Content-Type: application/json; charset=utf-8
```

`receive_id_type` 可选值：

| 值 | 说明 | 示例 |
|----|------|------|
| `chat_id` | 群聊 ID | `oc_xxx` |
| `open_id` | 用户 Open ID | `ou_xxx` |
| `user_id` | 用户 User ID | `xxx` |
| `union_id` | 用户 Union ID | `xxx` |
| `email` | 用户邮箱 | `user@example.com` |

---

### 发送 Markdown 消息（卡片）

`msg_type` 用 `interactive`，`content` 为卡片 JSON 转义字符串：

```bash
BODY=$(python -c "import json; md=open('EXAMPLE.md').read(); card={'schema':'2.0','body':{'elements':[{'tag':'markdown','element_id':'markdown_1','content':md}]}}; print(json.dumps({'receive_id':'<chat_id>','msg_type':'interactive','content':json.dumps(card)}))")
curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "$BODY"
```

---

### 发送文本消息

```bash
# ✅ 正确：用 Python 构造 JSON，自动处理所有转义
BODY=$(python3 -c "
import json, os
text = '''<消息内容，可含换行
和特殊字符>'''
print(json.dumps({
    'receive_id': '<chat_id>',
    'msg_type': 'text',
    'content': json.dumps({'text': text})
}))
")
curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "$BODY"
```

如果消息内容存在变量中（如 `$MSG`）：

```bash
BODY=$(python3 -c "
import json, sys
text = sys.argv[1]
print(json.dumps({
    'receive_id': '<chat_id>',
    'msg_type': 'text',
    'content': json.dumps({'text': text})
}))
" "$MSG")
curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "$BODY"
```

**content 结构**（转义前）：
```json
{"text": "消息内容"}
```

支持的文本特性：
- 换行：文本中直接换行即可（Python json.dumps 会自动转为 `\n`）
- @用户：`<at user_id="ou_xxx">姓名</at>`，@所有人：`<at user_id="all"></at>`
- 加粗：`**文本**`，斜体：`<i>文本</i>`，下划线：`<u>文本</u>`，删除线：`<s>文本</s>`
- 超链接：`[显示文字](https://url)`

---

### 发送图片消息

发送前需先上传图片获取 `image_key`：

```bash
# 1. 上传图片
IMAGE_KEY=$(curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/images' \
  -H "Authorization: Bearer $TOKEN" \
  -F 'image_type=message' \
  -F 'image=@/path/to/image.png' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['image_key'])")

# 2. 发送图片消息
curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "{
    \"receive_id\": \"<chat_id>\",
    \"msg_type\": \"image\",
    \"content\": \"{\\\"image_key\\\":\\\"$IMAGE_KEY\\\"}\"
  }"
```

**content 结构**（转义前）：
```json
{"image_key": "img_xxx"}
```

---

### 发送文件消息

发送前需先上传文件获取 `file_key`：

```bash
# 1. 上传文件（file_type: pdf / doc / xls / ppt / stream(其他类型)）
FILE_KEY=$(curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/files' \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file_type=stream' \
  -F 'file_name=<文件名>' \
  -F 'file=@/path/to/file' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['file_key'])")

# 2. 发送文件消息
curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "{
    \"receive_id\": \"<chat_id>\",
    \"msg_type\": \"file\",
    \"content\": \"{\\\"file_key\\\":\\\"$FILE_KEY\\\"}\"
  }"
```

**content 结构**（转义前）：
```json
{"file_key": "file_v2_xxx"}
```

`file_type` 支持值：`opus`（音频）、`mp4`（视频）、`pdf`、`doc`、`xls`、`ppt`、`stream`（其他类型）。文件大小不超过 30MB，不允许空文件。

---

### 发送视频消息

先用上传文件接口上传视频（`file_type=mp4`）取得 `file_key`，可选再上传封面图取得 `image_key`。可传 `duration`（毫秒）显示时长：

```json
{"file_key": "file_v2_xxx", "image_key": "img_xxx"}
```

```bash
# 上传视频（可加 -F 'duration=3000' 指定时长毫秒）
FILE_KEY=$(curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/files' \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file_type=mp4' \
  -F 'file_name=video.mp4' \
  -F 'duration=3000' \
  -F 'file=@/path/to/video.mp4' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['file_key'])")

# msg_type 为 media
-d "{\"receive_id\":\"<chat_id>\",\"msg_type\":\"media\",\"content\":\"{\\\"file_key\\\":\\\"$FILE_KEY\\\",\\\"image_key\\\":\\\"$IMAGE_KEY\\\"}\"}"
```

---

### 发送语音消息

语音必须使用 `opus` 格式（`file_type=opus`），其他格式需先转换：

```bash
ffmpeg -i input.mp3 -acodec libopus -ac 1 -ar 16000 output.opus
```

上传后取 `file_key`，可传 `duration`（毫秒）显示时长：

```json
{"file_key": "file_v2_xxx"}
```

```bash
# 上传语音
FILE_KEY=$(curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/files' \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file_type=opus' \
  -F 'file_name=audio.opus' \
  -F 'duration=3000' \
  -F 'file=@/path/to/audio.opus' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['file_key'])")

# msg_type 为 audio
-d "{\"receive_id\":\"<chat_id>\",\"msg_type\":\"audio\",\"content\":\"{\\\"file_key\\\":\\\"$FILE_KEY\\\"}\"}"
```

---

### 发送表情包消息

`file_key` 仅支持发送机器人收到的表情包：

```json
{"file_key": "file_v2_xxx"}
```

```bash
# msg_type 为 sticker
-d "{\"receive_id\":\"<chat_id>\",\"msg_type\":\"sticker\",\"content\":\"{\\\"file_key\\\":\\\"$FILE_KEY\\\"}\"}"
```

---

## 完整示例：一键发送文本到群

```bash
TOKEN=$(curl -s -X POST 'https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json' \
  -d "{\"app_id\":\"$LARK_APP_ID\",\"app_secret\":\"$LARK_APP_SECRET\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['tenant_access_token'])")

curl -s -X POST 'https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{
    "receive_id": "oc_xxx",
    "msg_type": "text",
    "content": "{\"text\":\"Hello from MoonAgent!\"}"
  }'
```

## 如何获取 chat_id

`chat_id` 是群聊的唯一标识，格式为 `oc_` 开头的字符串，如 `oc_a0553eda9014c201e6969b478895c230`。

### 查询机器人所在所有群

```bash
curl -s 'https://open.larksuite.com/open-apis/im/v1/chats?page_size=20' \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data['data']['items']:
    print(c['chat_id'], c.get('name',''))
"
```

响应中每条记录包含 `chat_id` 和群名称（`name`），找到目标群后复制其 `chat_id` 即可。

> 前提：机器人已加入目标群。若机器人未在群内，需先将机器人邀请入群，或通过创建群接口建群后从响应中取 `chat_id`。

---

## 错误处理

响应体中 `code != 0` 表示失败，常见错误：

| code | 说明 |
|------|------|
| `99991663` | token 过期，重新获取 |
| `230002` | receive_id 无效 |
| `230013` | 机器人不在目标群内 |
