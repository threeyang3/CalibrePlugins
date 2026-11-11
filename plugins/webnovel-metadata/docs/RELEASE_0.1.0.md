# WebNovel Metadata v0.1.0（预览版）

首次发布 Calibre 网文元数据插件，源码在 `plugins/webnovel-metadata/`，参考作者已有的 `webnovel-import` 与 NewDouban 的 Calibre 元数据源方式。

## 下载与安装

下载附件 **`WebNovelMetadata.zip`**（Calibre 可直接安装，**不要解压**）。在 Calibre 中打开“首选项 → 插件 → 从文件加载插件”，选中 ZIP，完成安装并重启 Calibre；然后在“首选项 → 元数据下载”中启用 **WebNovel Metadata**。另附 `WebNovelMetadata.zip.sha256` 供校验。

最低声明 Calibre 5.0 / Python 3.8；此前已在真实 **Calibre 6.29.0** 环境中验证安装和元数据接口。建议先用测试书库试用。

## 主要功能

- **起点中文网、七猫中文网、番茄小说**三个独立来源，取得书名、作者、简介、封面、题材标签和作品 ID。
- 支持**书名 + 作者搜索**或通过 `qidian:ID`、`qimao:ID`、`fanqie:ID` 及正式作品详情页链接精确匹配；明确 ID 失败不偷偷改用同名书。
- 提取明确的作品首发日期；**不把更新时间当成出版日期**。字数、连载状态、最新章节和更新时间可选地附在简介末尾。
- 保存作品来源和 Calibre 可点击的官方链接；封面不误用作者头像、推荐作品或已知占位图。
- 各平台可分别启停，设置候选数量、超时、封面数量和简介附注；允许读取浏览器已保存的 HTML 详情页。
- 不下载正文、不要求账号登录，也不自动覆盖独立的个人阅读记录。手工修改元数据请继续使用 Calibre 原生编辑界面。

## 本版验证情况

- **58 项离线测试通过**，及此前真实 Calibre 6.29.0 下的 **29 项集成断言通过**。
- 此前已在安装后的 Calibre 插件中实际取得：起点《诡秘之主》、七猫《盖世神医》（书名搜索），以及番茄《十日终焉》（作品 ID）的元数据与官方封面。
- 发布工作流会重新运行离线测试并校验 ZIP 的 SHA-256；本次工作流**不重新进行官网联机测试或 Calibre GUI 验收**。

**已知限制：**番茄的匿名**书名搜索在本轮网络环境下返回空响应，尚未验证成功**；建议使用番茄作品 ID 或正式详情 URL。起点桌面网页在本轮环境可能显示访问验证，插件可回退移动站。macOS / Windows 图形界面仍待用户本机验收，故此版本标为 **Pre-release**。

完整的 [使用说明](https://github.com/threeyang3/CalibrePlugins/blob/main/plugins/webnovel-metadata/README.md) 和 [验证记录](https://github.com/threeyang3/CalibrePlugins/blob/main/plugins/webnovel-metadata/docs/VALIDATION.md)。

## 校验与来源

`WebNovelMetadata.zip` 预期大小 **22,520 bytes**，SHA-256：

```text
807d2084a1f867853b4d50e25ac071ff8ec079e7de45cdc305f8710a9ba683e2
```

发布过程将实际构建并校验此哈希值，校验失败不会发布附件。许可证及参考来源见插件目录的 `LICENSE` / `NOTICE.md`。
