当前执行门槛：用户已要求先完成腾讯云高数独立能力验证。服务尚未开通，真实验证未进行。本计划的适配代码属于未验证草稿，暂停继续接入，按 docs/tencent-marking-validation.md 执行。

# Exam marking tool implementation plan

Goal: expose Tencent exam marking through authenticated FinalBoost APIs and a local stdio MCP server. Follow the confirmed design in this conversation. Credentials are not yet provisioned; live grading is an explicit follow-up verification.

Architecture: ExamMarkingTool owns resource authorization, persistent job state and deduplication. TencentMarkingProvider wraps the official SDK. The MCP bridge passes a trusted login token to the existing FastAPI application. First version submits one uploaded image per job and optionally one reference-answer image. It returns hierarchical annotations, never invented scores.

Tech stack: existing FastAPI, SQLite, Pillow; optional Tencent OCR SDK and pinned MCP v1 SDK.

## Tasks
- [ ] Write failing tests for nested annotations, empty results, authentication, ownership, deduplication, polling, failed submissions and no fabricated scores.
- [ ] Add provider.py, models.py, service.py and router.py under backend/app/marking; add migration 002_marking_jobs.sql and register the router.
- [ ] Reserve local jobs before external submission; call the provider outside database transactions; keep unknown submission outcomes to prevent automatic duplicate billing.
- [ ] Add backend/marking_mcp.py with submit_exam_marking and get_exam_marking. Credentials come from process environment and never from model arguments.
- [ ] Verify with offline provider fixtures and a real MCP stdio client. Run existing backend tests, export OpenAPI and regenerate frontend types.
- [ ] Document installation, service activation, environment settings, client setup and unresolved live validation. Do not commit or enable paid calls automatically.

## Acceptance
Authenticated users can submit their own uploaded image, retry a request key without resubmission, query their own persisted result after restart, and receive nested answers and quadrilateral coordinates. A timeout during submission never becomes a mock success. Empty results are rejected. Scores remain null. No real Tencent requests are made during offline tests. Original-image annotation UI is a later consumer of these returned coordinates.

