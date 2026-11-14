# 验证记录 · LightNovel Metadata v0.2.0（2026-11-14）

## 已验证（离线）

- `python -W error -m unittest discover -s tests -p 'test_*.py' -q`：本地 46 项通过。
- ISBN-10/13 checksum、数字与半卷卷次、日版/台版 ISBN 隔离，以及同 ISBN 来源 ID / 卷次 / 语言冲突拒绝融合。
- Bangumi 小说文本/数字子分类、非小说排除、关联条目过滤，以及只有关联另一**实际系列条目**时才赋予系列身份。
- 台湾角川的规范商品 URL + 正文 ISBN 双重身份核验，尖端的商品 ID + 商品特色 ISBN 校验；脚本和推荐商品不参与本书身份判定。
- NCL 官方 CSV 列名、UTF-8 和 CP950 解析、无效 ISBN 过滤、只读 SQLite ISBN/书名查询、损坏路径拒绝、预订出版日与正式出版日期分离。
- 分字段来源优先、缺失字段回退、来源溯源，模拟 Calibre 元数据候选及封面缓存、网络重定向/响应大小边界。
- Python 3.8 语法兼容 AST、可重复安装 ZIP 和 SHA-256 校验。

## 在线事实与代码兼容性（不是实时运行通过）

- Bangumi 公共 v0 API 官方文档存在 `/v0/search/subjects`、`/v0/subjects/{id}` 和 `/v0/subjects/{id}/subjects`。
- 台湾角川官网存在 `products/{ISBN}` 书目页面，已核对展示作者、上市日、ISBN；尖端官网存在 `SalePage/Index/{商品ID}` 且展示条码 ISBN、绘者/译者。
- 台湾国家图书馆「臺灣出版新書預告書訊」开放 CSV，主要字段是 `申請書名`、`出版機構`、`預訂出版日`、`ISBN` 等；非实时单书 API。
- openBD 可按 ISBN 调用兼容接口，但上游供数方式/封面覆盖率已变化，不能保证每个 ISBN 有图。

## 尚未验证（不得宣称已经可用）

- 本运行环境无法直接联网访问上述网站，因此无法完成**真实请求**、Cookie/验证拦截、页面 HTML 改版、封面 CDN 重定向或速率限制的验收。现有解析器测试的 HTML/JSON/XML 是**人工结构样本**，不代表本日抓取的真实网页。
- 运行环境未安装完整 Calibre，因此只有模拟接口测试，尚未通过 `calibre-customize -a`、`calibre-debug` 和 Calibre GUI 真机验证。
- 台湾出版社无保证稳定的开放 API，HTML 适配器属于**实验性**：URL、正文布局或反爬限制变化会导致正确拒绝结果。
- NCL CSV 实际发布文件的全部历史编码、列名变化与增量策略尚未通过完整官方归档测试。
- Calibre 5+ 不同操作系统/最新版本没有逐一真实安装；本阶段不创建正式稳定 Release。

## 建议在隔离 Calibre 配置中验证

```bash
cd plugins/lightnovel-metadata
python3 build.py
export CALIBRE_CONFIG_DIRECTORY="$(mktemp -d)"
calibre-customize -a dist/LightNovelMetadata.zip
# 随后在 Calibre 图形界面使用“下载元数据”：
# 1. 台版台湾角川 ISBN 9786264354356
# 2. 尖端官网 /SalePage/Index/10055328
# 3. Bangumi 实际标注为小说、包含系列关系的单卷 Subject ID
# 4. 日文 ISBN 的 NDL + openBD，并人工核对真正版次/封面
# 5. NCL 官方 CSV 离线索引（查询/重复导入/不存在的书）
```

记录每项来源的 HTTP 状态、页面结构、结果 ISBN、封面 URL 可信域名及 Calibre 字段效果；任何失败不得用同名作品的另一 ISBN 静默替换。PR #2 已于 2026-11-14 合并到 main；v0.2.0 预览 ZIP 已发布在独立分发分支（不是 GitHub Releases 记录）。真实验证通过后再考虑正式稳定版 Release。

本仓库不为该插件添加自动 CI，避免消耗 GitHub Actions 额度。测试、打包和实机验收优先本地执行。
