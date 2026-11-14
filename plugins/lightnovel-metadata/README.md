# LightNovel Metadata · Calibre 轻小说元数据

面向本地 EPUB/电子书书库的 **Calibre 元数据来源插件**，聚合 Bangumi、台版书店与出版社、台湾国家图书馆开放书目，以及日本 openBD、国立国会图书馆（NDL）资料。关注轻小说的**作品、系列、单卷、日文版、繁体中文版**的准确识别。

> **v0.2.0 预览版**：46 项离线单元/模拟适配测试通过；尚未完成真实 Calibre 安装及网站实时数据验收。请先在测试书库试用，不要批量替换已有书目。此版不自动读写 EPUB 内部封面或元数据，也不读取个人评分、笔记、收藏和阅读状态。

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

网站页面适配器可能因访问限制/改版而失效。不尝试登录、绕过验证码、抓取正文或下载付费内容。联网请求有站点白名单、最大响应体积、超时及取消检查。

## 安装与验证

在 `plugins/lightnovel-metadata` 目录运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 build.py
```

运行时依赖 Calibre 自带 Python 及 `lxml`；构建脚本仅用标准库。将生成的 `dist/LightNovelMetadata.zip` **不解压**，在 Calibre「首选项 → 插件 → 从文件加载插件」中安装，重启后在「元数据下载」里启用 `LightNovel Metadata`。最低目标版本为 Calibre 5.0，macOS/Windows/Linux 实机验收仍待完成。

**先用测试书库和已知 ISBN 实测**：核对书名、版次、封面及来源，再决定使用哪些字段；特别注意 Calibre 的「简介」字段可能已经包含你的私人笔记，必要时在 Calibre 元数据下载设置中禁用该字段。

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

可填入下列来源代号之一：`bangumi`、`books_tw`、`kadokawa_tw`、`spp_tw`、`ncl_tw`、`openbd`、`ndl`，或 `auto`。例如：

- `pref_title = books_tw`：同一 ISBN 下优先使用博客来的繁体书名。
- `pref_cover = kadokawa_tw`：同一 ISBN 下优先使用台湾角川的封面。
- `pref_description = bangumi`：同一 ISBN 下优先使用 Bangumi 的简介。

**优先级仅作用于 checksum 正确、完全相同 ISBN 的记录**。首选来源缺失该字段时退回其他匹配来源，不会因此借用日版/台版的另一 ISBN。对于同一 ISBN 存在不同来源 ID、冲突卷次或语言的情况，拒绝合并并保留独立候选。`tags`、插画师及译者在 `auto` 下去重合并，明确指定来源则不跨来源拼接。

融合结果的「简介」附注可以看到每个关键字段来自哪个网站，便于核对。当前使用 Calibre 原生来源选项（文本设置），没有另建一套复杂表单。

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

详见 [验证记录](docs/VALIDATION.md)、[上游数据接口说明](docs/SOURCES.md) 和 [集成提示](docs/INTEGRATION.md)。**无常驻任务，不新增 CI 工作流**；先完成真实 Calibre 客户端和目标网站的手动验收，再考虑正式 Release。许可证见 [LICENSE](LICENSE)，来源使用条件见 [NOTICE.md](NOTICE.md)。
