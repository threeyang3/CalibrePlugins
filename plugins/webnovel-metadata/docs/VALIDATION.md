# WebNovel Metadata 0.1.0 验证记录

日期：2026-11-11。此记录针对本目录 `0.1.0` 预览版，区分离线回归、真实 Calibre 集成与实际官网请求。测试不打开或修改用户书库，不写回电子书。

## 结果

| 验证层次 | 环境与方法 | 结果 |
| --- | --- | --- |
| 离线回归 | Python 3.12 + lxml，`unittest discover` | **58 项全部通过** |
| 真实 Calibre 集成 | 官方 Linux Calibre 6.29.0 / Python 3.10.1；安装构建 ZIP；隔离配置；fixture HTTP | **29 项断言全部通过** |
| 已安装 ZIP 联网链路 | 真实 Calibre Source → 官方搜索 / 详情 → 官方图片下载 | 起点、七猫的书名搜索与三站详情 / 封面成功 |
| 更多真实页面结构 | 独立保存公开页面后，使用同一 Python 解析器核对；无章节正文请求 | 七猫 3 部、番茄 2 部、起点 1 部详情，以及 2 种搜索结构通过 |
| 打包 | Python 3.8 语法检查、ZIP 根结构和 CRC；固定归档时间 | 通过；只包含运行时模块、LICENSE、NOTICE.md |

## 最终安装包的联网结果

全部经已安装的插件执行，未用 fixture 或本地 HTML 代替网络。每个平台只核对 1 个搜索候选，避免额外请求。

| 来源与入口 | 取得的作品 / 作者 | 作品 ID | 出版日期 | 实际封面 |
| --- | --- | --- | --- | --- |
| 起点：书名 + 作者搜索 | 《诡秘之主》 / 爱潜水的乌贼 | `1010868264` | `2018-04-01`，来自本书 `Book.datePublished` | JPEG，600 × 800，211,988 bytes |
| 七猫：书名 + 作者搜索 | 《盖世神医》 / 狐颜乱语 | `195958` | 留空，页面无明确首发证据 | JPEG，360 × 480，28,950 bytes |
| 番茄：作品 ID | 《十日终焉》 / 杀虫队队员 | `7143038691944959011` | 留空，更新信息未冒充首发时间 | JPEG，225 × 300，13,786 bytes |

官网详情：

- [起点《诡秘之主》](https://m.qidian.com/book/1010868264/)
- [七猫《盖世神医》](https://www.qimao.com/shuku/195958/)
- [番茄《十日终焉》](https://fanqienovel.com/page/7143038691944959011)

额外详情结构样本为七猫《玉奴娇》（`1672986`）、《江海潜寻》（`1734099`），番茄《永夜君主》（`6857085053504064524`）。完整网页只作为临时研究材料，不收录进仓库。离线 fixtures 是按观察结构编写的虚构文本，不能作为联网成功的证据。

## 搜索与访问限制

### 起点

- 桌面作品页、桌面搜索在本轮环境返回 HTTP 202 的短验证页面。
- 正常移动站 `https://m.qidian.com/so/{keyword}.html` 返回 HTTP 200；从 `script#vite-plugin-ssr_pageContext` 的 `pageContext.pageProps.pageData.bookInfo.records` 提取 `bid`。
- 《诡秘之主》《斗破苍穹》搜索均获得 20 条候选，分别以 `1010868264`、`1209977` 为首条。
- 详情使用桌面 URL，遇到非可用响应时允许正常移动作品页回退；没有执行验证脚本或模拟解验证码。
- 合法页面也含验证码相关脚本字符串，因此不以出现 `captcha` 单词作为受限判据。

### 七猫

- HTML 搜索页依赖脚本，不能只抓页面链接。
- 正常官网搜索接口：`https://www.qimao.com/qimaoapi/api/search/result?keyword=...&page=1&page_size=15`。
- 本轮匿名 HTTP 200；只读 `data.search_list`，不将 `do_you_like_list` 推荐内容当成搜索命中。
- 详情身份由本作品头部信息中的最新章节链接等核对。该字段只用于定位作品，没有访问章节正文。

### 番茄

- 正常详情页匿名 HTTP 200，可以取得作品信息和绑定本书 ID 的封面。
- 官网搜索接口 `/api/author/search/search_book/v1` 在本轮环境返回 **HTTP 200、正文 0 字节**；HTML 搜索页也只提供加载状态。
- 已实现当前官网接口结构，但**不能宣称番茄书名搜索已联网成功**。该平台目前优先使用作品 ID 或正式详情页 URL。
- 封面采用本书 JSON-LD 中的签名 URL，保留 `x-expires` / `x-signature` 等查询参数。签名过期时允许重新识别同一作品以刷新 URL。
- 页面更新时间、JSON-LD `upDate` 和 `lastPublishTime` 不作为出版日期。

## 关键回归范围

- 三站 URL / ID 往返、长 ID、同平台相互矛盾的标识符、相似域名、非法协议与端口。
- 详情与输入身份不符时拒绝；明确 ID 失败后不改搜另一本同名作品。
- 同名不同作者拒绝；字段缺失、验证页、作者简介、推荐区图片与占位图不混入本书元数据。
- 作品首发日期与更新日期分离；标签、来源附注和连载状态可选；不产生个人评分。
- 不执行网页脚本，简介以纯文本转义生成 HTML。
- 网络总预算、单次超时、取消、来源开关、候选上限、响应大小与解压大小限制。
- 每次重定向重新核对地址与预算；损坏 gzip、无效编码、空响应和单站异常隔离。
- 后续请求超时或受限时保留已取得结果；用户取消时不继续发布结果。
- 本地 HTML 文件身份校验，同名文件读取失败不偷偷用网络替换。
- 跨平台相同数字 ID 的封面缓存隔离；最佳封面请求经 Calibre 自己的 Worker 传递；图片经真实 Calibre 解码。

## 复现

在插件目录运行：

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 build.py
```

在已安装 Calibre 的机器上，使用独立配置目录：

```bash
export CALIBRE_CONFIG_DIRECTORY="$(mktemp -d)"
export QT_QPA_PLATFORM=offscreen
calibre-customize -a dist/WebNovelMetadata.zip
calibre-debug -e tests/calibre_smoke.py
```

上一步不请求官网。需要主动进行少量实时验证时再运行：

```bash
calibre-debug -e tests/live_smoke.py -- --run-live
```

安装包 SHA-256 在构建时写入同目录的 `WebNovelMetadata.zip.sha256`。当前完整安装包为 **22,520 bytes**，SHA-256：

```text
807d2084a1f867853b4d50e25ac071ff8ec079e7de45cdc305f8710a9ba683e2
```

## 尚未验收

- 用户 macOS / Windows 机器上的实际界面操作、个人书库中多源合并后的选项体验。
- Calibre 5.0 最低版本的真实运行；目前已检查 Python 3.8 语法并核对相关 API，但真正执行的是 Calibre 6.29.0。
- 番茄匿名书名搜索在其他网络下的可用性。
- 高并发、大规模批量查询或长期运行；首版通过候选数、请求预算与三个临时线程限制开销。

总时间预算在请求、跳转、读取之间检查；进行中的阻塞 I/O 仍可能等待到单次超时，因此不是严格实时取消。没有新增 GitHub Actions 工作流，也没有声称完成 GitHub CI、GitHub Release 或用户本机验收。
