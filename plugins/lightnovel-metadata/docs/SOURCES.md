# 数据来源、接口与维护边界

本项目只读取公开作品和出版书目，**不读取第三方账号个人数据**、不抓正文、不绕过验证，也不将第三方封面打包分发。

| 来源 | 公开入口 | 身份条件与维护策略 |
| --- | --- | --- |
| Bangumi v0 | https://bangumi.github.io/api/ | Subject ID 是公共作品/卷次条目身份，关系需再核对系列条目；小说子分类应兼容数字 `1002` 和文字 `小说` 等，不能误收漫画 |
| 台湾博客来 | https://www.books.com.tw/ | 商品 `001...` ID + 自身 ISBN；书名搜索会依 HTML 结构退化 |
| 台灣角川 | https://www.kadokawa.com.tw/ | `products/{ISBN}` + 页面声明 ISBN；不对 SKU、预购套组作推测 |
| 尖端 | https://www.spp.com.tw/ | `SalePage/Index/{商品ID}` + 商品特色条码 ISBN；不猜测网站搜索接口 |
| 台湾国家图书馆 | https://data.gov.tw/dataset/6730 | **官方下载 CSV**，本地 `tools/import_ncl.py` 生成离线索引；书目属于出版前申请，预订日期不是确认出版日期 |
| openBD | https://openbd.jp/ | `/v1/get?isbn=`；上游数据来源及封面覆盖率有过变化，请严格做字段空值回退、遵守使用条款 |
| NDL Search | https://ndlsearch.ndl.go.jp/help/api | `api/opensearch` 的 ISBN/题名检索；可能检出同书多版，按 ISBN 决定版次身份 |

安全边界：元数据与封面请求均在固定 HTTPS 域名白名单、请求预算和响应体积限制之内；仅相同 ISBN 候选进入跨源融合。能确认出版版次的独立站点 ID 写入 Calibre 标识符，冲突时保留独立记录供人工核对。

更新平台解析器时，应首先保存**不包含个人信息的真实 HTML/JSON 小样本**作为离线回归，再做定量限流的单站点联调。来源页变更和网站访问限制被视作可预期错误，不应被伪装成“无结果”。
