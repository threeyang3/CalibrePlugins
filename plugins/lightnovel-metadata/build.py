#!/usr/bin/env python3
"""Reproducible, zero-dependency Calibre plugin ZIP builder."""
import ast
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def build_package(source, output):
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


def build(output=None):
    path = Path(output) if output else ROOT / 'dist' / 'LightNovelMetadata.zip'
    return build_package(ROOT / 'src', path)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Path for the metadata source ZIP')
    source_zip = build(parser.parse_args().output)
    library_zip = build_package(ROOT / 'library', source_zip.with_name('LightNovelLibrary.zip'))
    for path in (source_zip, library_zip):
        print('%s (%s bytes)' % (path, path.stat().st_size))
