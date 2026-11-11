# 来源与实现说明

本目录是用户项目 `threeyang3/CalibrePlugins` 中的独立 Calibre 插件，按本目录的 MIT 许可证提供。该许可证不自动覆盖仓库中的其他插件。

## 参考项目

- [threeyang3/webnovel-import](https://github.com/threeyang3/webnovel-import)，参考基线 `d8d016449acaf3de180b92af1437bee83453d4ce`：沿用用户已有项目的三站作品身份、字段含义、页面选择器、首发日期证据和封面排除规则，改写为 Python。没有打包 Obsidian、Electron、JavaScript 构建产物或其依赖。
- [fugary/calibre-douban / NewDouban](https://github.com/fugary/calibre-douban)，上游 Apache-2.0：参考元数据源插件的使用方式和 `Source` 接口组织；本插件的网络层、搜索调度和平台适配器独立实现，没有复制或分发 NewDouban 的源码。
- [Calibre 官方插件 API](https://manual.calibre-ebook.com/plugins.html#module-calibre.ebooks.metadata.sources.base)及[插件结构文档](https://manual.calibre-ebook.com/creating_plugins.html#anatomy-of-a-calibre-plugin)：遵循 `Source`、`Option`、`Metadata` 与 ZIP 插件命名空间协议。

## 平台数据

元数据从用户查询所对应的起点、七猫、番茄公开作品页取得。作品信息和封面权利归原权利人。测试目录使用虚构文本制作结构样本，未在仓库中收录完整网页、作品正文、账号数据或平台 Cookie。
