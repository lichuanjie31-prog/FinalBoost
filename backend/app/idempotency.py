import hashlib
import json
import time
from fastapi.responses import JSONResponse
from .common import envelope, fail

def execute(db, user_id, request, payload, status, operation):
    key = request.headers.get("idempotency-key", "")
    if not 1 <= len(key) <= 128: fail(400,"请提供有效的 Idempotency-Key")
    scope = (user_id,request.method,request.url.path,key)
    request_hash = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    existing = db.execute("SELECT * FROM idempotency_records WHERE user_id=? AND method=? AND path=? AND key=?",scope).fetchone()
    if existing and existing["expires_at"] > time.time():
        if existing["request_hash"] != request_hash: fail(409,"同一个提交标识不能用于不同内容")
        return JSONResponse(status_code=existing["response_status"],content=json.loads(existing["response_json"]))
    if existing: db.execute("DELETE FROM idempotency_records WHERE user_id=? AND method=? AND path=? AND key=?",scope)
    result = envelope(operation())
    db.execute("INSERT INTO idempotency_records VALUES (?,?,?,?,?,?,?,?)",(*scope,request_hash,status,json.dumps(result,ensure_ascii=False),time.time()+86400))
    return JSONResponse(status_code=status,content=result)
