"""Short-lived capability downloads keep PDF bytes out of model transcripts."""
import hashlib
import os
from pathlib import Path
import re
import secrets
import tempfile
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..pdf import verify_pdf_bytes

router = APIRouter(prefix='/api/v1/materials/artifacts', tags=['materials'])
_TOKEN = re.compile(r'^[A-Za-z0-9_-]{43}$')
MAX_ARTIFACTS = 128


def _directory():
    return Path(os.environ.get('MATERIAL_ARTIFACT_DIR') or
                Path(tempfile.gettempdir()) / 'finalboost-practice-artifacts')


def store_pdf(data, filename, question_count, ttl_seconds=900):
    verify_pdf_bytes(data)
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    now = time.time()
    active = 0
    for entry in directory.glob('*.pdf'):
        if not _TOKEN.fullmatch(entry.stem):
            continue
        try:
            if entry.stat().st_mtime <= now:
                entry.unlink(missing_ok=True)
            else:
                active += 1
        except FileNotFoundError:
            continue
    if active >= MAX_ARTIFACTS:
        raise ValueError('临时题卷存储已满，请稍后重试')
    token = secrets.token_urlsafe(32)
    path = directory / f'{token}.pdf'
    with path.open('xb') as stream:
        stream.write(data)
    expiry = now + ttl_seconds
    os.utime(path, (expiry, expiry))
    base = os.environ.get('MATERIAL_PUBLIC_BASE_URL', 'https://dumate.codehive.asia').rstrip('/')
    return {'filename': filename, 'mimeType': 'application/pdf',
            'downloadUrl': f'{base}/api/v1/materials/artifacts/{token}',
            'sha256': hashlib.sha256(data).hexdigest(), 'sizeBytes': len(data),
            'questionCount': question_count, 'expiresAt': expiry}


def load_pdf(token, now=None):
    if not _TOKEN.fullmatch(token):
        return None
    path = _directory() / f'{token}.pdf'
    try:
        if path.stat().st_mtime <= (time.time() if now is None else now):
            return None
        return path
    except FileNotFoundError:
        return None


@router.get('/{token}')
def download_pdf(token: str):
    path = load_pdf(token)
    if path is None:
        raise HTTPException(404, '题卷链接不存在或已过期')
    return FileResponse(path, media_type='application/pdf', filename='专项练习卷.pdf',
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
