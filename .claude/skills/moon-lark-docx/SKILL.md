---
name: moon-lark-docx
description: 飞书云文档（docx）完整操作。支持创建文档、添加/转移用户权限、Markdown 转文档块并插入（含图片和文件上传）、读取文档内容转 Markdown。当用户需要创建飞书文档、写入内容、上传素材或读取文档时使用。需要 LARK_APP_ID 和 LARK_APP_SECRET 环境变量。
---

# Moon Lark Docx Skill

操作飞书云文档（docx 类型），涵盖创建、内容写入（含图片/文件素材）、读取、权限管理。

## 环境变量

| 变量 | 说明 |
|------|------|
| `LARK_APP_ID` | 飞书应用 App ID |
| `LARK_APP_SECRET` | 飞书应用 App Secret |
| `LARK_USER_EMAIL` | （可选）文档创建后自动授权的用户公司邮箱 |

---

## Step 0：获取 tenant_access_token

每次调用前先获取 token（有效期 2 小时）：

```bash
TOKEN=$(curl -s -X POST 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json' \
  -d "{\"app_id\":\"$LARK_APP_ID\",\"app_secret\":\"$LARK_APP_SECRET\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['tenant_access_token'])")
```

---

## Step 1：创建文档

```bash
DOC_ID=$(curl -s -X POST 'https://open.feishu.cn/open-apis/docx/v1/documents' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{
    "folder_token": "",
    "title": "文档标题"
  }' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['document']['document_id'])")
echo "DOC_ID=$DOC_ID"
echo "URL: https://sample.feishu.cn/docx/$DOC_ID"
```

- `folder_token`：可选，不传或传空表示创建到根目录；`tenant_access_token` 下只能指定应用创建的文件夹
- 返回的 `document_id` 用于后续所有操作

### 创建后自动授权给用户

文档创建完成后，默认立即将权限授予当前用户：

- **有 `LARK_USER_EMAIL` 环境变量**：自动执行以下授权命令
- **无环境变量**：创建文档后询问用户的公司邮箱，获取后再执行以下授权命令

```bash
# USER_EMAIL 替换为实际邮箱
curl -s -X POST "https://open.feishu.cn/open-apis/drive/v1/permissions/$DOC_ID/members?type=docx" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "{
    \"member_type\": \"email\",
    \"member_id\": \"$USER_EMAIL\",
    \"perm\": \"full_access\",
    \"type\": \"user\"
  }"
echo "已授权 $USER_EMAIL 可管理权限"
```

- `perm` 默认 `full_access`（可管理），可按需改为 `edit`（可编辑）或 `view`（可阅读）

---

## Step 2：Markdown 转换为文档块

```bash
BLOCKS_JSON=$(curl -s -X POST 'https://open.feishu.cn/open-apis/docx/v1/documents/blocks/convert' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{
    "content_type": "markdown",
    "content": "# 标题\n\n正文内容\n\n- item1\n- item2\n"
  }')
echo $BLOCKS_JSON | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['data'], ensure_ascii=False, indent=2))"
```

- `content_type`：`markdown` 或 `html`
- 支持块类型：文本、1-9级标题、无序/有序列表、代码块、引用、待办、图片、表格
- **含表格**：插入前必须去除所有 Table 块中的 `merge_info` 字段（只读属性，传入会报错）
- **含图片**：转换后 Image Block 内容为空，需按 Step 4 上传素材并绑定

---

## Step 3：插入块到文档（创建嵌套块）

因请求体较大，先将内容写入文件再发送：

```bash
# 将转换后的块写入 payload 文件，index=-1 表示追加到末尾
# children_id 列出所有顶层块的 block_id；descendants 包含所有块（扁平列表）
cat > /tmp/blocks_payload.json << 'EOF'
{
  "index": -1,
  "children_id": ["heading_1", "text_1"],
  "descendants": [
    {
      "block_id": "heading_1",
      "block_type": 3,
      "heading1": {
        "elements": [{"text_run": {"content": "标题"}}]
      },
      "children": []
    },
    {
      "block_id": "text_1",
      "block_type": 2,
      "text": {
        "elements": [{"text_run": {"content": "正文内容"}}]
      },
      "children": []
    }
  ]
}
EOF

# 插入到文档根节点（block_id 路径参数与 document_id 相同）
curl -s -X POST "https://open.feishu.cn/open-apis/docx/v1/documents/$DOC_ID/blocks/$DOC_ID/descendant?document_revision_id=-1" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d @/tmp/blocks_payload.json
```

