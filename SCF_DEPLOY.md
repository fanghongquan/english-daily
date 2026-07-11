# 腾讯云函数部署指南（发音 + 多设备同步）

部署后：网页选中文字用腾讯云自然发音；遗忘库经云函数读写 COS，实现手机/电脑同步。
**部署前不影响使用**——网页会自动用浏览器语音、同步先存本地；部署完填好地址即点亮。

> 全程在你自己的腾讯云账号操作；过程中可能要你**微信扫码（MFA）**验证，这步只能你本人做。

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
2. Actions 里手动跑一次 `daily-english`（或等次日自动跑），网页就会带上这个地址：
   - 选中文字 → 腾讯云发音
   - 背单词模块右下角「开启同步」→ 设个同步码，手机和电脑填同一个即可互通

> 费用：个人用量很小，前 3 个月基本 0；之后约每月几毛到几元。

## 六、安全维护与轮换

- `ALLOW_ORIGIN` 必须是精确的 GitHub Pages 来源，不要配置成 `*`。
- 怀疑访问码泄露时，在 SCF 中生成新的 `APP_ACCESS_KEY`；这就是访问码轮换。所有设备下次调用时会收到 401，然后输入新访问码。
- 不要把 `APP_ACCESS_KEY`、腾讯云密钥或墨墨 Token 写进仓库、模板或 GitHub Variables。
- 网关建议按个人用量配置每分钟请求上限，并开启异常流量告警。
- 云函数返回 502 时查看 SCF 日志；浏览器只收到通用错误，不会看到上游密钥或详细响应。
