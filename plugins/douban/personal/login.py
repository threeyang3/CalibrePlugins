"""Session-only Douban login for the personal-records interface plugin.

The caller must verify the returned session against Douban before using it.
Closing the web login window never proves which account, if any, signed in.
"""

import copy
import re
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy

from qt.core import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QUrl,
    QVBoxLayout,
)


LOGIN_URL = 'https://accounts.douban.com/passport/login'
LOGIN_HOSTS = frozenset((
    'douban.com', 'www.douban.com', 'book.douban.com', 'accounts.douban.com',
    'sec.douban.com',
))
COOKIE_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def new_cookie_jar():
    """Keep host-only cookies on their original host."""
    policy = DefaultCookiePolicy(
        strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain,
    )
    return CookieJar(policy=policy)


def cookie_from_qt(cookie):
    """Copy a QNetworkCookie without losing HTTP-only or scope information.

    Qt WebEngine is deliberately not imported here: this conversion only
    requires the cookie's public accessors. Unrelated cookies are ignored.
    """
    domain = str(cookie.domain()).lower()
    host = domain[1:] if domain.startswith('.') else domain
    if not (host == 'douban.com' or host.endswith('.douban.com')):
        return None
    if not host or host.startswith('.') or any(c.isspace() for c in domain):
        return None
    name = bytes(cookie.name()).decode('latin-1')
    value = bytes(cookie.value()).decode('latin-1')
    if not COOKIE_NAME.fullmatch(name) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    path = str(cookie.path()) or '/'
    if not path.startswith('/'):
        return None
    session = bool(cookie.isSessionCookie())
    expires = None
    if not session:
        expiry = cookie.expirationDate()
        if not expiry.isValid():
            return None
        expires = int(expiry.toSecsSinceEpoch())
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=domain.startswith('.'),
        domain_initial_dot=domain.startswith('.'),
        path=path,
        path_specified=bool(cookie.path()),
        secure=bool(cookie.isSecure()),
        expires=expires,
        discard=session,
        comment=None,
        comment_url=None,
        rest={'HttpOnly': None} if cookie.isHttpOnly() else {},
        rfc2109=False,
    )


