# CalibrePlugins

面向 [Calibre](https://calibre-ebook.com/) 的电子书管理插件集合。本仓库采用 **一插件项目一个目录** 的方式维护源代码、测试和说明；仓库根目录只放公共文档、通用设置与发布工作流，不把多个插件的源码混在根目录。

## 插件列表

| 项目 | 作用 | 当前版本 | 下载 / 文档 |
| --- | --- | --- | --- |
| **Douban · 豆瓣书籍资料与个人阅读记录** | 原有豆瓣公共元数据下载 + 可选的个人标签、评分、阅读状态、简评导入 | `v0.1.0` 预览版 | [版本发布](https://github.com/threeyang3/CalibrePlugins/releases/tag/douban-v0.1.0) · [使用说明](plugins/douban/README.md) |

## 目录规范

```text
CalibrePlugins/
├── README.md                     # 插件总览与下载入口
├── plugins/
│   ├── README.md                 # 多插件目录与版本约定
│   └── douban/                   # 豆瓣插件独立项目
│       ├── README.md
│       ├── src/                   # 公共元数据插件源码
│       ├── personal/              # 个人阅读记录插件源码
│       ├── tests/                 # 离线测试
│       ├── docs/                  # 安装、验证和发行说明
│       ├── build.py
│       ├── LICENSE
│       └── NOTICE
└── .github/workflows/            # 发布工作流（按插件区分）
```

后续新插件放在 `plugins/<plugin-id>/`，拥有独立 README、源码、测试、构建流程和许可证。各插件单独编号、单独发布（例如 `douban-v0.1.0`），不以整个仓库的版本号替代插件版本。发行包只包含安装所需文件，避免把其他插件、测试、个人凭证或开发资料打包进去。

## 安装

进入相应插件的 Release，下载对应的 **Calibre 插件 `.zip` 文件**（不需要解压），在 Calibre 的“首选项 → 插件 → 从文件加载插件”中安装。不同插件的安装要求请阅读各自说明。

豆瓣插件包含两个单独安装的 ZIP：`NewDouban.zip`（公共元数据）与 `DoubanReadingRecords.zip`（个人阅读记录）。后者目前是**待真实账号验收的预览版**，建议先使用测试书库。

## 开发与许可

参见 [`plugins/README.md`](plugins/README.md)；每个插件按其子目录中的许可文件处理。豆瓣项目保留 [fugary/calibre-douban](https://github.com/fugary/calibre-douban) 的原作者署名和 Apache-2.0 许可。
