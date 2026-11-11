"""Optional, on-demand Calibre UI for importing one's own Douban records."""

from queue import Empty, Queue
from threading import Event, Thread

from qt.core import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QTimer, Qt, QVBoxLayout,
)
from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction

from .client import DoubanClient
from .core import DoubanError, LoginRequired, NoRecord
from .login import LoginDialog
from .storage import apply_selected, capture_targets, compatible_columns
from .sync import FIELD_SPECS, build_plan


class DoubanReadingAction(InterfaceAction):
    name = 'Douban Reading Records'
    action_spec = ('豆瓣阅读记录', 'book.png', '登录豆瓣，读取个人阅读记录并预览导入', None)

    def genesis(self):
        self.cookie_jar = None
        self.account = None
        self.dialog = None
        self.in_library = True
        self.qaction.triggered.connect(self.show_records)

    def location_selected(self, loc):
        self.in_library = loc == 'library'
        self.qaction.setEnabled(self.in_library)
        if self.menuless_qaction is not None:
            self.menuless_qaction.setEnabled(self.in_library)
        if not self.in_library and self.dialog is not None:
            self.dialog.invalidate_library()

    def show_records(self):
        if not self.in_library:
            return
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        dialog = self.dialog = RecordsDialog(self)
        try:
            dialog.exec()
        finally:
            dialog.cancel_event.set()
            dialog.timer.stop()
            dialog.deleteLater()
            self.dialog = None

    def library_about_to_change(self, olddb, db):
        if self.dialog is not None:
            self.dialog.invalidate_library()

    def library_changed(self, db):
        if self.dialog is not None:
            self.dialog.invalidate_library()


def plain_label(text, parent):
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def display_value(key, value):
    if value is None or value == '' or value == [] or value == ():
        return '（空）'
    if key == 'tags':
        return '、'.join(value)
    if key == 'rating':
        return f'{value / 2:g} / 5 星' if value else '（未评分）'
    if key == 'comment':
        from calibre.ebooks.BeautifulSoup import BeautifulSoup
        return BeautifulSoup(str(value)).get_text('\n', strip=True)
    return str(value)


