"""Calibre entry point for updating selected light novel editions by ISBN."""

from calibre.customize import InterfaceActionBase


class LightNovelLibrary(InterfaceActionBase):
    name = 'LightNovel Library'
    description = '按 ISBN 补齐选中轻小说的出版资料及专用栏目，保留已有资料和封面。'
    author = 'threeyang3'
    version = (0, 3, 0)
    minimum_calibre_version = (8, 0, 0)
    actual_plugin = 'calibre_plugins.lightnovel_library.action:LightNovelLibraryAction'
