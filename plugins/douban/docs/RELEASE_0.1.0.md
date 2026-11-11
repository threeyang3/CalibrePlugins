# Douban 插件 v0.1.0（预览版）

这是 `CalibrePlugins` 多插件仓库中豆瓣插件的首次发布，基于 [fugary/calibre-douban](https://github.com/fugary/calibre-douban) 的 Apache-2.0 开源代码扩展。**尚未完成真实 Calibre GUI 和个人豆瓣账号验收，不建议直接用于唯一的正式书库。**

## 安装文件

- **DoubanReadingRecords.zip**：配套的个人阅读记录插件，可登录自己的豆瓣账户并读取已关联书籍的个人标签、1–5 星评分、想读／在读／读过状态和简评；先预览再写入到四个独立的 Calibre 自定义列。
- **NewDouban.zip**：原公共元数据下载插件，下载书名、作者、封面、简介等公共信息；如果已安装兼容版本可不重复安装。

两个 ZIP 都是 Calibre 可直接从文件安装的插件，**无需解压**；不要把整个源码目录当作插件安装。

## 数据安全

初次同步仅填空白字段；后续仅更新仍等于本插件上次写入值的字段。用户手改、清空、账号变化或条目版本变化不自动覆盖。读取失败或无法确认个人记录时，不拿公共评分／热门短评补位。不会向豆瓣回写，也不会后台同步。

## 验证状态

- 50 项离线单元测试通过（合成网页／模拟数据库）。
- Python 编译检查通过。
- 本地打包可复现：`DoubanReadingRecords.zip` SHA-256 `39e28c1935da860130771ee8d21cb543c5797c46a53d43ba2fa739d059cbd447`，`NewDouban.zip` SHA-256 `bcdb264bef6ea0c0331dafe31b96ec83bde8a4423b4d767c46ee3f2d3c8d351d`。
- **未验证：**真实账号登录与页面结构、Calibre 界面和真实数据库、Qt WebEngine、书库切换等 GUI 交互。

请先在测试书库中用两三本书试用。安装方法和验收清单参见 [`docs/INSTALL.zh-CN.md`](https://github.com/threeyang3/CalibrePlugins/blob/main/plugins/douban/docs/INSTALL.zh-CN.md)。

## 来源与许可

原作者 Gary Fu：[`fugary/calibre-douban`](https://github.com/fugary/calibre-douban)；保留 Apache-2.0 的 `LICENSE`、`NOTICE` 和来源说明。此发布并非豆瓣或原作者的官方发行。
