"""Calibre GUI entry point for the optional personal-reading companion."""

from calibre.customize import InterfaceActionBase


class DoubanReadingRecords(InterfaceActionBase):
    name = 'Douban Reading Records'
    description = '读取豆瓣个人标签、评分、阅读状态和简评，预览后保存到独立自定义列。'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Calibre Douban contributors'
    version = (0, 1, 0)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin = 'calibre_plugins.douban_reading_records.action:DoubanReadingAction'
