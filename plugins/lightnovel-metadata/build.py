#!/usr/bin/env python3
"""Reproducible, zero-dependency Calibre plugin ZIP builder."""
import ast
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def build(output=None):
    output = Path(output) if output else ROOT / 'dist' / 'LightNovelMetadata.zip'
    source = ROOT / 'src'
    files = sorted(x for x in source.rglob('*') if x.is_file() and
                   (x.suffix == '.py' or x.name.startswith('plugin-import-name-')))
    for f in files:
        if f.suffix == '.py':
            ast.parse(f.read_text(encoding='utf-8'), filename=str(f), feature_version=(3, 8))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED, compresslevel=9) as zipfile:
        for f in files + [ROOT / 'LICENSE']:
            info = ZipInfo(f.relative_to(source).as_posix() if f in files else f.name,
                           (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zipfile.writestr(info, f.read_bytes())
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name + '.sha256').write_text(checksum + '  ' + output.name + '\n', encoding='ascii')
    return output


if __name__ == '__main__':
    path = build()
    print('%s (%s bytes)' % (path, path.stat().st_size))
