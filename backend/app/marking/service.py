"""Reusable Agent tool; identity must come from trusted authentication."""
import hashlib
import json
import time
from ..business import owned
from ..common import fail, new_id
from .models import normalize_result
from .provider import ProviderError, prepare_image

# A submission that never reported back is only declared unknown once this much
# time has passed without an answer from the vendor.
SUBMIT_GRACE_SECONDS = 60


class ExamMarkingTool:
    def __init__(self, database, provider, settings):
        self.db, self.provider, self.settings = database, provider, settings

    def _output(self, row, include_raw=True):
        payload = {
            'jobId': row['id'], 'examId': row['exam_id'], 'status': row['status'], 'source': 'tencent',
            'pageIndex': row['page_index'] or 0, 'providerJobId': row['provider_job_id'],
            'image': json.loads(row['image_json']),
            'result': json.loads(row['result_json']) if row['result_json'] else None,
            'error': json.loads(row['error_json']) if row['error_json'] else None,
            'requestId': row['request_id'], 'queryRequestId': row['query_request_id'],
            'createdAt': row['created_at'],
            'retryAfterSeconds': self.settings.marking_submit_interval,
        }
        if include_raw and row['raw_json']:
            payload['raw'] = json.loads(row['raw_json'])
        return payload

    def readiness(self):
        state = self.provider.readiness()
        return {
            'ready': bool(state['configured']), 'mode': state['mode'], 'reason': state.get('reason'),
            'message': state['message'], 'region': state.get('region'),
            'submitIntervalSeconds': self.settings.marking_submit_interval,
        }

    def _row(self, job_id, user_id):
        with self.db.transaction() as conn:
            return dict(owned(conn, 'marking_jobs', job_id, user_id))

    def _update(self, job_id, **values):
        # Only internal callers supply column names.
        with self.db.transaction() as conn:
            conn.execute('UPDATE marking_jobs SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?',
                         (*values.values(), job_id))

    def submit(self, user_id, body):
        fingerprint = hashlib.sha256(body.model_dump_json(exclude={'requestKey'}).encode()).hexdigest()
        with self.db.transaction() as conn:
            owned(conn, 'exams', body.examId, user_id)
            file = dict(owned(conn, 'files', body.fileId, user_id))
            ref = dict(owned(conn, 'files', body.referenceFileId, user_id)) if body.referenceFileId else None
            existing = conn.execute('SELECT * FROM marking_jobs WHERE user_id=? AND request_key=?',
                                    (user_id, body.requestKey)).fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    fail(409, '同一 requestKey 已用于另一份批改请求')
                return self._output(existing)
        # Refuse before anything chargeable happens, and never fall back to a
        # fabricated score when the vendor is not configured.
        if hasattr(self.provider, 'ensure_ready'):
            try:
                self.provider.ensure_ready()
            except ProviderError as exc:
                fail(503, str(exc))
        try:
            image, size = prepare_image((self.db.data_dir / 'uploads' / file['storage_key']).read_bytes())
            reference = prepare_image((self.db.data_dir / 'uploads' / ref['storage_key']).read_bytes())[0] if ref else None
        except (OSError, ValueError):
            fail(422, '图片不可读取或超过批改接口限制，请检查文件后重试')
        job_id = new_id()
        now = time.time()
        metadata = {'fileId': body.fileId, 'width': size[0], 'height': size[1],
                    'url': f'/api/v1/marking/jobs/{job_id}/image', 'mimeType': 'image/png',
                    'orientation': 'exif_normalized'}
        with self.db.transaction() as conn:
            # Recheck under the reservation transaction for concurrent duplicates.
            existing = conn.execute('SELECT * FROM marking_jobs WHERE user_id=? AND request_key=?',
                                    (user_id, body.requestKey)).fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    fail(409, 'requestKey 冲突')
                return self._output(existing)
            # Vendor allowance is ten submitted images per minute.
            if conn.execute('SELECT 1 FROM marking_jobs WHERE created_at>? LIMIT 1',
                            (now - self.settings.marking_submit_interval,)).fetchone():
                fail(429, f'批改提交频率受限，请等待至少 {self.settings.marking_submit_interval:g} 秒后重试')
            conn.execute(
                'INSERT INTO marking_jobs(id,user_id,exam_id,file_id,request_key,fingerprint,status,'
                'image_json,page_index,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                (job_id, user_id, body.examId, body.fileId, body.requestKey, fingerprint, 'submitting',
                 json.dumps(metadata), body.pageIndex, now))
        image_dir = self.db.data_dir / 'marked-inputs'
        image_dir.mkdir(exist_ok=True)
        try:
            (image_dir / (job_id + '.png')).write_bytes(image)
        except OSError:
            self._update(job_id, status='failed',
                         error_json=json.dumps({'code': 'StorageError', 'message': '图片保存失败，未调用批改服务'}))
            return self._output(self._row(job_id, user_id))
        try:
            response = self.provider.submit(image, reference)
            remote_id = response.get('JobId')
            if not isinstance(remote_id, str) or not remote_id:
                raise ValueError('missing job ID')
            self._update(job_id, status='queued', provider_job_id=remote_id,
                         request_id=response.get('RequestId'))
        except Exception as exc:
            known = isinstance(exc, ProviderError) and not exc.uncertain
            error = {
                'code': str(exc.code) if isinstance(exc, ProviderError) else 'SubmissionUnknown',
                'message': str(exc) if isinstance(exc, ProviderError) else
                '提交结果未知，请勿自动重新提交。需核对供应商任务，避免重复计费。',
            }
            self._update(job_id, status='failed' if known else 'submission_unknown',
                         error_json=json.dumps(error, ensure_ascii=False),
                         request_id=exc.request_id if isinstance(exc, ProviderError) else None)
        return self._output(self._row(job_id, user_id))

    def get(self, user_id, job_id):
        now = time.time()
        with self.db.transaction() as conn:
            row = dict(owned(conn, 'marking_jobs', job_id, user_id))
            if row['status'] == 'submitting' and now - row['created_at'] > SUBMIT_GRACE_SECONDS:
                conn.execute("UPDATE marking_jobs SET status='submission_unknown',error_json=? WHERE id=?",
                             (json.dumps({'code': 'SubmissionUnknown', 'message': '提交结果未知，请勿自动重复提交'}), job_id))
                row = dict(conn.execute('SELECT * FROM marking_jobs WHERE id=?', (job_id,)).fetchone())
            if row['status'] not in ('queued', 'running'):
                return self._output(row)
            # Query pacing, persisted across restarts and multiple clients.
            last = conn.execute('SELECT MAX(last_poll) FROM marking_jobs').fetchone()[0] or 0
            if now - last < self.settings.marking_poll_interval:
                return self._output(row)
            conn.execute('UPDATE marking_jobs SET last_poll=? WHERE id=?', (now, job_id))
        try:
            raw = self.provider.describe(row['provider_job_id'])
        except Exception as exc:
            # A failed query only ever retries this same job; it never resubmits.
            self._update(job_id, error_json=json.dumps({
                'code': str(exc.code) if isinstance(exc, ProviderError) else 'QueryUnavailable',
                'message': '暂时无法查询批改结果，请稍后查询同一 jobId，不要重新提交'}),
                query_request_id=exc.request_id if isinstance(exc, ProviderError) else row['query_request_id'])
            return self._output(self._row(job_id, user_id))
        status = raw.get('JobStatus')
        result = None
        error = None
        if status == 'DONE':
            try:
                result = normalize_result(raw)
                local = 'succeeded'
            except (ValueError, TypeError, AttributeError):
                local = 'failed'
                error = {'code': 'InvalidProviderResult', 'message': '批改结果不完整，未生成分数，请人工核对'}
        elif status == 'FAIL':
            local = 'failed'
            error = {'code': str(raw.get('ErrorCode') or 'ProviderFailed'),
                     'message': str(raw.get('ErrorMessage') or '腾讯云批改失败，请按错误码和 RequestId 排查')}
        elif status in ('WAIT', 'RUN'):
            local = {'WAIT': 'queued', 'RUN': 'running'}[status]
        else:
            local = 'failed'
            error = {'code': 'InvalidProviderStatus', 'message': '供应商返回未知状态'}
        self._update(job_id, status=local,
                     result_json=json.dumps(result, ensure_ascii=False) if result else None,
                     raw_json=json.dumps(raw, ensure_ascii=False),
                     error_json=json.dumps(error, ensure_ascii=False) if error else None,
                     query_request_id=raw.get('RequestId'))
        return self._output(self._row(job_id, user_id))

    def list_by_exam(self, user_id, exam_id, cursor=None, limit=50):
        with self.db.transaction() as conn:
            owned(conn, 'exams', exam_id, user_id)
            rows = conn.execute(
                'SELECT * FROM marking_jobs WHERE exam_id=? AND user_id=? AND id>? '
                'ORDER BY page_index, id LIMIT ?', (exam_id, user_id, cursor or '', limit + 1)).fetchall()
        return {'items': [self._output(row, include_raw=False) for row in rows[:limit]],
                'nextCursor': rows[limit - 1]['id'] if len(rows) > limit else None}

    def image_path(self, user_id, job_id):
        self._row(job_id, user_id)
        path = self.db.data_dir / 'marked-inputs' / (job_id + '.png')
        if not path.is_file():
            fail(404, '批改原图不存在')
        return path