- `block_id` 路径参数：插入文档根节点时与 `document_id` 相同；插入某块内部时填该块的 `block_id`
- `document_revision_id=-1`：始终基于最新版本
- 单次最多插入 **1000** 个块，超过需分批调用

**关键陷阱**：/blocks/convert 返回的 blocks 顺序是乱的，不可信。Markdown 转换 API 返回的 blocks 数组顺序与原始文档顺序不一致（随机乱序）。如果直接用返回顺序生成 children_id，文档内容会错乱。
**正确做法**：不要依赖转换 API 的返回顺序。改为手动按原始内容顺序逐块构建 blocks（block_type + 对应字段），直接指定 children_id 的顺序，确保与 Markdown 段落顺序一致。

### Markdown 全流程组合

```bash
# 1. 转换
BLOCKS_JSON=$(curl -s -X POST 'https://open.feishu.cn/open-apis/docx/v1/documents/blocks/convert' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "{\"content_type\":\"markdown\",\"content\":$(python3 -c "import sys,json; print(json.dumps(open('/tmp/content.md').read()))")}")

# 2. 去除表格的 merge_info，生成 payload
echo $BLOCKS_JSON | python3 - << 'PYEOF'
import sys, json

data = json.loads(sys.stdin.read())
blocks = data.get('data', {}).get('blocks', [])

# 去除 merge_info（Table 块 block_type=31 中的只读字段）
for block in blocks:
    if block.get('block_type') == 31:
        table = block.get('table', {})
        prop = table.get('property', {})
        prop.pop('merge_info', None)

children_id = [b['block_id'] for b in blocks if not any(
    b['block_id'] in other.get('children', []) for other in blocks)]

payload = {"index": -1, "children_id": children_id, "descendants": blocks}
with open('/tmp/blocks_payload.json', 'w') as f:
    json.dump(payload, f, ensure_ascii=False)
print(f"Generated {len(blocks)} blocks, {len(children_id)} top-level")
PYEOF

# 3. 插入
curl -s -X POST "https://open.feishu.cn/open-apis/docx/v1/documents/$DOC_ID/blocks/$DOC_ID/descendant?document_revision_id=-1" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d @/tmp/blocks_payload.json
```

---

## Step 4：插入图片

三步操作（创建 Block → 上传素材 → 绑定）：

```bash
IMAGE_PATH="/path/to/image.png"

# Step 1：创建空 Image Block（block_type=27），返回 Image Block ID
IMAGE_BLOCK_ID=$(curl -s -X POST "https://open.feishu.cn/open-apis/docx/v1/documents/$DOC_ID/blocks/$DOC_ID/children?document_revision_id=-1" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"index": -1, "children": [{"block_type": 27, "image": {}}]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['children'][0]['block_id'])")
echo "IMAGE_BLOCK_ID=$IMAGE_BLOCK_ID"

# Step 2：上传图片素材（parent_type=docx_image，parent_node=Image Block ID）
FILE_SIZE=$(wc -c < "$IMAGE_PATH" | tr -d ' ')
IMAGE_TOKEN=$(curl -s -X POST 'https://open.feishu.cn/open-apis/drive/v1/medias/upload_all' \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$IMAGE_PATH" \
  -F "file_name=$(basename $IMAGE_PATH)" \
  -F 'parent_type=docx_image' \
  -F "parent_node=$IMAGE_BLOCK_ID" \
  -F "size=$FILE_SIZE" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['file_token'])")
echo "IMAGE_TOKEN=$IMAGE_TOKEN"

# Step 3：将素材绑定到 Image Block（replace_image 操作）
curl -s -X PATCH "https://open.feishu.cn/open-apis/docx/v1/documents/$DOC_ID/blocks/$IMAGE_BLOCK_ID?document_revision_id=-1" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"replace_image\": {\"token\": \"$IMAGE_TOKEN\"}}"
```

### Markdown 转换后的图片处理

Markdown 转换生成的 Image Block 默认内容为空，需额外处理：

```bash
# 从转换结果找到 block_type=27 的块（Image Block）
# 下载图片到本地
curl -o /tmp/img.png "<markdown中的图片URL>"
# 然后用上方 Step 2-3 上传并绑定，IMAGE_BLOCK_ID 为转换结果中该图片块的 block_id
```