class RecordsDialog(QDialog):
    def __init__(self, action):
        super().__init__(action.gui)
        self.action = action
        self.gui = action.gui
        self.db = self.gui.current_db.new_api
        self.library_id = self.db.library_id
        self.invalidated = False
        self.busy = False
        self.cancel_event = Event()
        self.events = Queue()
        self.plan_rows = []
        self.preview_account_id = None
        self.setWindowTitle('豆瓣阅读记录 · 测试版 0.1.0')
        self.resize(1080, 660)
        layout = QVBoxLayout(self)
        self.account_label = plain_label('', self)
        layout.addWidget(self.account_label)
        layout.addWidget(plain_label(
            '选中书籍 → 读取豆瓣 → 检查变化 → 写入勾选项。个人数据保存到四个独立列；'
            '本地手动修改会保留。登录会话只保留到本次 Calibre 退出。', self))
        buttons = QHBoxLayout()
        self.login_button = QPushButton('登录 / 切换豆瓣账号', self)
        self.logout_button = QPushButton('退出登录', self)
        self.columns_button = QPushButton('创建所需的四个列', self)
        self.fetch_button = QPushButton('读取选中书籍', self)
        for button in (self.login_button, self.logout_button, self.columns_button, self.fetch_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.login_button.clicked.connect(self.login)
        self.logout_button.clicked.connect(self.logout)
        self.columns_button.clicked.connect(self.create_columns)
        self.fetch_button.clicked.connect(self.fetch)
        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(['导入', '书籍 / 豆瓣 ID', '字段', '当前值', '豆瓣值', '处理说明'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate((48, 210, 105, 190, 190, 260)):
            self.table.setColumnWidth(col, width)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self.update_apply_button)
        layout.addWidget(self.table)
        self.status = plain_label('', self)
        layout.addWidget(self.status)
        footer = QHBoxLayout()
        self.cancel_button = QPushButton('取消读取', self)
        self.apply_button = QPushButton('写入勾选项', self)
        self.close_button = QPushButton('关闭', self)
        footer.addWidget(self.cancel_button)
        footer.addStretch(1)
        footer.addWidget(self.apply_button)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.cancel_button.clicked.connect(self.cancel_read)
        self.apply_button.clicked.connect(self.apply)
        self.close_button.clicked.connect(self.reject)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.refresh_controls()

    def is_same_library(self):
        return (not self.invalidated and self.gui.current_db.new_api is self.db
                and self.db.library_id == self.library_id)

    def invalidate_library(self):
        self.invalidated = True
        self.cancel_event.set()
        self.clear_preview()
        self.status.setText('书库或设备视图已经切换，请关闭后在书库中重新打开插件。')
        self.refresh_controls()

    def reject(self):
        self.cancel_event.set()
        self.timer.stop()
        super().reject()

    def clear_preview(self):
        self.plan_rows = []
        self.preview_account_id = None
        self.table.setRowCount(0)
        self.apply_button.setEnabled(False)

    def refresh_controls(self):
        available = not self.busy and self.is_same_library()
        account = self.action.account
        self.account_label.setText(
            f'已验证账号：{account.display_name}（{account.user_id}）' if account else '尚未登录豆瓣。')
        self.login_button.setEnabled(available)
        self.logout_button.setEnabled(available and account is not None)
        self.columns_button.setEnabled(available)
        self.fetch_button.setEnabled(available and account is not None)
        self.cancel_button.setEnabled(self.busy and not self.cancel_event.is_set())
        self.update_apply_button()

    def update_apply_button(self, *args):
        checked = any(
            self.table.item(row, 0) is not None
            and self.table.item(row, 0).checkState() == Qt.CheckState.Checked
            for row in range(len(self.plan_rows)))
        self.apply_button.setEnabled(not self.busy and self.is_same_library() and checked)

    def start_job(self, job):
        self.clear_preview()
        self.busy = True
        self.cancel_event = Event()
        self.events = Queue()
        event_queue, cancel = self.events, self.cancel_event

        def run():
            try:
                result = job(event_queue, cancel)
                event_queue.put(('result', result))
            except LoginRequired as exc:
                event_queue.put(('login_required', str(exc)))
            except DoubanError as exc:
                event_queue.put(('error', str(exc)))
            except Exception:
                event_queue.put(('error', '读取未完成。请检查网络或重新登录；书库数据没有写入。'))

        Thread(target=run, name='douban-reading-records', daemon=True).start()
        self.timer.start()
        self.refresh_controls()

    def poll(self):
        if not self.is_same_library() and not self.invalidated:
            self.invalidate_library()
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except Empty:
                return
            if kind == 'progress':
                if not self.cancel_event.is_set():
                    self.status.setText(payload)
                continue
            self.busy = False
            self.timer.stop()
            if self.cancel_event.is_set() or not self.is_same_library():
                self.status.setText('读取已取消，未写入任何字段。' if not self.invalidated else '书库已切换，结果已丢弃。')
            elif kind in ('error', 'login_required'):
                if kind == 'login_required':
                    self.action.cookie_jar = None
                    self.action.account = None
                self.status.setText(payload)
            elif payload['kind'] == 'login':
                self.action.cookie_jar = payload['client'].cookie_jar
                self.action.account = payload['account']
                self.status.setText('账号验证成功。可读取已关联豆瓣条目的选中书籍。')
            else:
                self.action.cookie_jar = payload['client'].cookie_jar
                self.show_preview(payload)
            self.refresh_controls()

    def cancel_read(self):
        self.cancel_event.set()
        self.status.setText('正在取消；当前网络请求结束后停止。')
        self.refresh_controls()

    def login(self):
        dialog = LoginDialog(self)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            jar, cookie = dialog.cookie_jar, dialog.cookie_header
        finally:
            dialog.deleteLater()
        self.clear_preview()
        # Drop the old identity before testing a replacement session.
        self.action.cookie_jar = None
        self.action.account = None
        self.status.setText('正在向豆瓣验证账号身份……')

        def job(events, cancel):
            client = DoubanClient(cookie_jar=jar, cookie_header=cookie, cancel_event=cancel)
            account = client.verify_account()
            return {'kind': 'login', 'client': client, 'account': account}

        self.start_job(job)

    def logout(self):
        self.action.cookie_jar = None
        self.action.account = None
        self.clear_preview()
        self.status.setText('本插件的登录会话已清除。已导入的阅读记录保留。')
        self.refresh_controls()

    def create_columns(self):
        if not self.is_same_library():
            return
        from calibre.gui2.preferences.create_custom_column import CreateNewCustomColumn
        missing, incompatible = compatible_columns(self.db)
        if incompatible:
            error_dialog(self, '列类型不匹配', '请先检查这些列的类型：' + '、'.join(incompatible), show=True)
            return
        if not missing:
            info_dialog(self, '已就绪', '四个自定义列已经存在，类型正确。', show=True)
            return
        creator = CreateNewCustomColumn(self.gui)
        added = 0
        for spec in FIELD_SPECS.values():
            if spec['column'] not in missing:
                continue
            result, message = creator.create_column(
                spec['column'], spec['name'], spec['datatype'], spec['is_multiple'],
                display={'description': '由豆瓣阅读记录插件填写；本地手改受保护。'},
                freeze_lookup_name=True)
            if result == creator.Result.COLUMN_ADDED:
                added += 1
            elif result == creator.Result.CANCELED:
                break
            else:
                error_dialog(self, '未能继续创建列', message, show=True)
                break
        if added:
            info_dialog(self, '请重启 Calibre',
                        f'已创建 {added} 个列。重启 Calibre 后，重新打开豆瓣阅读记录即可使用；缺少的列可稍后继续创建。',
                        show=True)
            self.reject()

    def fetch(self):
        if not self.is_same_library() or self.action.account is None:
            return
        if self.gui.must_restart_before_config:
            info_dialog(self, '请先重启', '自定义列有待生效的更改，请重启 Calibre。', show=True)
            return
        missing, incompatible = compatible_columns(self.db)
        if missing or incompatible:
            message = '请先点击“创建所需的四个列”，然后重启 Calibre。' if missing else '这些自定义列的类型不匹配：' + '、'.join(incompatible)
            error_dialog(self, '尚未准备好目标列', message, show=True)
            return
        rows = self.gui.library_view.selectionModel().selectedRows()
        ids = [self.gui.library_view.model().id(row) for row in rows]
        if not ids:
            info_dialog(self, '请先选择书籍', '在 Calibre 书库中选中需要读取豆瓣记录的书籍。', show=True)
            return
        targets, skipped = capture_targets(self.db, ids)
        if not targets:
            error_dialog(self, '没有可读取的关联', '\n'.join(f'{title}：{reason}' for title, reason in skipped), show=True)
            return
        expected_account = self.action.account.user_id
        jar = self.action.cookie_jar
        self.status.setText(f'正在读取 {len(targets)} 本书的个人记录……')

        def job(events, cancel):
            client = DoubanClient(cookie_jar=jar, cancel_event=cancel)
            account = client.verify_account()
            if account.user_id != expected_account:
                raise DoubanError('登录账号已改变，请重新登录后读取。')
            records, misses, cache = [], list(skipped), {}
            for index, target in enumerate(targets, 1):
                events.put(('progress', f'正在读取 {index}/{len(targets)}：{target.title}'))
                try:
                    if target.subject_id not in cache:
                        cache[target.subject_id] = client.fetch_record(target.subject_id, expected_account)
                    record = cache[target.subject_id]
                    records.append((target, record))
                except NoRecord as exc:
                    misses.append((target.title, str(exc)))
            if client.verify_account().user_id != expected_account:
                raise DoubanError('读取期间登录账号发生变化，结果已丢弃，请重新登录。')
            return {'kind': 'records', 'account': account, 'client': client,
                    'records': records, 'skipped': misses}

        self.start_job(job)

    def show_preview(self, result):
        account_id = result['account'].user_id
        self.preview_account_id = account_id
        self.plan_rows = []
        for target, record in result['records']:
            if record.account_id != account_id or record.subject_id != target.subject_id:
                self.clear_preview()
                self.status.setText('读取结果的账号或书籍关联不一致，请重新读取。')
                return
            for change in build_plan(target.book_id, target.book_uuid, account_id, target.subject_id,
                                     target.current, target.previous, record.values):
                self.plan_rows.append((target, change, record))
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.plan_rows))
        for row, (target, change, record) in enumerate(self.plan_rows):
            check = QTableWidgetItem('')
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if change.allowed:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            check.setFlags(flags)
            check.setCheckState(Qt.CheckState.Checked if change.allowed else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)
            texts = [f'{target.title} · {target.subject_id}', FIELD_SPECS[change.key]['name'],
                     display_value(change.key, change.before), display_value(change.key, change.after), change.reason]
            for col, text in enumerate(texts, 1):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        count = sum(change.allowed for target, change, record in self.plan_rows)
        skipped = result['skipped']
        self.status.setText(f'读取完成：{len(result["records"])} 本书，{count} 个可导入字段；跳过 {len(skipped)} 本。'
                            '检查后点击“写入勾选项”。' +
                            ('\n' + '\n'.join(f'{title}：{reason}' for title, reason in skipped[:8]) if skipped else ''))

    def apply(self):
        if (not self.is_same_library() or self.action.account is None
                or self.action.account.user_id != self.preview_account_id):
            self.clear_preview()
            self.status.setText('书库或账号已改变，请重新读取。')
            return
        selected = [entry for row, entry in enumerate(self.plan_rows)
                    if entry[1].allowed and self.table.item(row, 0).checkState() == Qt.CheckState.Checked]
        if not selected:
            return
        written, skipped, error = apply_selected(
            self.db, self.library_id, lambda: self.gui.current_db.new_api,
            self.preview_account_id, selected)
        self.clear_preview()
        affected = {book_id for book_id, key in written}
        if affected:
            self.gui.library_view.model().refresh_ids(affected)
            self.gui.tags_view.recount()
        self.status.setText(f'已写入 {len(affected)} 本书的 {len(written)} 个字段；另有 {len(skipped)} 个字段保留。'
                            + ('\n' + error if error else '') +
                            ('\n' + '\n'.join(f'{title}：{reason}' for title, reason in skipped[:5]) if skipped else ''))
        self.refresh_controls()
