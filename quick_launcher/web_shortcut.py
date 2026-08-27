from __future__ import annotations

import uuid
from urllib.parse import urlsplit, urlunsplit

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .icon_service import IconService
from .models import AppEntry


class WebShortcutError(ValueError):
    pass


def favicon_url(target_url: str) -> str:
    parsed = urlsplit(target_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/favicon.ico", "", ""))


def normalize_web_url(raw_url: str) -> str:
    text = raw_url.strip()
    if not text:
        raise WebShortcutError("网页地址不能为空。")
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlsplit(text)
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise WebShortcutError("请输入有效的 http 或 https 网页地址。")
    try:
        port = parsed.port
    except ValueError as exc:
        raise WebShortcutError("网页地址端口无效。") from exc

    host = parsed.hostname.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def default_web_name(url: str) -> str:
    host = urlsplit(url).hostname or url
    return host.removeprefix("www.")


def build_web_entry(
    raw_url: str,
    name: str,
    category_id: str,
    existing_apps: tuple[AppEntry, ...],
) -> AppEntry:
    url = normalize_web_url(raw_url)
    display_name = name.strip()
    if not display_name:
        raise WebShortcutError("网页名称不能为空。")
    existing_urls = {
        normalize_web_url(app.target)
        for app in existing_apps
        if app.target.casefold().startswith(("http://", "https://"))
    }
    if url in existing_urls:
        raise WebShortcutError("该网页已经添加。")
    existing_ids = {app.id for app in existing_apps}
    while True:
        app_id = f"web-{uuid.uuid4().hex[:12]}"
        if app_id not in existing_ids:
            break
    return AppEntry(app_id, display_name, category_id, url)


class WebIconLoader(QObject):
    """Fetch a site's conventional favicon without blocking the UI thread."""

    finished = Signal(str, bool)

    def __init__(self, icon_service: IconService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._icon_service = icon_service
        self._network = QNetworkAccessManager(self)

    def fetch(self, target_url: str) -> None:
        request = QNetworkRequest(QUrl(favicon_url(target_url)))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Sushi/0.1")
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        reply = self._network.get(request)
        reply.finished.connect(lambda: self._finish(reply, target_url))

    def _finish(self, reply: QNetworkReply, target_url: str) -> None:
        success = False
        if reply.error() == QNetworkReply.NetworkError.NoError:
            success = self._icon_service.save_icon_data(target_url, bytes(reply.readAll()))
        reply.deleteLater()
        self.finished.emit(target_url, success)
