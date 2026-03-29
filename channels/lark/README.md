# 飞书渠道

通过飞书自建应用，[三分钟快速接入](https://open.feishu.cn/document/develop-an-echo-bot/introduction)。

## 配置

在 `.env` 中填写以下变量：

```env
ENABLE_LARK=true           # 必填，启用飞书渠道
LARK_APP_ID=cli_xxx        # 应用 ID，飞书开放平台 → 凭证与基础信息
LARK_APP_SECRET=xxx        # 应用密钥，同上
LARK_OPEN_ID=ou_xxx        # （可选）Bot 自身的 open_id，用于识别群聊中的 @提及
```

## 创建应用

### 1. 新建自建应用

前往 [飞书开放平台](https://open.feishu.cn/) 创建自建应用。

### 2. 开启权限

**应用能力**
- 机器人

**应用身份权限**

- `im:message.p2p_msg:readonly` — 读取用户发给机器人的单聊消息
- `im:message:send_as_bot` — 以应用的身份发消息
- `im:message.group_at_msg:readonly` — 接收群聊中 @机器人 消息事件

**事件订阅**
- 订阅类型：长连接
- 应用身份事件：`im.message.receive_v1`（接收消息）

### 3. 发布与部署

发布应用，并将 Bot 添加到目标群，或与目标用户建立单聊。

### 4. 填写配置

将应用 ID 和密钥填入 `.env`，重启 Agent 即可。
