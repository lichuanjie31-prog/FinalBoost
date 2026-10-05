"""DuMate 智能体调用云端 FastAPI 的服务级 Token 校验。

放在 app/ 下，与 common.fail 的失败契约保持一致：未配置 503、Token 不匹配 401。
"""
import hmac
import os

from fastapi import Header

from .common import fail


def service_token_guard(x_service_token: str = Header(default='', alias='X-Service-Token')):
    """校验 X-Service-Token 头。每次请求读取环境变量，便于热更新与轮换。"""
    expected = os.environ.get('SERVICE_TOKEN', '')
    if not expected:
        fail(503, '服务级 Token 未配置')
    if not hmac.compare_digest(x_service_token.encode(), expected.encode()):
        fail(401, '无效的服务级 Token')
    return {'id': 'service', 'username': 'dumate-agent'}
