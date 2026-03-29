<p align="center">
  <img src="icon.png" alt="MoonAgent" width="200">
</p>


<p align="center">
  基于 Claude Code 的私人 AI 助理，轻量、安全、易于理解，专为深度定制而设计。
</p>
<p align="center">
  <!-- 更新 token-count：pip install tiktoken -q && python -c 'import glob,tiktoken as t;e=t.get_encoding("cl100k_base");f=[x for p in"*.py channels/**/*.py".split()for x in glob.glob(p,recursive=True)if __import__("os").path.isfile(x)];n=sum(len(e.encode(open(x,errors="ignore").read()))for x in f);print(f"{n/1000:.1f}K, {round(n/1e6*100,1)}% of 1M")' -->
  <img src="https://img.shields.io/badge/7.8K_tokens-0.8%25_of_1M_context-brightgreen" alt="7.8K tokens, 0.8% of 1M context window" valign="middle">
  <img alt="GitHub License" src="https://img.shields.io/github/license/vvkoishi/moonagent" valign="middle">
  <a href="https://pypi.org/project/moon-agent/"><img alt="PyPI - Version" src="https://img.shields.io/pypi/v/moon-agent" valign="middle"></a>
</p>


---

## 设计哲学

- **极致轻量。** 小到可以自迭代——Agent 能读懂整个代码库，你可以直接指示它开发新 Skill、接入新渠道、生成新灵魂。
- **安全隔离。** 运行在 Docker 容器内，Agent 不仅具有完整权限处理任务，还能确保宿主机环境安全。
- **Skills 即产品。** 浏览器、定时任务、文档协作、外部服务……这些能力以独立 Skill 存在，可按需增删，不进入代码库。Agent 本体只管运行时与渠道接入，保持极简。

## 快速开始

**依赖：**

- [Python 3.14+](https://www.python.org/downloads/) — 运行时
- [Docker](https://www.docker.com/) — 安全沙箱（可选）

**安装：**

```bash
git clone git@lf.git.oa.mt:zijianli/MoonAgent.git
cd MoonAgent
pip install -e .
```

**配置：**

```
cp .env.example .env
# 编辑 .env，填写 ANTHROPIC_API_KEY
```

**启动：**

```
moon
```

启动后即可在命令行与 MoonAgent 对话。试着问问她：`帮我把 MoonAgent 接入飞书渠道`

**部署:（可选，生产环境）**

```
docker compose up -d
```

**更新:（可选，如需追踪最新特性）**

```
git pull
# 然后重新运行 moon
```

## 风险提示

> [!WARNING] 
>
> 请勿在 `.env`、对话或任何提示词中填写数据库密码、SSH 私钥等高权限凭据——Agent 具备代码执行能力，填写即意味着授权。

## Q&A

> [!TIP]
>
> **如何选择 OpenClaw，NanoClaw 和 MoonAgent ？**
>
> MoonAgent 核心代码 token 数仅 7.8K，远低于 NanoClaw 的 40.7K 和 OpenClaw 的 3.5M，且具备完全相同的能力。对于 1M 上下文的模型，仅占用 0.8% ，可以放心交给 AI 自迭代。
>
> **为什么是 ClaudeCode ？**
>
> 因为 ClaudeCode 是目前最优雅、最成熟的代理工具。MoonAgent 完全基于 ClaudeCode，可以从 Anthropic 的每次技术进步中受益。

