# Calibre Douban：书籍资料与个人阅读记录

**多插件仓库目录：** `plugins/douban/`。本项目包含两个可分别安装的 ZIP 插件，请前往 [Douban v0.1.0 发布页](https://github.com/threeyang3/CalibrePlugins/releases/tag/douban-v0.1.0) 下载。当前为预览版，真实登录与 GUI 尚待验收。

在 Calibre 管理电子书时，保留豆瓣书籍资料，同时把自己在豆瓣记录的**标签、评分、阅读状态和简评**放进书库。

本开发版本基于 [fugary/calibre-douban](https://github.com/fugary/calibre-douban) 的 `deea4743d177e8439103bece4cf8faa4ab4e0f4a`。保留 Gary Fu 的原元数据插件，新增可单独安装的 **Douban Reading Records / 豆瓣阅读记录** 配套插件。

> **0.1.0 测试版 · 2026-11-10。** 已完成代码、离线测试及 ZIP 构建；尚未在真实 Calibre 中完成安装、豆瓣登录与真实账号四字段验收。先用测试书库和少量已收藏书籍验收。具体范围见 [验证记录](docs/VERIFICATION.md)。

## 两个插件各做什么

| 插件 | 入口 | 内容 |
| --- | --- | --- |
| **New Douban Books**，原插件 | Calibre 的“下载元数据” | 书名、作者、出版社、ISBN、封面、简介、公共标签、公众评分等 |
| **Douban Reading Records**，本次新增 | 工具栏“豆瓣阅读记录” | 登录自己的豆瓣账号，读取选中书籍的个人标签、个人评分、想读／在读／读过、个人简评 |

原插件已有手动填写 Cookie 的配置项，但它不会自动让解析结果变成个人评分或简评。个人记录需要核对账号、定位书库记录、预览变化并保护本地修改，所以新增独立入口。Calibre 元数据下载流程会合并不同来源的结果，不宜承担这些个人数据的写入规则。

**已经安装原插件的话，只需增加 `DoubanReadingRecords.zip`。** 配套插件也能处理手动填写的 `douban:1234567` 标识符，不强制依赖原插件。

## 四项数据在哪里

| 豆瓣个人信息 | Calibre 列名 | 查找名 | 类型 |
| --- | --- | --- | --- |
| 我给书打的标签 | 豆瓣个人标签 | `#douban_my_tags` | 可包含多个值的文本列 |
| 我的 1–5 星评分 | 豆瓣个人评分 | `#douban_my_rating` | 评分列，界面仍为 1–5 星 |
| 想读／在读／读过 | 豆瓣阅读状态 | `#douban_read_status` | 单值文本列 |
| 我的短评文字 | 豆瓣简评 | `#douban_my_comment` | 长文本／评论列 |

个人简评与书籍简介分开，个人标签与原有分类标签分开。这些是 Calibre 自定义列，能够搜索、编辑和导出；卸载插件不会删除已写入列内的记录。

## 开始使用

完整步骤见 [安装与使用](docs/INSTALL.zh-CN.md)。

1. “首选项 → 插件 → 从文件加载插件”，选择 **`DoubanReadingRecords.zip`**，添加工具栏入口并重启。ZIP 无需解压。
2. 打开“豆瓣阅读记录”，点击“创建所需的四个列”，确认名称与类型，然后按提示再重启一次。
3. 在书库选中少量已在豆瓣收藏、具有正确 `new_douban` 或 `douban` ID 的书。可以先用原插件下载元数据完成关联。
4. 打开配套插件，点击“登录 / 切换豆瓣账号”，在豆瓣网页内自行登录；点击“完成登录”，等待显示核对后的账号。
5. 点击“读取选中书籍”，检查当前值、豆瓣值与处理原因，再点击“写入勾选项”。

内嵌浏览器不可用时有手动 Cookie 入口。Cookie 只在自己的电脑上填写，不需要发给任何人。当前登录状态只在本次 Calibre 进程内保留，退出软件后需要重新登录；没有跨重启持久登录。

## 更新时如何保护人工整理

- **第一次导入：**只填写空白列；已有内容保留，即使它恰好等于豆瓣值也不自动认领。
- **后续导入：**只有当前值仍等于上次插件实际写入的值，才允许更新。
- **本地修改或手动清空：**均视为你的决定，后续导入会跳过。
- **豆瓣为空、未收藏或字段未识别：**保留本地内容，本版本不传播来源删除。
- **换账号、改豆瓣版本 ID：**历史关联不同就跳过，不混入其他账号或版本的数据。
- **登录过期、读取失败或安全验证：**停止读取，不应用未完成批次。
- **预览后修改字段、删除书籍或切换书库：**写入前复核，不使用过时预览覆盖新内容。

四个字段分别写入。数据库错误可能发生在部分字段已经完成之后，界面会报告已写入数量并停止后续操作。本版本没有整批事务回滚。

## 当前范围

实现的是**豆瓣 → Calibre 的手动触发导入**，支持多选书籍。不会向豆瓣提交记录，也不在后台定时扫描。登录浏览器仅在打开时创建；请求由后台线程串行执行，默认请求间隔至少 1.5 秒。

仅按已确认的豆瓣条目 ID 读取。没有 ID 的书会跳过，不用书名猜测，不自动合并译本或再版。支持 `new_douban` 和 `douban`，两者同时存在且冲突时需要先修正。

页面布局和登录风控会变化，目前仍需真实账号验证。无法读取时不会用公众评分、公共标签或热门短评替代个人记录。这里的“简评”不含长书评、划线批注、页码进度或阅读时长。

## 本地构建

从仓库根目录先执行 `cd plugins/douban`。

```bash
python -m unittest discover -s tests -v
python -m compileall -q personal src build.py
python build.py
```

离线测试需要 Python 3.9+ 和 `lxml`。在 Calibre 中使用其自带依赖；插件声明最低 Calibre 6（Qt 6），尚未做真实版本矩阵验证。

输出 `out/NewDouban.zip` 和 `out/DoubanReadingRecords.zip`。`src/` 原插件源代码保持原样。构建只加入插件源文件与许可，不加入缓存、凭证或调试输出。**整个源码压缩包不能直接当作插件安装。**

## 维护结构

| 路径 | 职责 |
| --- | --- |
| `src/__init__.py` | 上游原公共元数据插件 |
| `personal/core.py` | 账号、条目、个人字段解析 |
| `personal/client.py` | 只读 HTTP、Cookie 作用域、限速、取消 |
| `personal/login.py` | Qt 网页登录及手动 Cookie 入口 |
| `personal/sync.py` | 字段映射、变化规划、人工修改保护 |
| `personal/storage.py` | Calibre 数据库适配、写入复核与来源快照 |
| `personal/action.py` | 创建列、后台读取、预览、导入界面 |
| `tests/` | 合成页面、模拟网络与模拟数据库测试 |

后续优先完成真实登录与页面验收，再考虑持久登录、显式解决冲突、已有列映射和豆瓣书单匹配。Media Core 可以以后读取这些独立列，但本版本尚未实现自动连接。

## 来源与许可

原项目作者 Gary Fu：[fugary/calibre-douban](https://github.com/fugary/calibre-douban)，[原说明](https://fugary.com/?p=423)，[原版发行包](https://github.com/fugary/calibre-douban/releases/latest/download/NewDouban.zip)。

保留 Apache-2.0 许可证与署名，见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。新增实现不是原作者的正式发行版，也不属于豆瓣官方产品。接口依据见 [验证记录](docs/VERIFICATION.md)。
