"""Tencent SDK boundary. No implicit retry of chargeable submissions."""
import base64
import io
import json
import os
from PIL import Image, ImageOps

class ProviderError(Exception):
    def __init__(self,code,message,request_id=None,uncertain=False):
        super().__init__(message)
        self.code,self.request_id,self.uncertain=code,request_id,uncertain


def prepare_image(content):
    with Image.open(io.BytesIO(content)) as img:
        img.load()
        if img.format not in {'PNG','JPEG','WEBP'}: raise ValueError('仅支持 JPEG、PNG、WebP')
        # Normalize EXIF orientation and WebP to the same PNG used for coordinates.
        img=ImageOps.exif_transpose(img).convert('RGB')
        out=io.BytesIO(); img.save(out,format='PNG')
        data=out.getvalue(); size=img.size
    if len(base64.b64encode(data))>10_000_000: raise ValueError('转换后 Base64 超过 10MB，请缩小图片后重新上传')
    return data,size

class TencentMarkingProvider:
    def __init__(self,client=None):
        self._client=client

    def ensure_ready(self):
        if self._client is not None: return
        secret_id=os.getenv('TENCENTCLOUD_SECRET_ID','')
        secret_key=os.getenv('TENCENTCLOUD_SECRET_KEY','')
        if not secret_id or not secret_key:
            raise ProviderError('NotConfigured','请先开通腾讯云试题批改 Agent，并在后端配置腾讯云凭据')
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.ocr.v20181119.ocr_client import OcrClient
        except ImportError:
            raise ProviderError('MissingDependency','请安装 backend/requirements-marking.txt') from None
        profile=ClientProfile()
        profile.httpProfile=HttpProfile(endpoint='ocr.tencentcloudapi.com',reqTimeout=30)
        self._client=OcrClient(credential.Credential(secret_id,secret_key,os.getenv('TENCENTCLOUD_TOKEN')),os.getenv('TENCENTCLOUD_REGION','ap-guangzhou'),profile)

    def _call(self,action,params):
        self.ensure_ready()
        from tencentcloud.ocr.v20181119 import models
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
        request=getattr(models,action+'Request')(); request.from_json_string(json.dumps(params))
        try:
            return json.loads(getattr(self._client,action)(request).to_json_string())
        except TencentCloudSDKException as exc:
            code=exc.get_code() or 'ProviderError'
            # Preserve machine code/request ID, not vendor messages which may echo inputs.
            raise ProviderError(code,'腾讯云请求未完成，请根据错误码和 RequestId 排查',exc.get_request_id(),
                uncertain=code.startswith(('ClientNetworkError','InternalError')) or 'Timeout' in code) from None

    def submit(self,image,reference=None):
        params={'ImageBase64':base64.b64encode(image).decode('ascii'),
            'QuestionConfigMap':json.dumps({'KnowledgePoints':True,'TrueAnswer':True,'StepCorrection':True,'OutputSubQuestionsAndCoords':True})}
        if reference is not None:
            params.update({'AssistMarkType':2,'ImageBase64List':[base64.b64encode(reference).decode('ascii')]})
        return self._call('SubmitQuestionMarkAgentJob',params)

    def describe(self,job_id):
        return self._call('DescribeQuestionMarkAgentJob',{'JobId':job_id})
