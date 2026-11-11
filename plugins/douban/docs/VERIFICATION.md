# 验证记录与实现依据

日期：2026-11-10。上游基线：`fugary/calibre-douban@deea4743d177e8439103bece4cf8faa4ab4e0f4a`。配套插件：0.1.0 测试版。

## 已完成

| 检查 | 结果 | 实际边界 |
| --- | --- | --- |
| 账号、条目、个人字段解析与 HTTP | 23 项 unittest 通过 | 合成 HTML、模拟 HTTP，不是真实登录页面 |
| 逐字段同步规划 | 14 项 unittest 通过 | 独立 Python 逻辑，含人工修改／清空、来源为空与身份变化 |
| 数据库适配与应用路径 | 13 项 unittest 通过 | 模拟 Calibre new_api，含复核、部分失败、实际回读快照 |
| Python 编译 | `compileall` 通过 | 语法检查，不等于 Calibre GUI 运行 |
| 插件打包 | 两个 ZIP 已构建 | 包含入口、模块、导入标记与 Apache 许可 |
| Calibre API 审查 | 已按官方当前源码核对 | 切库回调签名、工具栏位置、建列重启与窗口生命周期 |

以上 50 项离线测试通过：

```bash
python -m unittest discover -s tests -v
python -m compileall -q personal src build.py
python build.py
```

没有增加 GitHub Actions 工作流，也没有调用远端 CI。

## 仍需本机验收

- 真实 Calibre 安装、工具栏显示与自定义列生效。
- 用户所装 Qt WebEngine 是否能显示豆瓣登录页、扫码、验证码。
- 真实 `/mine/` 账号身份，以及公开／仅本人可见收藏的差异。
- 四个真实页面字段，尤其是旧版个人简评布局。
- 数据库写入后的自定义列显示，评分为 1–5 星。
- 窗口关闭、书库切换、网络超时后的真实 GUI 行为。

本次环境没有 Calibre 可执行程序与 Qt GUI 运行时，未访问用户豆瓣会话，未修改用户书库。合成页面和模拟数据库测试不构成真实账号同步验收。

## 实现依据

### 上游插件

- [原源码](https://github.com/fugary/calibre-douban/blob/deea4743d177e8439103bece4cf8faa4ab4e0f4a/src/__init__.py)：`NewDoubanBooks(Source)`、`douban_login_cookie`、`v:average` 公共评分及书籍简介。
- [原项目](https://github.com/fugary/calibre-douban)：Apache-2.0 许可、原作者与安装方式。

### Calibre

- [插件 API](https://manual.calibre-ebook.com/plugins.html)：`Source`、`InterfaceAction`。
- [界面插件说明](https://manual.calibre-ebook.com/creating_plugins.html)：入口与 `plugin-import-name-*.txt`。
- [数据库 API](https://manual.calibre-ebook.com/db_api.html)：`field_for`、`set_field`、`get_custom_book_data`、`add_custom_book_data`。
- [元数据合并](https://github.com/kovidgoyal/calibre/blob/master/src/calibre/ebooks/metadata/sources/identify.py)：多来源会合并 ratings/comments，故个人记录采用独立写入流程。
- [ZIP 插件加载](https://github.com/kovidgoyal/calibre/blob/master/src/calibre/customize/zipplugin.py)：一个包的插件入口选择规则，故构建两个独立 ZIP。
- [创建自定义列](https://github.com/kovidgoyal/calibre/blob/master/src/calibre/gui2/preferences/create_custom_column.py)：`CreateNewCustomColumn`，建列后需重启。
- [内嵌网页](https://github.com/kovidgoyal/calibre/blob/master/src/calibre/gui2/store/web_store.py)：Qt WebEngine 使用方式。

### 豆瓣页面

依据既有 `threeyang3/douban-import@a3bf14f4705326569d9e4f35f1c7bbda831159f2` 的请求地址和选择器重新实现，未复制 GPL 代码：

- [UserComponent.ts](https://github.com/threeyang3/douban-import/blob/a3bf14f4705326569d9e4f35f1c7bbda831159f2/src/sources/douban/auth/UserComponent.ts)：`GET https://www.douban.com/mine/` 与账号资料区域。
- [DoubanBookLoadHandler.ts](https://github.com/threeyang3/douban-import/blob/a3bf14f4705326569d9e4f35f1c7bbda831159f2/src/sources/douban/loaders/DoubanBookLoadHandler.ts)：个人状态与 `input#n_rating`。
- [DoubanPageParser.ts](https://github.com/threeyang3/douban-import/blob/a3bf14f4705326569d9e4f35f1c7bbda831159f2/src/sources/douban/parsing/DoubanPageParser.ts)：个人区域、标签与简评的布局线索。

部分兼容选择器仅由合成测试覆盖，不能据此断言所有当前豆瓣页面采用同一布局。无法识别则省略字段或跳过书籍。

## 本版本没有实现

跨重启登录保持、双向写回、全账号收藏自动建档、标题／ISBN 模糊匹配、页码进度、长书评或批注、定时运行、强制覆盖人工修改、来源删除传播、任意列映射、整批回滚、Media Core 自动连接。

下一轮优先解决真实登录与真实页面验收暴露的问题。
