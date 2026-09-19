"""Verify immutable source documents and generated OpenAPI without rewriting them."""
import hashlib
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from app.main import create_app

expected={
    'FinalBoost-API-v1.0.md':'6808CC8BA5F684D0A5A28F483FDD50343543B35894C3857DD0C6A3250CA4789A',
    'FinalBoost-MVP-design.md':'7D365C5D62F8A4208D886C53F28607716751D5AD63903E35F9A9572858932B2B',
    'FinalBoost-team-framework.md':'906D8F589CC285A663B4317F051C1143CE12A1C05810E88A3F893FBA70DEBECE',
}
for name,value in expected.items():
    actual=hashlib.sha256((root/'docs'/name).read_bytes()).hexdigest().upper()
    assert actual==value, f'Original document changed: {name}'
    print(f'SHA256 PASS {name}: {actual}')
actual=create_app(grading_mode='mock').openapi()
saved=json.loads((root/'contracts/openapi.json').read_text(encoding='utf-8'))
assert actual==saved, 'OpenAPI differs from backend models; export again'
print(f'OPENAPI PASS: {len(actual["paths"])} paths match running models')
