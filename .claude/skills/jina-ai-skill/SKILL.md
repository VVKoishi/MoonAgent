---
name: jina-ai-skill
description: Web reading and searching via Jina AI APIs. Fetch clean markdown from any URL (r.jina.ai), perform web search (s.jina.ai), or run deep multi-step research (DeepSearch). Use when the user needs to read a URL as markdown, search the web, or do complex multi-source research. Requires JINA_API_KEY environment variable.
---

# Jina AI — Reader, Search & DeepSearch

Web reading and search powered by Jina AI. Requires `JINA_API_KEY` environment variable.

> **Trust & Privacy:** By using this skill, URLs and queries are transmitted to Jina AI (jina.ai). Only use if you trust Jina with your data.

**Get your API key:** https://jina.ai/ → Dashboard → API Keys

---

## External Endpoints

This skill makes HTTP requests to the following external endpoints only:

| Endpoint | URL Pattern | Purpose |
|----------|-------------|---------|
| **Reader API** | `https://r.jina.ai/{url}` | Converts URL content to clean markdown |
| **Search API** | `https://s.jina.ai/{query}` | Web search with LLM-friendly results |
| **DeepSearch API** | `https://deepsearch.jina.ai/v1/chat/completions` | Multi-step research agent |

No other external network calls are made by this skill.

---

## Security & Privacy

- **Authentication:** Only your `JINA_API_KEY` is transmitted to Jina's servers (via `Authorization` header)
- **Data sent:** URLs and search queries you provide are sent to Jina's servers for processing
- **Local files:** No local files are read or transmitted by this skill
- **Local storage:** No data is stored locally beyond stdout output
- **Environment access:** Only the `JINA_API_KEY` environment variable is accessed; no other env vars are read
- **Cookies:** Cookies are not forwarded by default; the `X-Set-Cookie` header is available for authenticated content but is opt-in only

---

## Endpoints

| Endpoint | Base URL | Purpose |
|----------|----------|---------|
| **Reader** | `https://r.jina.ai/{url}` | Convert any URL → clean markdown |
| **Search** | `https://s.jina.ai/{query}` | Web search with LLM-friendly results |
| **DeepSearch** | `https://deepsearch.jina.ai/v1/chat/completions` | Multi-step research agent |

All endpoints accept `Authorization: Bearer $JINA_API_KEY`.

---

## Reader API (`r.jina.ai`)

Fetches any URL and returns clean, LLM-friendly content. Works with web pages, PDFs, and JS-heavy sites.

### Basic Usage

```bash
# Plain text output
curl -s "https://r.jina.ai/https://example.com" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Accept: text/plain"

# JSON output (includes url, title, content, timestamp)
curl -s "https://r.jina.ai/https://example.com" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Accept: application/json"
```

### Parameters (via headers or query params)

#### Content Control

| Header | Query Param | Values | Default | Description |
|--------|-------------|--------|---------|-------------|
| `X-Respond-With` | `respondWith` | `content`, `markdown`, `html`, `text`, `screenshot`, `pageshot`, `vlm`, `readerlm-v2` | `content` | Output format |
| `X-Retain-Images` | `retainImages` | `none`, `all`, `alt`, `all_p`, `alt_p` | `all` | Image handling |
| `X-Retain-Links` | `retainLinks` | `none`, `all`, `text`, `gpt-oss` | `all` | Link handling |
| `X-With-Generated-Alt` | `withGeneratedAlt` | `true`/`false` | `false` | Auto-caption images |
| `X-With-Links-Summary` | `withLinksSummary` | `true` | - | Append links section |
| `X-With-Images-Summary` | `withImagesSummary` | `true`/`false` | `false` | Append images section |
| `X-Token-Budget` | `tokenBudget` | number | - | Max tokens for response |

#### CSS Selectors

| Header | Query Param | Description |
|--------|-------------|-------------|
| `X-Target-Selector` | `targetSelector` | Only extract matching elements |
| `X-Wait-For-Selector` | `waitForSelector` | Wait for elements before extracting |
| `X-Remove-Selector` | `removeSelector` | Remove elements before extraction |

#### Browser & Network

| Header | Query Param | Description |
|--------|-------------|-------------|
| `X-Timeout` | `timeout` | Page load timeout (1-180s) |
| `X-Respond-Timing` | `respondTiming` | When page is "ready" (`html`, `network-idle`, etc.) |
| `X-No-Cache` | `noCache` | Bypass cached content |
| `X-Proxy` | `proxy` | Country code or `auto` for proxy |
| `X-Set-Cookie` | `setCookies` | Forward cookies for authenticated content |

### Common Patterns

```bash
# Extract main content, remove navigation elements
curl -s "https://r.jina.ai/https://example.com/article" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "X-Retain-Images: none" \
  -H "X-Remove-Selector: nav, footer, .sidebar, .ads" \
  -H "Accept: text/plain"

# Extract specific section
curl -s "https://r.jina.ai/https://example.com" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "X-Target-Selector: article.main-content"

# Parse a PDF
curl -s "https://r.jina.ai/https://example.com/paper.pdf" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Accept: text/plain"

# Wait for dynamic content
curl -s "https://r.jina.ai/https://spa-app.com" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "X-Wait-For-Selector: .loaded-content" \
  -H "X-Respond-Timing: network-idle"
```

---

## Search API (`s.jina.ai`)

Web search returning LLM-friendly results with full page content.

### Basic Usage

```bash
# Plain text
curl -s "https://s.jina.ai/your+search+query" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Accept: text/plain"

# JSON
curl -s "https://s.jina.ai/your+search+query" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Accept: application/json"
```

### Search Parameters

| Param | Values | Description |
|-------|--------|-------------|
| `site` | domain | Limit to specific site |
| `type` | `web`, `images`, `news` | Search type |
| `num` / `count` | 0-20 | Number of results |
| `gl` | country code | Geo-location (e.g. `us`, `in`) |
| `filetype` | extension | Filter by file type |
| `intitle` | string | Must appear in title |

All Reader parameters also work on search results.

### Common Patterns

```bash
# Site-scoped search
curl -s "https://s.jina.ai/OpenAI+GPT-5?site=reddit.com" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Accept: text/plain"

# News search
curl -s "https://s.jina.ai/latest+AI+news?type=news&num=5" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Accept: application/json"

# Search for PDFs
curl -s "https://s.jina.ai/machine+learning+survey?filetype=pdf&num=5" \
  -H "Authorization: Bearer $JINA_API_KEY"
```

---

## DeepSearch

Multi-step research agent that combines search + reading + reasoning. OpenAI-compatible chat completions API.

```bash
curl -s "https://deepsearch.jina.ai/v1/chat/completions" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jina-deepsearch-v1",
    "messages": [{"role": "user", "content": "Your research question here"}],
    "stream": false
  }'
```

Use for complex research requiring multiple sources and reasoning chains.

---

## Rate Limits

- **Free (no key):** 20 RPM
- **With API key:** Higher limits, token-based pricing

## API Docs

- Reader: https://jina.ai/reader
- Search: https://s.jina.ai/docs
- OpenAPI specs: https://r.jina.ai/openapi.json | https://s.jina.ai/openapi.json
