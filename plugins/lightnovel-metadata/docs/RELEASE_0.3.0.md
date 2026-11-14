## 本版改动

- 新增「轻小说书目」工具栏操作，按 ISBN 补齐选中书籍的公开资料。已填写的书库数据、封面和 EPUB 文件会保留。只有缺封面的书才会补图。
- 新增「译者（书目）」「插画师（书目）」「作品原名」「出版日期（原文）」四个书目列，以及供手填的「EPUB 制作者」。下载时会跳过书库里重复的 ISBN 和有明确卷次或版别冲突的记录。
- 新增日本 KADOKAWA 数据源。以出版方商品页的 ISBN 确认版本，获取书名、作者、插画师、出版日期和官方封面。

## 安装

| 附件 | 用途 | 最低 Calibre 版本 |
| --- | --- | --- |
| `LightNovelMetadata.zip` | 下载普通元数据及封面 | 5.0 |
| `LightNovelLibrary.zip` | 创建书目栏目，按 ISBN 补齐数据。需要同时安装元数据源 | 8.0 |

在 Calibre **首选项 → 插件 → 从文件加载插件** 分别安装两个 ZIP，然后重启。需要使用书库操作时，在目标书库选择 **轻小说书目 → 建立轻小说书目栏目**，按提示重启。选中已有 ISBN 的书，点击工具栏上的 **轻小说书目** 即可补齐。本 Release 附有两个包的 SHA-256 校验文件。[完整使用说明](https://github.com/threeyang3/CalibrePlugins/blob/lightnovel-metadata-v0.3.0/plugins/lightnovel-metadata/README.md)

## 验证范围

在 macOS 上使用 Calibre 9.16 通过 51 项离线测试、4 项书库操作测试及隔离书库集成测试。按 ISBN `9784041026229` 实测从日本 KADOKAWA 下载《你的名字。》书目和 705 × 1000 的官方封面，并在图形界面补齐空白简介和条目标识。写入前后核对了原封面、EPUB 文件与既有自定义列。其他数据源的在线覆盖范围仍在验证中。[验证记录](https://github.com/threeyang3/CalibrePlugins/blob/lightnovel-metadata-v0.3.0/plugins/lightnovel-metadata/docs/VALIDATION.md)
