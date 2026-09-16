import hashlib
import hmac
import secrets
import sqlite3
import time
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .schemas import Credentials, Envelope, AuthOut, UserOut
from .common import envelope, fail, new_id

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64*1024*1024)
    return f"scrypt${salt}${derived.hex()}"

def origin_guard(request: Request):
    if request.headers.get("x-requested-with") != "FinalBoost": fail(403, "请求来源校验失败")
    origin = request.headers.get("origin")
    if origin and origin not in request.app.state.settings.origins: fail(403, "请求来源不受信任")

def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    if not credentials: fail(401, "请先登录账号")
    with request.app.state.db.transaction() as db:
        row = db.execute("SELECT u.id,u.username,s.id AS session_id FROM access_tokens a JOIN sessions s ON s.id=a.session_id JOIN users u ON u.id=s.user_id WHERE a.digest=? AND a.expires_at>? AND s.expires_at>? AND s.revoked=0", (digest(credentials.credentials),time.time(),time.time())).fetchone()
    if row is None: fail(401, "登录已过期，请重新登录")
    return dict(row)

def issue(db, user, settings, response, session_id=None):
    sid = session_id or new_id()
    if session_id is None: db.execute("INSERT INTO sessions VALUES (?,?,?,0)", (sid,user["id"],time.time()+settings.refresh_seconds))
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute("INSERT INTO access_tokens VALUES (?,?,?)", (digest(access),sid,time.time()+settings.access_seconds))
    db.execute("INSERT INTO refresh_tokens VALUES (?,?,0)", (digest(refresh),sid))
    expires = db.execute("SELECT expires_at FROM sessions WHERE id=?",(sid,)).fetchone()[0]
    response.set_cookie("fb_refresh", refresh, httponly=True, secure=settings.secure_cookie, samesite="strict", path="/api/v1/auth", max_age=max(1,int(expires-time.time())))
    response.headers["Cache-Control"] = "no-store"
    return envelope({"accessToken":access,"expiresIn":settings.access_seconds,"user":{"userId":user["id"],"username":user["username"]}})

@router.post("/register", response_model=Envelope[AuthOut], status_code=201, dependencies=[Depends(origin_guard)])
def register(body: Credentials, request: Request, response: Response):
    user = {"id":new_id(),"username":body.username}
    encoded = hash_password(body.password)
    with request.app.state.db.transaction() as db:
        try: db.execute("INSERT INTO users VALUES (?,?,?,?)", (user["id"],body.username,encoded,time.time()))
        except sqlite3.IntegrityError: fail(409, "这个用户名已被使用，请换一个或直接登录")
        return issue(db,user,request.app.state.settings,response)

@router.post("/login", response_model=Envelope[AuthOut], dependencies=[Depends(origin_guard)])
def login(body: Credentials, request: Request, response: Response):
    with request.app.state.db.transaction() as db: user = db.execute("SELECT * FROM users WHERE username=?",(body.username,)).fetchone()
    salt = user["password_hash"].split("$")[1] if user else "00"*16
    candidate = hash_password(body.password,salt)
    if user is None or not hmac.compare_digest(candidate,user["password_hash"]): fail(401,"用户名或密码不正确")
    with request.app.state.db.transaction() as db: return issue(db,user,request.app.state.settings,response)

@router.post("/refresh", response_model=Envelope[AuthOut], dependencies=[Depends(origin_guard)])
def refresh(request: Request, response: Response):
    token = request.cookies.get("fb_refresh")
    if not token: fail(401,"请登录账号")
    invalid = False
    with request.app.state.db.transaction() as db:
        row = db.execute("SELECT r.used,s.id AS session_id,s.revoked,s.expires_at,u.id,u.username FROM refresh_tokens r JOIN sessions s ON s.id=r.session_id JOIN users u ON u.id=s.user_id WHERE r.digest=?",(digest(token),)).fetchone()
        if row is None or row["revoked"] or row["expires_at"] <= time.time(): invalid = True
        elif row["used"]:
            db.execute("UPDATE sessions SET revoked=1 WHERE id=?",(row["session_id"],))
            invalid = True
        else:
            db.execute("UPDATE refresh_tokens SET used=1 WHERE digest=?",(digest(token),))
            result = issue(db,row,request.app.state.settings,response,row["session_id"])
    if invalid: fail(401,"登录已过期，请重新登录")
    return result

@router.post("/logout", response_model=Envelope[None], dependencies=[Depends(origin_guard)])
def logout(request: Request, response: Response):
    token = request.cookies.get("fb_refresh")
    authorization = request.headers.get("authorization", "")
    with request.app.state.db.transaction() as db:
        if token: db.execute("UPDATE sessions SET revoked=1 WHERE id IN (SELECT session_id FROM refresh_tokens WHERE digest=?)", (digest(token),))
        if authorization.startswith("Bearer "): db.execute("UPDATE sessions SET revoked=1 WHERE id IN (SELECT session_id FROM access_tokens WHERE digest=?)", (digest(authorization[7:]),))
    response.delete_cookie("fb_refresh", path="/api/v1/auth", httponly=True, samesite="strict", secure=request.app.state.settings.secure_cookie)
    response.headers["Cache-Control"] = "no-store"
    return envelope(None)

@router.get("/me", response_model=Envelope[UserOut])
def me(user=Depends(current_user)): return envelope({"userId":user["id"],"username":user["username"]})
