#!/usr/bin/env python3
"""Build a reproducible, directly installable Calibre ZIP using only stdlib."""

import argparse
import ast
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent


def build_package(source, output):
    files = sorted(path for path in source.rglob("*") if path.is_file()
                   and (path.suffix == ".py" or path.name.startswith("plugin-import-name-")))
    for path in files:
        if path.suffix == ".py":
            # The minimum Calibre version uses Python 3.8.
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 8))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = ZipInfo(path.relative_to(source).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
        for name in ("LICENSE", "NOTICE.md"):
            path = ROOT / name
            if path.is_file():
                info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name + ".sha256").write_text(digest + "  " + output.name + "\n", encoding="ascii")
    print("{} ({} bytes)".format(output, output.stat().st_size))
    print("SHA-256: " + digest)
    return output


def build(output=None):
    path = Path(output) if output else ROOT / "dist" / "WebNovelMetadata.zip"
    return build_package(ROOT / "src", path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Path for the metadata source ZIP")
    args = parser.parse_args()
    source_zip = build(args.output)
    build_package(ROOT / "library", source_zip.with_name("WebNovelLibrary.zip"))
