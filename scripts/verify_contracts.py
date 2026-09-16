"""Verify immutable source documents and generated OpenAPI without rewriting them."""
import hashlib
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from app.main import create_app

expected={
    'FinalBoost-API-v1.0.md':'71333021A7DBA954CA7DF4FAA7385F1DC7F9ED9DFCC3A37323E9A89BDA8CEA5B',
    'FinalBoost-MVP-design.md':'E467E3CE756ACB9342FC55E5699FEB49B03604B80B2ACD47A492E7BA8A9C6F3A',
    'FinalBoost-team-framework.md':'9D0B47A2B2C4840AB2889453BC6B8EBA6F933D3C4670DDE04C9E422979307C5B',
}
for name,value in expected.items():
    actual=hashlib.sha256((root/'docs'/name).read_bytes()).hexdigest().upper()
    assert actual==value, f'Original document changed: {name}'
    print(f'SHA256 PASS {name}: {actual}')
actual=create_app(grading_mode='mock').openapi()
saved=json.loads((root/'contracts/openapi.json').read_text(encoding='utf-8'))
assert actual==saved, 'OpenAPI differs from backend models; export again'
print(f'OPENAPI PASS: {len(actual["paths"])} paths match running models')
