"""Build the public metadata source and optional personal-records companion.

No Calibre installation or network access is needed to create the ZIP files.
"""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent


def zip_dir(input_path, output_file):
    source = Path(input_path)
    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {path.relative_to(source).as_posix(): path
             for path in source.rglob('*')
             if path.is_file() and '__pycache__' not in path.parts
             and (path.suffix == '.py' or path.name.startswith('plugin-import-name-'))}
    files['LICENSE'] = ROOT / 'LICENSE'
    files['NOTICE'] = ROOT / 'NOTICE'
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, path in sorted(files.items()):
            info = ZipInfo(name, date_time=(2026, 11, 10, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    print(f'{output.name}: {output.stat().st_size:,} bytes')


if __name__ == '__main__':
    zip_dir(ROOT / 'src', ROOT / 'out' / 'NewDouban.zip')
    zip_dir(ROOT / 'personal', ROOT / 'out' / 'DoubanReadingRecords.zip')
