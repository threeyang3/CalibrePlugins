# 将 LightNovel Metadata v0.2.0 并入 CalibrePlugins

插件必须独立放在 `CalibrePlugins/plugins/lightnovel-metadata/`，不修改已有的豆瓣或网文插件。

在 CalibrePlugins 根目录：

```bash
git switch -c feat/lightnovel-metadata-v0.2.0
# 使用本文发布的增量补丁，将整个插件目录加入项目
git apply --check /path/to/LightNovelMetadata-v0.2.0.patch
git apply /path/to/LightNovelMetadata-v0.2.0.patch
python3 -m unittest discover -s plugins/lightnovel-metadata/tests -p 'test_*.py' -v
python3 plugins/lightnovel-metadata/build.py
git diff --check
git add plugins/lightnovel-metadata
git commit -m "feat: add light novel metadata sources and edition-aware fusion"
git push -u origin feat/lightnovel-metadata-v0.2.0
```

也可从完整源码 ZIP 解压相同目录，无需额外安装运行依赖。构建产物在 `dist/`，已被 `.gitignore` 排除。

**建议以草稿 PR 引入源码，不立刻发布稳定版。** 先完成 `docs/VALIDATION.md` 所列 Calibre 和目标网站真实验收；禁用不稳定的数据源；最后再创建独立 `lightnovel-metadata-v0.2.0` Release 与可安装 ZIP，避免将预览版误标为稳定版。

插件中没有计划持续 CI 或定时任务。根目录 README 可新增插件条目，但在测试阶段应标注**预览/真实网站待验证**。
