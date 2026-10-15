"""Download trusted practice artifacts without passing binary text through an LLM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 10_000_000


def download_pdf(metadata, destination):
    destination = Path(destination)
    url = str(metadata.get('downloadUrl', ''))
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or parsed.username or parsed.password:
        raise ValueError('无效的题卷下载链接')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('远程题卷必须使用 HTTPS')
    if not re.fullmatch(r'/api/v1/materials/artifacts/[A-Za-z0-9_-]{43}', parsed.path):
        raise ValueError('题卷下载路径无效')
    expected_hash = metadata.get('sha256', '')
    expected_size = metadata.get('sizeBytes')
    if not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
        raise ValueError('缺少有效的 SHA-256')
    if type(expected_size) is not int or not 0 < expected_size <= MAX_BYTES:
        raise ValueError('题卷字节数无效')
    if metadata.get('questionCount') != 3:
        raise ValueError('当前检验卷必须完整包含三道题')
    with urlopen(Request(url), timeout=15) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError('题卷字节数或 SHA-256 不一致，禁止交付')
    if not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):
        raise ValueError('题卷文件不完整')
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != expected_hash:
            raise FileExistsError('目标文件已存在，请更换文件名，保留原文件')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.part', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            # No destination file exists until all integrity checks pass.
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {'path': str(destination.resolve()), 'sha256': expected_hash,
            'sizeBytes': len(data), 'questionCount': 3}


def checked_download(metadata_path, destination, timeout_seconds=15):
    """Kill the entire fetch on a wall-clock deadline, including DNS/slow reads."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.practice-download-') as directory:
        candidate = Path(directory) / 'verified.pdf'
        try:
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                                        str(Path(metadata_path).resolve()), str(candidate)],
                                       capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('完整 PDF 下载超时，已停止下载，禁止交付') from exc
        if completed.returncode != 0:
            raise ValueError('PDF 下载或完整性核验失败，禁止交付')
        metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
        data = candidate.read_bytes()
        if hashlib.sha256(data).hexdigest() != metadata['sha256']:
            raise ValueError('PDF 完整性校验失败')
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != metadata['sha256']:
                raise FileExistsError('目标文件已存在，请更换文件名')
        else:
            os.replace(candidate, destination)
    return {'path': str(destination.resolve()), 'sha256': metadata['sha256'],
            'sizeBytes': len(data), 'questionCount': 3}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('metadata', help='JSON metadata returned by generate_practice_pdf')
    parser.add_argument('destination', help='new local PDF filename')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        metadata = json.loads(Path(args.metadata).read_text(encoding='utf-8'))
        result = download_pdf(metadata, args.destination)
    else:
        result = checked_download(args.metadata, args.destination)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
