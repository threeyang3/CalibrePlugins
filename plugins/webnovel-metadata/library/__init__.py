"""Calibre entry point for writing downloaded web novel fields to the library."""

from calibre.customize import InterfaceActionBase


class WebNovelLibrary(InterfaceActionBase):
    name = 'WebNovel Library'
    description = '从网文元数据插件获取选中作品，为连载平台、首发日期、字数等自定义列填写数据。'
    author = 'threeyang3'
    version = (0, 2, 0)
    minimum_calibre_version = (8, 0, 0)
    actual_plugin = 'calibre_plugins.webnovel_library.action:WebNovelLibraryAction'
