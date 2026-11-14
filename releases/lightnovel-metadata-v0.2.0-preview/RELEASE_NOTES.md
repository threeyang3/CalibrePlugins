# LightNovel Metadata v0.2.0 Preview

发布日期：2026-11-14。**预览版：供独立 Calibre 测试书库试装。** 本分发包不代表真实书站及 Calibre GUI 已完成验收。

## 文件

- `LightNovelMetadata.zip`：在 Calibre“首选项 → 插件 → 从文件加载插件”中直接安装，不要解压。
- `LightNovelMetadata.zip.sha256`：校验安装包是否完整。
- 源码与测试位于主分支 `plugins/lightnovel-metadata/`。

SHA-256: `d13134b3f1d3d1be1e5727738401af517977d30121fc134e2373258624a0f72c`

## 更新摘要

- Bangumi、博客来、台湾角川、尖端、日本 openBD、日本国立国会图书馆（NDL）与台湾国家图书馆 CSV 离线书目。
- 系列／分卷／具体出版 ISBN 的身份隔离和字段优先级；同 ISBN 出现卷次、语言矛盾时不自动融合。
- 台湾国家图书馆“预订出版日”不当作正式出版日；不下载正文、不自动改写 EPUB、不读取用户个人阅读数据。

## 验收

- 46 项离线测试通过，重建 ZIP 与本安装包字节级一致。
- 尚未完成真实 Calibre GUI 和实时出版网站联网验收。

PR: https://github.com/threeyang3/CalibrePlugins/pull/2

主分支合并提交：359eaf7b35fda6b8378e7149c1567d353f85f686

**这是不使用 GitHub Actions/CI 的独立分发分支，不是 GitHub Releases 正式 Release 记录。**
