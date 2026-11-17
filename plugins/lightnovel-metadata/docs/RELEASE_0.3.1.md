新增三民书局作为台版 ISBN 的备用来源。当首选来源缺少匹配书目、封面链接或译者时，插件会查询三民，并核对商品页上的 ISBN。也可以使用三民商品页 URL 或 `sanmin_tw` 标识符查询。

使用「轻小说书目」时，公开译者只会补入空白的「译者（书目）」列。已填写的书库资料、原封面和 EPUB 文件会保留。

| 安装包 | 插件版本 | 最低 Calibre 版本 |
| --- | --- | --- |
| `LightNovelMetadata.zip` | v0.3.1 | 5.0 |
| `LightNovelLibrary.zip` | v0.3.0 | 8.0 |

在 Calibre **首选项 → 插件 → 从文件加载插件** 安装 ZIP，然后重启。已有书库操作插件 v0.3.0 的用户可直接更新元数据源。两个安装包均附 SHA-256 校验文件。[使用说明](https://github.com/threeyang3/CalibrePlugins/blob/lightnovel-metadata-v0.3.1/plugins/lightnovel-metadata/README.md)

在 Calibre 9.16 上通过 58 项离线测试、4 项书库操作测试和隔离书库集成测试。用《敗北女角太多了！1》（ISBN `9789572696583`）实测下载到東立版书目、译者陳士晉和 284 × 407 的 JPEG 封面，并在书库操作中核对了空白译者栏和原封面。[三民商品页](https://www.sanmin.com.tw/product/index/011499432) · [验证记录](https://github.com/threeyang3/CalibrePlugins/blob/lightnovel-metadata-v0.3.1/plugins/lightnovel-metadata/docs/VALIDATION.md)