class ManualCookieDialog(QDialog):
    """Explicit fallback for an already-authenticated browser session."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cookie_header = ''
        self.setWindowTitle('使用豆瓣浏览器登录状态')
        layout = QVBoxLayout(self)
        explanation = QLabel(
            '在你已登录豆瓣的浏览器中，打开开发者工具的“网络”面板，'
            '刷新豆瓣读书页面，复制发往 book.douban.com 的请求中的 Cookie 请求头值。'
            '\n粘贴的登录状态只在本次 Calibre 会话中使用；下一步会核对实际账号。',
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.cookie_input = QLineEdit(self)
        self.cookie_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.cookie_input.setPlaceholderText('粘贴 Cookie 请求头值，不是账号密码')
        self.cookie_input.setAccessibleName('豆瓣 Cookie 请求头值')
        layout.addWidget(self.cookie_input)
        self.message = QLabel('', self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('继续核对账号')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(580, 230)

    def accept(self):
        value = self.cookie_input.text().strip()
        if value.lower().startswith('cookie:'):
            value = value[7:].strip()
        if not value or '=' not in value:
            self.message.setText('请粘贴有效的 Cookie 请求头值。')
            return
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            self.message.setText('请只复制一行 Cookie 请求头值，不要粘贴完整请求。')
            return
        self.cookie_header = value
        self.cookie_input.clear()
        super().accept()

    def reject(self):
        self.cookie_input.clear()
        self.cookie_header = ''
        super().reject()


class LoginDialog(QDialog):
    """Return cookie_jar or cookie_header after the user's login action.

    ``Accepted`` means the user asked to proceed, not that authentication
    succeeded. The caller must verify the session and display the account.
    Neither passwords nor cookies are written to disk by this dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cookie_jar = new_cookie_jar()
        self._cookie_header = ''
        self._cookies = {}
        self._view = self._profile = self._page = self._store = None
        self._disposed = False
        self.setWindowTitle('登录豆瓣，导入个人阅读记录')
        layout = self._layout = QVBoxLayout(self)
        explanation = QLabel(
            '请在豆瓣网页中自行完成登录和验证码。完成后点击“完成登录”，'
            '插件会在下一步核对账号，再读取个人阅读记录。'
            '\n登录状态仅保留在本次 Calibre 会话中。',
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self._status = QLabel('', self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        browser_ready = self._start_browser()
        controls = QHBoxLayout()
        fallback = QPushButton('使用已登录浏览器的 Cookie…', self)
        fallback.clicked.connect(self._manual_cookie)
        controls.addWidget(fallback)
        controls.addStretch(1)
        cancel = QPushButton('取消', self)
        cancel.clicked.connect(self.reject)
        controls.addWidget(cancel)
        finish = QPushButton('完成登录', self)
        finish.setEnabled(browser_ready)
        finish.clicked.connect(self._finish_login)
        controls.addWidget(finish)
        layout.addLayout(controls)
        self.resize(860, 740 if browser_ready else 260)

    @property
    def cookie_jar(self):
        return self._cookie_jar

    @property
    def cookie_header(self):
        return self._cookie_header

    def _start_browser(self):
        try:
            # Some calibre packages omit Qt WebEngine. Import it only when
            # opening this dialog, so the manual session fallback still works.
            from qt.webengine import QWebEnginePage, QWebEngineProfile, QWebEngineView

            class LoginPage(QWebEnginePage):
                def acceptNavigationRequest(page, url, navigation_type, is_main_frame):
                    if not is_main_frame:
                        return True
                    allowed = (
                        url.isValid()
                        and url.scheme().lower() == 'https'
                        and url.host().lower() in LOGIN_HOSTS
                        and url.port(-1) in (-1, 443)
                        and not url.userName()
                        and not url.password()
                    )
                    if not allowed:
                        self._status.setText('登录窗口仅打开豆瓣的 HTTPS 页面。')
                    return allowed

                def createWindow(page, window_type):
                    # Do not create an unrestricted popup browser.
                    return None

            self._view = QWebEngineView(self)
            # No storage name means an off-the-record profile. No cookie or
            # local-storage persistence is enabled, and no default profile is used.
            self._profile = QWebEngineProfile(self)
            self._page = LoginPage(self._profile, self._view)
            self._view.setPage(self._page)
            self._store = self._profile.cookieStore()
            self._store.cookieAdded.connect(self._cookie_added)
            self._store.cookieRemoved.connect(self._cookie_removed)
            self._store.loadAllCookies()
            self._layout.addWidget(self._view, 1)
            self._view.load(QUrl(LOGIN_URL))
            return True
        except (ImportError, AttributeError, RuntimeError):
            self._dispose_browser()
            self._status.setText(
                '当前 Calibre 环境无法打开内嵌登录网页。'
                '可使用下方按钮导入已登录浏览器的 Cookie。'
            )
            return False

    def _cookie_added(self, qt_cookie):
        cookie = cookie_from_qt(qt_cookie)
        if cookie is not None:
            key = (cookie.domain, cookie.path, cookie.name)
            if cookie.is_expired():
                self._cookies.pop(key, None)
            else:
                self._cookies[key] = cookie

    def _cookie_removed(self, qt_cookie):
        cookie = cookie_from_qt(qt_cookie)
        if cookie is not None:
            self._cookies.pop((cookie.domain, cookie.path, cookie.name), None)

    def _finish_login(self):
        jar = new_cookie_jar()
        for cookie in self._cookies.values():
            if not cookie.is_expired():
                jar.set_cookie(copy.copy(cookie))
        self._cookie_jar = jar
        self._cookie_header = ''
        self.accept()

    def _manual_cookie(self):
        dialog = ManualCookieDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._cookie_header = dialog.cookie_header
            dialog.cookie_header = ''
            self._cookie_jar = new_cookie_jar()
            self.accept()
        dialog.deleteLater()

    def reject(self):
        self._cookie_header = ''
        self._cookie_jar = new_cookie_jar()
        super().reject()

    def done(self, result):
        self._dispose_browser()
        super().done(result)

    def _dispose_browser(self):
        if self._disposed:
            return
        self._disposed = True
        if self._store is not None:
            try:
                self._store.cookieAdded.disconnect(self._cookie_added)
                self._store.cookieRemoved.disconnect(self._cookie_removed)
            except (TypeError, RuntimeError):
                pass
        if self._view is not None:
            self._view.stop()
            self._view.hide()
        # A profile must outlive its pages. Queue their destruction in that order.
        if self._page is not None:
            self._page.deleteLater()
        if self._view is not None:
            self._view.deleteLater()
        if self._profile is not None:
            self._profile.deleteLater()
        # LoginPage's navigation callback closes over this dialog. Drop our
        # references as well, so repeated login attempts do not retain that cycle.
        self._page = self._view = self._profile = self._store = None
        self._cookies.clear()
