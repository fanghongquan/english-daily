# 腾讯云函数部署指南（发音、词本与阅读反馈）

部署后：网页按需使用腾讯云自然发音、写入墨墨词本，并把阅读难度反馈保存到私有 COS。
**部署前不影响使用**——网页会自动用浏览器语音，反馈先存本地；档案读取失败时，每日生成
使用默认平衡档案。

> 全程在你自己的腾讯云账号操作；过程中可能要你**微信扫码（MFA）**验证，这步只能你本人做。
>
> **本项目当前升级遵守零新增预算：只更新已有 SCF 函数和已有 COS 存储桶。不要创建新函数、
> 新存储桶、资源包或付费网关；若控制台出现购买、升级或计费确认，立即停止。** 下面“一、二”
> 的创建步骤只供全新且愿意自行评估费用的部署参考，已有资源时必须跳过。

---

## 一、建一个 COS 存储桶（放遗忘库数据）

1. 进 [对象存储 COS 控制台](https://console.cloud.tencent.com/cos/bucket) → 创建存储桶
2. 名称：`english-daily`（创建后全名会变成 `english-daily-<你的APPID>`，例如 `english-daily-1300942703`）
3. 地域：**广州 ap-guangzhou**；访问权限：**私有读写**（数据只给云函数读写，无需公开）
4. 记下完整桶名（含 APPID），后面填 `COS_BUCKET`

## 二、创建云函数

1. 进 [云函数 SCF 控制台](https://console.cloud.tencent.com/scf) → 新建 → **从头开始**
2. 函数类型 **事件函数**；运行环境 **Python 3.9**；地域 **广州**；函数名随意（如 `english-tts`）
3. 提交方法选「**本地上传 zip 包**」，上传本项目里 `scf/` 打包的 zip（只含 `index.py`）；
   或选「在线编辑」，把 `scf/index.py` 全部内容粘进去。执行方法保持 `index.main_handler`
4. 展开**高级配置 → 环境变量**，添加：
   - `TENCENT_SECRET_ID` = 你的 SecretId
   - `TENCENT_SECRET_KEY` = 你的 SecretKey（保密那半）
   - `COS_BUCKET` = 第一步的完整桶名（如 `english-daily-1300942703`）
   - `COS_REGION` = `ap-guangzhou`
   - `TTS_VOICE` = `101051`
   - `APP_ACCESS_KEY` = 至少 32 字节的随机个人访问码，可用 `openssl rand -hex 32` 生成
   - `PROFILE_READ_TOKEN` = 另一份至少 32 字节的随机令牌，只供 GitHub Actions 读取学习档案
   - `ALLOW_ORIGIN` = `https://fanghongquan.github.io`（只写来源，不带路径和末尾 `/`）
   - `RATE_BURST` = `20`
   - `RATE_PER_MINUTE` = `30`
   （进阶可选：不填密钥，改给函数绑定一个有 **TTS + COS 读写** 权限的运行角色，更安全）
5. 完成创建（这步可能要扫码 MFA）

## 三、开启函数 URL并限制流量

1. 函数详情 → **函数 URL** → 创建/开启。URL 层可以公开，但应用代码会校验个人访问码的 HMAC 签名。
2. 复制生成的 URL（形如 `https://xxxx.ap-guangzhou.tencentscf.com/`）——这就是要填给网页的地址
3. 推荐在腾讯云 **API 网关**或函数 URL 配置中增加限流。代码里的限流只对单个函数实例有效，不能替代网关限流。

## 四、自测一下

设置 `TTS_API_URL` 后重新构建页面。首次点击云端朗读或“＋生词”时，网页会要求输入
`APP_ACCESS_KEY`，访问码只保存在当前浏览器的 `localStorage`。输入正确后能播放语音或写入墨墨即表示签名链路正常；访问码错误时服务器返回 401，网页会自动清除并要求重输。

## 五、把地址接到网页

1. GitHub 仓库 → Settings → Secrets and variables → Actions → **Variables** → 新建：
   `TTS_API_URL` = 你的函数 URL
2. 在 **Secrets** 新建 `PROFILE_READ_TOKEN`，值必须与 SCF 环境变量中的同名值完全一致。
3. Actions 里手动跑一次 `daily-english`（或等次日自动跑），网页就会带上这个地址：
   - 选中文字 → 腾讯云发音
   - 双击单词或点选短语 → 加入墨墨
   - 读完文章 → 三级难度反馈写入学习档案

> 零新增预算约束下，不为本功能开通任何新资源。现有 SCF/COS 如果不可用，页面保留本机
> pending 数据，生成任务退回默认难度，不自动购买、扩容或升级。

## 六、阅读反馈的私有数据

- `learning-profile/events/YYYY-MM-DD.json`：单篇合并后的三级反馈和客观计数。
- `learning-profile/profile.json`：派生后的能力分、下一篇目标和最近趋势。
- 网页只上传完成状态、首次答题得分、单词操作数和短语操作数；**不上传具体单词或短语**，
  也不上传文章正文。
- `profile_get` 只返回生成任务需要的派生参数，不返回最近事件明细。
- COS 必须保持私有，函数运行角色只需对现有桶具备对象读写权限。

## 七、安全维护、轮换与恢复

- `ALLOW_ORIGIN` 必须是精确的 GitHub Pages 来源，不要配置成 `*`。
- 怀疑访问码泄露时，在 SCF 中生成新的 `APP_ACCESS_KEY`；这就是访问码轮换。所有设备下次调用时会收到 401，然后输入新访问码。
- `PROFILE_READ_TOKEN` 与手机访问码相互独立。轮换时先同时更新 SCF 和 GitHub Secret，
  再手动跑一次工作流；不要把它配置成 GitHub Variable。
- 不要把 `APP_ACCESS_KEY`、腾讯云密钥或墨墨 Token 写进仓库、模板或 GitHub Variables。
- 网关建议按个人用量配置每分钟请求上限，并开启异常流量告警。
- 云函数返回 502 时查看 SCF 日志；浏览器只收到通用错误，不会看到上游密钥或详细响应。
- 若升级后异常，回滚到上一版 `scf/index.py`，保留 COS 中两个 `learning-profile/` 对象即可；
  每日生成会继续使用默认平衡档案，不影响原有文章发布。
