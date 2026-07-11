# 每日英语四级阅读 · 飞书推送

每天通过飞书机器人推一篇约 1000 词的 CET-4 阅读文章。点开链接进入网页：
段段对照中文翻译，**重点词加粗并标注美式音标**，**选中任意单词或句子点一下就能听美式发音**，整段 / 全文也能朗读。

发音用浏览器内置的 **Web Speech API** 实时合成，免费、不依赖任何第三方 API、不需要预先生成音频文件。

---

## 它长什么样

- 标题 + 中文标题 + 导读
- 顶部工具条：显示/隐藏中文翻译、显示/隐藏音标、朗读全文、停止、语速调节
- 每段英文下方紧跟中文翻译，可单独「中/英」切换、「朗读本段」
- 正文里的重点词蓝色加粗，后面跟着小号美式音标，点词即可发音
- 选中任意文字 → 浮出「🔊 朗读选中」按钮 → 听美式发音
- 底部「重点词汇表」，点任一行发音

先打开 `site/2026-06-13.html` 看效果（用 Safari / Chrome）。

---

## 目录结构

```
english-daily/
├─ template.html          网页模板（交互+发音逻辑都在这里）
├─ articles/
│   └─ 2026-06-13.json     一天一篇的文章数据（schema 见此文件）
├─ site/                   构建产物：每天一个 HTML + index.html
├─ get_article.py          生成当日文章 JSON（AI 生成 / 抓取）
├─ build.py                把 JSON 渲染成网页
├─ push_feishu.py          向飞书 webhook 推交互卡片
├─ daily.py                一键：生成→构建→推送
└─ .github/workflows/daily.yml   GitHub Actions 每天定时跑
```

---

## 部署建议：GitHub Pages + GitHub Actions（推荐，免费、免服务器）

你之前问「跑在哪里」——最省事的方案是**完全不用买服务器**：
用 GitHub Pages 托管网页，用 GitHub Actions 当定时器。每天自动生成文章、构建网页、
推送飞书卡片，零成本。

**步骤：**

1. 新建一个 GitHub 仓库（比如 `english-daily`），把本目录所有文件传上去。
2. 仓库 Settings → Pages → Source 选 `Deploy from a branch`，分支选 `main`、目录选 `/site`。
   保存后你会得到一个地址：`https://<你的用户名>.github.io/english-daily/`
3. 仓库 Settings → Secrets and variables → Actions 里配置：
   - **Secrets**（机密）：`FEISHU_WEBHOOK`、`FEISHU_SECRET`（开了加签才填）、
     以及内容生成用的 `ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY`
   - **Variables**（变量）：`SITE_BASE_URL` = 上一步的 Pages 地址（去掉结尾斜杠）；
     用 OpenAI 兼容服务时再填 `OPENAI_BASE_URL`、`OPENAI_MODEL`
4. `.github/workflows/daily.yml` 已设好每天**北京时间 06:30**触发。想改时间改里面的 cron。
   先在 Actions 页面点 `Run workflow` 手动跑一次，验证能收到飞书卡片。

> 备选方案：如果你有一台常开的电脑 / 云服务器 / 云函数，也可以直接 `crontab` 调
> `python daily.py`。GitHub Actions 的好处是不用自己维护机器。

---

## 飞书配置

本项目用的是**群自定义机器人 webhook**：
飞书群 → 设置 → 群机器人 → 添加「自定义机器人」→ 复制 webhook 地址。
如果你勾选了「签名校验」，把那串密钥配成 `FEISHU_SECRET`。
卡片里的「开始阅读」按钮会直接跳转到当天的网页。

### 自动任务的可靠性

每日任务先生成并校验文章、提交到 GitHub Pages，确认当天页面可以访问后才推送飞书。
飞书明确返回成功后，任务才会在 `state/YYYY-MM-DD.json` 记录完成。备用定时任务依据
`state/` 去重，而不是依据 HTML 是否存在。

如果飞书推送失败，Actions 会显示红色，且不会写成功状态；后续备用时段会继续重试。
如果 AI 生成失败，任务同样会失败并等待下一次重试，不再静默推送旧文章。修复配置后也可在
Actions 页面手动执行工作流恢复。

---

## 自然发音（可选 · 腾讯云 TTS）

不配也能用——网页默认用浏览器内置语音实时合成（在工具条「嗓音」里挑带 ⭐ 的增强版能改善音质）。
想要更接近真人的发音，配上腾讯云 TTS，构建时会为**整篇 / 每段 / 每个重点词**预生成自然 mp3，
网页优先播放这些音频；**选中任意文字仍用浏览器实时合成**（任意文本无法预生成）。

