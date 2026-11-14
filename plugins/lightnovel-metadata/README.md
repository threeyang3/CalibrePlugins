# LightNovel Metadata · Calibre 轻小说元数据

面向本地 EPUB/电子书书库的 **Calibre 元数据来源插件**，聚合 Bangumi、台版书店与出版社、台湾国家图书馆开放书目，以及日本 openBD、国立国会图书馆（NDL）资料。关注轻小说的**作品、系列、单卷、日文版、繁体中文版**的准确识别。

**v0.3.0 预览版**增加了「轻小说书目」工具栏操作，可按 ISBN 补齐公开书目资料，同时保留已有的书库数据与 EPUB 文件。

## 下载预览版

- [LightNovelMetadata.zip](https://github.com/threeyang3/CalibrePlugins/releases/download/lightnovel-metadata-v0.3.0/LightNovelMetadata.zip)
- [LightNovelLibrary.zip](https://github.com/threeyang3/CalibrePlugins/releases/download/lightnovel-metadata-v0.3.0/LightNovelLibrary.zip)
- [发布说明与 SHA-256 校验文件](https://github.com/threeyang3/CalibrePlugins/releases/tag/lightnovel-metadata-v0.3.0)

## 数据源与查询能力

| 来源 | 触发条件 | 提供的主要字段 | 验证边界 |
| --- | --- | --- | --- |
| [Bangumi v0](https://bangumi.github.io/api/) | 书名 / Subject ID / 条目 URL | 中日书名、作者、插画师、标签、简介、卷册、关系 | 只接受明确标注为**小说**的条目；按系列关系复核主系列，不以同名推断 |
| [博客来](https://www.books.com.tw/) | 书名、ISBN、商品 ID/URL | 繁体版书名、ISBN、译者、出版社、封面 | 要求商品身份与 ISBN 均可核验；HTML 解析尚待在线验证 |
| [台灣角川](https://www.kadokawa.com.tw/) | **精确台湾 ISBN** 或 `products/ISBN` URL | 正式商品页书名、作者、插画师、封面、上市日期 | 官方商品页规范 URL **及正文 ISBN 必须一致**；不猜测套装 SKU |
| [尖端出版](https://www.spp.com.tw/) | **精确商品 ID 或 SalePage/Index URL** | 商品条码 ISBN、作者、绘者、译者、封面、上市日期 | 依商品编号和商品特色栏核验；不使用未确认的搜索接口 |
| [台湾国家图书馆开放书目](https://data.gov.tw/dataset/6730) | **用户预先导入的本地 SQLite 索引**，ISBN/书名 | ISBN、申请书名、作者、出版机构、预订出版日 | 离线查询；预订日期**不会当作正式出版日期** |
| [openBD](https://openbd.jp/) | 日本 ISBN | 日文书名、作者、出版社、日期、部分封面 | 只有 ISBN 查询；覆盖率尤其是封面取决于上游数据 |
| [日本 NDL Search](https://ndlsearch.ndl.go.jp/help/api) | 日文书名或 ISBN | 日文书名、出版单位、作者、ISBN、日期 | 仅使用公开书目；可能返回多个候选版本 |
| [日本 KADOKAWA](https://www.kadokawa.co.jp/) | 日本 ISBN 或官网商品 ID | 书名、封面、作者、插画师、上市日期 | 只采用商品页上与查询一致的纸本 ISBN |

网站页面适配器可能因访问限制/改版而失效。不尝试登录、绕过验证码、抓取正文或下载付费内容。联网请求有站点白名单、最大响应体积、超时及取消检查。

## 安装与验证

在 `plugins/lightnovel-metadata` 目录运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 build.py
```

构建生成 `dist/LightNovelMetadata.zip`（普通元数据源）和 `dist/LightNovelLibrary.zip`（书库操作）。在 Calibre **首选项 → 插件 → 从文件加载插件** 分别安装两个 ZIP，重启后在「元数据下载」中启用 `LightNovel Metadata`。元数据源需要 Calibre 5.0 或更新版本，书库操作需要 Calibre 8.0 或更新版本。

## 补齐书库里的轻小说资料

在目标书库选择 **轻小说书目 → 建立轻小说书目栏目**，并按提示重启。选中一本或多本已有 ISBN 的书，点击工具栏上的「轻小说书目」补齐公开资料。如果按钮未显示，可在 **首选项 → 工具栏与菜单 → 主工具栏** 添加。已有的书名、作者、简介、语言、丛书、出版方、出版日期和其他自定义字段均保留。公开书目的译者和插画师分别存入「译者（书目）」和「插画师（书目）」，已有填写值优先。作品原名与部分日期也有独立栏目。

「EPUB 制作者」供手填，书目下载不会写入这列。Calibre 封面只在书库缺图时补齐。原始 EPUB 文件也会保留，包括内部元数据、封面和制作者署名。

书库内 ISBN 重复、命中多个互相冲突的候选、上下卷或明确版本标记冲突时，书库操作会跳过该条目。需要手动选择候选和字段时，可继续使用 Calibre 自带的「编辑元数据 → 下载元数据」。

## 查询方式

可在 Calibre 书籍「标识符」中填写有效 ISBN 和/或明确的来源 ID，例如：

```text
isbn:9786264354356
kadokawa_tw:9786264354356
spp_tw:10055328
books_tw:0011234567
bangumi:123456
```

也可在**书名输入框**填写官方精确商品 URL（仅支持对应适配器的规范 URL）：

```text
https://www.kadokawa.com.tw/products/9786264354356
https://www.spp.com.tw/SalePage/Index/10055328
https://www.books.com.tw/products/0011234567
https://bgm.tv/subject/123456
```

示例 ID 用于说明格式，输入前请核对是否是对应作品；`books_tw` 和 `bangumi` 的数字纯属演示。显式提供来源 ID 后**只查该条目**，查不到时不会退回同名搜索。只有 ISBN 时仍可尝试其他已启用来源，但只采用匹配该 ISBN 的结果。

## 按字段控制来源

在「元数据下载 → 配置 LightNovel Metadata」里可填写各字段首选来源。十个来源优先项包括：**书名、作者、出版社、日期、封面、简介、系列、标签、插画师、译者**。默认值均为 `auto`。

可填入下列来源代号之一：`bangumi`、`books_tw`、`kadokawa_tw`、`spp_tw`、`ncl_tw`、`openbd`、`ndl`、`kadokawa_jp`，或 `auto`。例如：

- `pref_title = books_tw`：同一 ISBN 下优先使用博客来的繁体书名。
- `pref_cover = kadokawa_tw`：同一 ISBN 下优先使用台湾角川的封面。
- `pref_description = bangumi`：同一 ISBN 下优先使用 Bangumi 的简介。

**优先级仅作用于 checksum 正确、完全相同 ISBN 的记录**。首选来源缺失该字段时退回其他匹配来源，不会因此借用日版/台版的另一 ISBN。对于同一 ISBN 存在不同来源 ID、冲突卷次或语言的情况，拒绝合并并保留独立候选。`tags`、插画师及译者在 `auto` 下去重合并，明确指定来源则不跨来源拼接。

在元数据源设置里，可选择让普通下载的简介显示书目字段和来源。默认下载简介正文。书库操作会将公开译者等信息写入对应的书目列。

## Bangumi 系列与分卷

默认开启「Bangumi 系列关联」，读取该卷的公开 `GET /v0/subjects/{id}/subjects` 关系。只在相关条目确实是**书籍系列总条目**并能验证该关联时，记录主系列 Subject ID 并把已知卷号映射到 Calibre `series` / `series_index`。如果不能确认卷号，则只保留来源线索，不凭空设置第几卷。适配器不会把动画改编、漫画或同名其他版本误当成小说系列。

支持书名中明显的 `第 3 卷`、`（第3册）`、`(7.5)`、`Vol. 2` 等数字卷标。未提供 ISBN 的 Bangumi 作品级系列条目默认**不导入为图书候选**，可在设置中开启。

## 台湾国家图书馆 CSV → SQLite（离线可选）

官方「臺灣出版新書預告書訊」是**按期更新的出版前申请书目**，不是实时单书接口。可以从 [政府资料开放平台](https://data.gov.tw/dataset/6730) 下载所需月份 CSV 后运行：

```bash
python3 tools/import_ncl.py --output "$HOME/Books/ncl-lightnovels.sqlite" /path/to/2026-10.csv
# 此命令仅读取本地 CSV，不访问互联网或 Calibre 图书数据库
```

然后在插件设置 `ncl_index_path` 中填入该 SQLite 文件绝对路径。导入器自动识别台湾国家图书馆的主要字段名，包括 `ISBN`、`申請書名`、`作者`、`出版機構`、`預訂出版日`，兼容 UTF-8 BOM 与 Big5/CP950；过滤无效 ISBN；同 ISBN 以最近导入的行保留。要整体更新旧索引，用 `--replace` 原子替换。**不要直接下载全量 CSV 到插件运行时，或把预订出版日当作正式出版日**。

未配置路径时，不会触发台湾国家图书馆数据网络调用；没有本地索引也不影响其他来源。

## 自动匹配与数据保护原则

1. 作品、系列、单卷、语言版本、精装/平装等可能是不同层级；ISBN 校验一致是自动跨源合并的必要条件。
2. 书名相近及同一系列的记录仅能作为搜索候选，不能借用不同 ISBN 的出版社、日期及封面。
3. 不把 Bangumi 评分映射为 Calibre **个人评分**；不获取个人收藏、阅读进度和短评，也不自动创建或覆盖其他项目中的笔记。
4. 对资料缺失或尚未确认的日期/卷次保持空值，不凭印刷地点、出版年月或站点更新时间推测。
5. 默认只提供**候选元数据**；是否写入 Calibre、是否将已修改的元数据保存进 EPUB 仍由用户通过 Calibre 决定。

## 开发、维护与发布

独立源模块位于 `src/providers/`，融合与安全边界在 `src/models.py`、`src/engine.py`、`src/network.py`，本地 NCL 导入器在 `tools/import_ncl.py`。不依赖 Bangumi-sync、MangaTag 或 WebNovel Metadata 的运行环境，但遵循它们的身份隔离、适配器拆分和增量测试理念。

详见 [验证记录](docs/VALIDATION.md)、[上游数据接口说明](docs/SOURCES.md) 和 [集成提示](docs/INTEGRATION.md)。**无常驻任务，不新增 CI 工作流**；先完成真实 Calibre 客户端和目标网站的手动验收，再考虑正式稳定版 GitHub Release。许可证见 [LICENSE](LICENSE)，来源使用条件见 [NOTICE.md](NOTICE.md)。