---

## Step 5：插入文件/附件

三步操作（创建 Block → 上传素材 → 绑定）：

```bash
FILE_PATH="/path/to/attachment.pdf"

# Step 1：创建空 File Block（block_type=23）
# 注意：API 返回的 children[0] 是 View Block，File Block ID 在 View Block 的 children[0] 中
RESPONSE=$(curl -s -X POST "https://open.feishu.cn/open-apis/docx/v1/documents/$DOC_ID/blocks/$DOC_ID/children?document_revision_id=-1" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"index": -1, "children": [{"block_type": 23, "file": {"token": ""}}]}')
FILE_BLOCK_ID=$(echo $RESPONSE | python3 -c "import sys,json; d=json.load(sys.stdin)['data']['children'][0]; print(d['children'][0])")
echo "FILE_BLOCK_ID=$FILE_BLOCK_ID"

# Step 2：上传文件素材（parent_type=docx_file，parent_node=File Block ID）
FILE_SIZE=$(wc -c < "$FILE_PATH" | tr -d ' ')
FILE_TOKEN=$(curl -s -X POST 'https://open.feishu.cn/open-apis/drive/v1/medias/upload_all' \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$FILE_PATH" \
  -F "file_name=$(basename $FILE_PATH)" \
  -F 'parent_type=docx_file' \
  -F "parent_node=$FILE_BLOCK_ID" \
  -F "size=$FILE_SIZE" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['file_token'])")
echo "FILE_TOKEN=$FILE_TOKEN"

# Step 3：将素材绑定到 File Block（replace_file 操作）
# URL 中 block_id 必须是 File Block ID（非 View Block ID）
curl -s -X PATCH "https://open.feishu.cn/open-apis/docx/v1/documents/$DOC_ID/blocks/$FILE_BLOCK_ID?document_revision_id=-1" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"replace_file\": {\"token\": \"$FILE_TOKEN\"}}"
```

---

## Step 6：权限管理

### 添加协作者

```bash
# perm: view（可阅读）| edit（可编辑）| full_access（可管理）
curl -s -X POST "https://open.feishu.cn/open-apis/drive/v1/permissions/$DOC_ID/members?type=docx" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{
    "member_type": "openid",
    "member_id": "<用户 open_id>",
    "perm": "edit",
    "type": "user"
  }'
```

- `member_type`：`openid`、`userid`、`email`
- `type=docx` 为查询参数，指定云文档类型

### 转移文档所有者

```bash
# remove_old_owner=false 保留原所有者权限；stay_put=false 移至新所有者空间
curl -s -X POST "https://open.feishu.cn/open-apis/drive/v1/permissions/$DOC_ID/members/transfer_owner?type=docx&remove_old_owner=false&stay_put=false" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{
    "member_type": "openid",
    "member_id": "<新所有者 open_id>"
  }'
```

- `old_owner_perm`（可选）：转移后原所有者保留的权限，仅 `remove_old_owner=false` 时生效，可选 `view`、`edit`、`full_access`

---

## Step 7：读取文档内容（转 Markdown）

```bash
curl -s -X GET "https://open.feishu.cn/open-apis/docs/v1/content?content_type=markdown&doc_token=$DOC_ID&doc_type=docx" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['content'])"
```

- `content_type`：`markdown`
- `doc_type`：`docx`（新版文档）
- 知识库中的文档需先调用 `/wiki/v2/spaces/get_node?obj_type=wiki&token=<wiki_token>` 获取 `obj_token` 作为 `doc_token`

---

## 注意事项

| 限制 | 说明 |
|------|------|
| 应用频率 | 单应用 3 次/秒，超限返回 HTTP 400 + 错误码 99991400 |
| 文档并发编辑 | 单文档 3 次/秒，超限返回 HTTP 429（创建/删除/更新块均计入） |
| 单次插入块数 | 最多 1000 块，超过需分批调用 |
| 表格块 | 插入前必须去除 `merge_info` 字段 |
| 图片块 | Markdown 转换后 Image Block 为空，需手动下载原图并上传绑定 |
| 文件块 | 创建后 API 返回 View Block，`children[0]` 才是 File Block ID |
| token 权限 | `tenant_access_token` 只能操作应用自己创建的文档/文件夹；操作用户文档需 `user_access_token` |
