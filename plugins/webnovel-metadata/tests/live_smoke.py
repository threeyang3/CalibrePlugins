"""Optional live-site check through the installed Calibre plugin.

Run only when you intend to contact the three official platforms:
    calibre-debug -e tests/live_smoke.py -- --run-live

Uses one search candidate per platform, no retries or chapter requests, and an
isolated configuration. A platform failure is reported, not hidden by fixtures.
"""

import json
import os
import sys
from queue import Queue
from threading import Event


def main():
    if "--run-live" not in sys.argv or not os.environ.get("CALIBRE_CONFIG_DIRECTORY"):
        raise SystemExit("Use an isolated CALIBRE_CONFIG_DIRECTORY and pass --run-live explicitly.")
    from calibre.constants import __version__
    from calibre.customize.ui import metadata_plugins
    from calibre.ebooks.metadata.sources.base import create_log
    from calibre.utils.imghdr import identify

    source = next(plugin for plugin in metadata_plugins(["identify"]) if plugin.name == "WebNovel Metadata")
    saved = {option.name: source.prefs[option.name] for option in source.options}
    results = []
    cases = (
        ("qidian", "search", {"title": "诡秘之主", "authors": ["爱潜水的乌贼"]}),
        ("qimao", "search", {"title": "盖世神医", "authors": ["狐颜乱语"]}),
        ("fanqie", "identifier", {"identifiers": {"fanqie": "7143038691944959011"}}),
    )
    try:
        for option in source.options:
            source.prefs[option.name] = option.default
        source.prefs["max_candidates"] = 1
        for provider, mode, query in cases:
            print("Checking {} {}...".format(provider, mode), flush=True)
            for key in ("qidian", "qimao", "fanqie"):
                source.prefs["enable_" + key] = key == provider
            queue, log = Queue(), create_log()
            source.identify(log, queue, Event(), timeout=30, **query)
            if queue.empty():
                results.append({"provider": provider, "query_mode": mode, "metadata_ok": False})
                print("Metadata unavailable; inspect Calibre's normal download log for details.", flush=True)
                continue
            metadata = queue.get_nowait()
            covers = Queue()
            source.download_cover(log, covers, Event(), identifiers=metadata.identifiers,
                                  timeout=20, get_best_cover=True)
            cover_info = None
            if not covers.empty():
                unused, data = covers.get_nowait()
                fmt, width, height = identify(data)
                cover_info = {"bytes": len(data), "format": fmt, "width": width, "height": height}
            record = {
                "provider": provider, "query_mode": mode, "metadata_ok": True,
                "title": metadata.title, "authors": metadata.authors,
                "identifiers": metadata.identifiers,
                "publication_date": metadata.pubdate.isoformat() if metadata.pubdate else None,
                "comments_characters": len(metadata.comments or ""), "cover": cover_info,
            }
            results.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
        print(json.dumps({"calibre": __version__, "results": results}, ensure_ascii=False, indent=2))
    finally:
        for key, value in saved.items():
            source.prefs[key] = value
    if not all(result.get("metadata_ok") and result.get("cover") for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
