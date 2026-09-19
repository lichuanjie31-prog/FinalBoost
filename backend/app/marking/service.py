"""Provider-agnostic marking service.

Every provider shares this code: ownership, idempotency, rate limiting, the
status machine, persistence, restart recovery and the listing API. A provider
only submits an image and returns a ProviderOutcome.

Two execution shapes are supported and the service keys off the provider's
`async_remote` flag rather than pretending they are the same:

* async_remote=True  (Tencent) — submit creates a remote job; get_result polls it.
* async_remote=False (Qwen)    — one synchronous call yields the finished result,
  so it runs on a worker thread and the job moves queued -> running -> terminal.
"""
import hashlib
import json
import time

from ..business import owned
from ..common import fail, new_id
from .base import ProviderError, ProviderOutcome, prepare_image

# A submission that never reported back is only declared unknown once this much
# time has passed without an answer from the vendor.
SUBMIT_GRACE_SECONDS = 60

TERMINAL = ('succeeded', 'failed', 'submission_unknown')


def provider_name(provider):
    """Doubles used in tests predate the `name` attribute; default to tencent."""
    return getattr(provider, 'name', 'tencent')


def provider_is_async(provider):
    return bool(getattr(provider, 'async_remote', True))


class ExamMarkingTool:
    def __init__(self, database, providers, settings, executor=None):
        self.db, self.providers, self.settings = database, providers, settings
        self.executor = executor

    # -- provider selection -------------------------------------------------
    def active(self):
        """The (mode, name, provider) the current configuration selects."""
        mode, name = self.settings.resolve_marking()
        provider = self.providers.get(name)
        if provider is None:
            raise ProviderError('NotConfigured', f'批改服务 {name} 不可用')
        return mode, name, provider

    def _provider_for(self, name):
        provider = self.providers.get(name)
        if provider is None:
            raise ProviderError('NotConfigured', f'该任务所属的批改服务 {name} 不可用')
        return provider

    # -- serialization ------------------------------------------------------
    def _output(self, row, include_raw=True):
        payload = {
            'jobId': row['id'], 'examId': row['exam_id'], 'status': row['status'],
            'source': row['provider'] or 'tencent', 'model': row['model'],
            'pageIndex': row['page_index'] or 0, 'providerJobId': row['provider_job_id'],
            'image': json.loads(row['image_json']),
            'result': json.loads(row['result_json']) if row['result_json'] else None,
            'error': json.loads(row['error_json']) if row['error_json'] else None,
            'requestId': row['request_id'], 'queryRequestId': row['query_request_id'],
            'usage': json.loads(row['usage_json']) if row['usage_json'] else None,
            'latencyMs': row['latency_ms'],
            'createdAt': row['created_at'],
            'retryAfterSeconds': self.settings.marking_submit_interval,
        }
        if include_raw and row['raw_json']:
            payload['raw'] = json.loads(row['raw_json'])
        return payload

    def readiness(self):
        mode, name, provider = self.active()
        state = provider.readiness()
        return {
            'ready': bool(state['configured']), 'mode': mode, 'provider': name,
            'model': state.get('model'), 'reason': state.get('reason'),
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

    def _persist_outcome(self, job_id, outcome, as_submission=False):
        """Write a ProviderOutcome onto the job row. States map one-to-one.

        A poll outcome carries no job id and no submit request id, so those are
        only ever written when the outcome actually supplies them — otherwise a
        routine poll would erase the remote id we still need to poll.
        """
        values = {
            'status': outcome.state if outcome.state in ('queued', 'running', 'succeeded', 'failed') else 'queued',
            'result_json': json.dumps(outcome.result, ensure_ascii=False) if outcome.result else None,
            # Cleared on success so a stale error never outlives the failure.
            'error_json': json.dumps(outcome.error, ensure_ascii=False) if outcome.error else None,
        }
        if outcome.raw is not None:
            values['raw_json'] = json.dumps(outcome.raw, ensure_ascii=False)
        if outcome.provider_job_id is not None:
            values['provider_job_id'] = outcome.provider_job_id
        if outcome.request_id is not None:
            values['request_id' if as_submission else 'query_request_id'] = outcome.request_id
        if outcome.usage is not None:
            values['usage_json'] = json.dumps(outcome.usage, ensure_ascii=False)
        if outcome.latency_ms is not None:
            values['latency_ms'] = outcome.latency_ms
        if outcome.model is not None:
            values['model'] = outcome.model
        self._update(job_id, **values)

    # -- submission ---------------------------------------------------------
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
        mode, name, provider = self.active()
        if mode == 'disabled':
            fail(503, '试卷批改尚未启用')
        if ref is not None and not provider_is_async(provider):
            # Silently ignoring an uploaded answer sheet would be worse than saying so.
            fail(422, '千问批改暂不支持参考答卷图片，请移除参考答卷后重试')
        # Refuse before anything chargeable happens, and never fall back to a
        # fabricated score when the provider is not configured.
        try:
            provider.ensure_ready()
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
                'image_json,page_index,provider,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (job_id, user_id, body.examId, body.fileId, body.requestKey, fingerprint, 'submitting',
                 json.dumps(metadata), body.pageIndex, name, now))
        image_dir = self.db.data_dir / 'marked-inputs'
        image_dir.mkdir(exist_ok=True)
        image_path = image_dir / (job_id + '.png')
        reference_path = None
        try:
            image_path.write_bytes(image)
            if reference is not None:
                reference_path = image_dir / (job_id + '.ref.png')
                reference_path.write_bytes(reference)
        except OSError:
            self._update(job_id, status='failed',
                         error_json=json.dumps({'code': 'StorageError', 'message': '图片保存失败，未调用批改服务'}))
            return self._output(self._row(job_id, user_id))

        if provider_is_async(provider):
            # The remote job is created inline: that call is fast and its id is
            # what makes polling and restart recovery possible.
            try:
                outcome = provider.submit(image, reference)
            except Exception as exc:
                self._record_submission_failure(job_id, exc)
            else:
                self._persist_outcome(job_id, outcome, as_submission=True)
        else:
            # A synchronous model call must not hold the HTTP request open, so it
            # is queued and handed to a worker. `submitting` stays reserved for the
            # async case, where it means "the vendor may or may not have accepted".
            self._update(job_id, status='queued')
            if self.executor is None:
                self._run_sync(job_id, name, image_path, reference_path)
            else:
                self.executor.submit(self._run_sync, job_id, name, image_path, reference_path)
        return self._output(self._row(job_id, user_id))

    def _record_submission_failure(self, job_id, exc):
        known = isinstance(exc, ProviderError) and not exc.uncertain
        error = {
            'code': str(exc.code) if isinstance(exc, ProviderError) else 'SubmissionUnknown',
            'message': str(exc) if isinstance(exc, ProviderError) else
            '提交结果未知，请勿自动重新提交。需核对供应商任务，避免重复计费。',
        }
        self._update(job_id, status='failed' if known else 'submission_unknown',
                     error_json=json.dumps(error, ensure_ascii=False),
                     request_id=exc.request_id if isinstance(exc, ProviderError) else None)

    def _run_sync(self, job_id, name, image_path, reference_path):
        """Worker body for a synchronous provider. Runs outside any transaction."""
        self._update(job_id, status='running')
        provider = self.providers.get(name)
        try:
            image = image_path.read_bytes()
            reference = reference_path.read_bytes() if reference_path else None
            outcome = provider.submit(image, reference)
        except ProviderError as exc:
            if exc.uncertain:
                # The model may have run and been billed; never auto-resubmit.
                self._update(job_id, status='submission_unknown',
                             error_json=json.dumps({'code': str(exc.code), 'message': str(exc)},
                                                   ensure_ascii=False),
                             request_id=exc.request_id)
            else:
                self._update(job_id, status='failed',
                             error_json=json.dumps({'code': str(exc.code), 'message': str(exc)},
                                                   ensure_ascii=False),
                             request_id=exc.request_id)
        except Exception:
            self._update(job_id, status='failed', error_json=json.dumps(
                {'code': 'ProviderError', 'message': '批改服务内部错误，未生成分数，请稍后重试'},
                ensure_ascii=False))
        else:
            # The single synchronous call is both the submission and the result.
            self._persist_outcome(job_id, outcome, as_submission=True)

    # -- polling ------------------------------------------------------------
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
            provider = self._provider_for(row['provider'] or 'tencent')
        except ProviderError as exc:
            self._update(job_id, error_json=json.dumps({'code': str(exc.code), 'message': str(exc)},
                                                       ensure_ascii=False))
            return self._output(self._row(job_id, user_id))
        if not provider_is_async(provider):
            # A synchronous job still queued/running here means its worker died
            # (typically a restart). It cannot be resumed, so say so plainly.
            if now - row['created_at'] > self.settings.qwen_marking_timeout + SUBMIT_GRACE_SECONDS:
                self._update(job_id, status='failed', error_json=json.dumps(
                    {'code': 'Interrupted', 'message': '批改中断且无法恢复，未生成分数，请重新提交该页'},
                    ensure_ascii=False))
            return self._output(self._row(job_id, user_id))
        try:
            outcome = provider.get_result(row['provider_job_id'])
        except Exception as exc:
            # A failed query only ever retries this same job; it never resubmits.
            self._update(job_id, error_json=json.dumps({
                'code': str(exc.code) if isinstance(exc, ProviderError) else 'QueryUnavailable',
                'message': '暂时无法查询批改结果，请稍后查询同一 jobId，不要重新提交'}),
                query_request_id=exc.request_id if isinstance(exc, ProviderError) else row['query_request_id'])
            return self._output(self._row(job_id, user_id))
        # The poll's request id lands in its own column, so the submit id survives.
        self._persist_outcome(job_id, outcome)
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
        row = self._row(job_id, user_id)
        path = self.db.data_dir / 'marked-inputs' / (row['id'] + '.png')
        if not path.is_file():
            fail(404, '批改原图不存在')
        return path

    # -- restart recovery ---------------------------------------------------
    def reconcile_interrupted(self):
        """Fail jobs that a restart left mid-flight.

        Only synchronous providers are affected: an async job still has a remote
        id we can keep polling, but an in-process model call is simply gone.
        """
        names = [name for name, provider in self.providers.items() if not provider_is_async(provider)]
        if not names:
            return 0
        placeholders = ','.join('?' * len(names))
        with self.db.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE marking_jobs SET status='failed', error_json=? "
                f"WHERE status IN ('submitting','queued','running') AND provider IN ({placeholders})",
                (json.dumps({'code': 'Interrupted',
                             'message': '服务重启导致本次批改中断，未生成分数，请重新提交该页'},
                            ensure_ascii=False), *names))
            return cursor.rowcount
