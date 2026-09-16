import uuid
from fastapi import HTTPException
def new_id(): return uuid.uuid4().hex
def envelope(data, request_id=None): return {"code":0, "message":"success", "data":data, "requestId":request_id or new_id()}
def fail(status: int, message: str): raise HTTPException(status_code=status, detail=message)