**准备：**

1. 注册腾讯云并完成个人实名认证 → 控制台搜「语音合成」开通 → **领取免费资源包**
   （基础/精品 800 万字符，3 个月有效；大模型音色另送 10 万）。
2. 右上角头像 → 访问管理 CAM → API 密钥管理 → 新建密钥，得到 `SecretId` + `SecretKey`。
3. 安装 SDK：`pip install tencentcloud-sdk-python`
4. **配密钥（最简单的方式，不用碰环境变量）**：
   把项目里的 `secret.env.example` 复制一份、改名为 `secret.env`，
   用文本编辑器打开，把 `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY` 换成你的两串，保存。
   脚本会自动读取它（`secret.env` 已在 `.gitignore` 里，不会上传）。
5. 运行：

```bash
python gen_audio.py articles/2026-06-13.json # 单独生成音频
python build.py articles/2026-06-13.json     # 重新构建网页
# 或一步到位（daily.py 会自动读 secret.env 并调 gen_audio）
python daily.py --source ai
```

> 也可以用传统环境变量 `export TENCENT_SECRET_ID=...`，两种方式二选一即可。

**换音色**：改 `TTS_VOICE`。英文精品 `101050`(男 WeJack)/`101051`(女 WeRose) 走 800 万免费额度；
想最自然可换「大模型音色」(走 10 万免费额度)。完整列表见腾讯云「语音合成 - 音色列表」文档。

> 部署到 GitHub Actions 时，把 `TENCENT_SECRET_ID`/`TENCENT_SECRET_KEY` 配成 Secrets、
> `TTS_VOICE` 配成 Variable 即可，workflow 已接好。生成的 mp3 会随 `site/` 一起提交。

当前按需云端能力采用个人访问码保护。SCF 中配置 `APP_ACCESS_KEY` 和精确的
`ALLOW_ORIGIN`；网页首次使用云端发音或墨墨时输入访问码。公开访客不输入访问码仍可阅读、
答题并使用浏览器内置语音。完整部署、API 网关限流和访问码轮换方法见 `SCF_DEPLOY.md`。

---

## 内容来源（你选了「抓取真题/外刊」，请先看这里）

`get_article.py` 提供两种来源：

- `--source ai`（**默认，推荐**）：用大模型按四级难度现写一篇，配好翻译、重点词、音标，
  内容版权归你，零风险。配 `ANTHROPIC_API_KEY` 或任意 OpenAI 兼容 key（DeepSeek、
  通义、Kimi 等都行）即可。
- `--source scrape`：抓取外刊/真题。**⚠️ 版权提醒**：四级真题、The Economist、
  China Daily 等多受版权保护，整篇抓取后转发推送可能侵权。合规做法二选一：
  1. 只抓**公共领域 / 知识共享**来源（VOA Learning English、维基百科节选、古登堡计划等）；
  2. 把抓来的文章当**素材**喂给大模型，让它改写+简化到四级难度后再用，并附原文出处。

  `gen_scrape()` 目前是占位实现，按上面思路自行接入即可。

> 我的建议：日常推送用 `--source ai` 最稳，质量可控、无版权顾虑；
> 想练真题时再单独抓取做合规处理。

---

## 本地快速试跑

```bash
# 只构建网页、不推送（用现成的示例文章）
python build.py articles/2026-06-13.json
open site/2026-06-13.html      # macOS；其他系统用浏览器打开

# 用 AI 生成今天的文章（需先 export ANTHROPIC_API_KEY 或 OPENAI_API_KEY）
python get_article.py --source ai
python build.py

# 一键生成+构建+推飞书（需 export SITE_BASE_URL / FEISHU_WEBHOOK ...）
python daily.py --source ai
python daily.py --no-push       # 调试时只生成不推送
```

---

## 想自定义

- **换话题 / 难度**：改 `get_article.py` 里的 `PROMPT`。
- **改样式 / 加功能**：改 `template.html`（CSS 在 `<style>`，逻辑在底部 `<script>`）。
- **发音音色**：`template.html` 的 `pickVoice()` 里调整偏好的 en-US 嗓音。
  手机上的发音音色取决于系统自带语音库。
- **加生词本 / 打卡**：网页里可以用 `localStorage` 存用户点过的词（模板已是纯前端，便于扩展）。
