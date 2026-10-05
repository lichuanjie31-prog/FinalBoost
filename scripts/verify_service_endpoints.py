"""验证 DuMate 相关新增端点的连通性（服务级 Token）。

前置：后端已启动，且已设置环境变量 SERVICE_TOKEN。

用法（Windows PowerShell）：
    $env:SERVICE_TOKEN="<你的服务级Token>"
    backend\\.venv\\Scripts\\python.exe scripts\\verify_service_endpoints.py

用法（Linux / macOS）：
    SERVICE_TOKEN=<你的服务级Token> python scripts/verify_service_endpoints.py

可选：BASE_URL 覆盖默认地址（默认 http://127.0.0.1:8000）。
仅用标准库，无需安装 requests。
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
TOKEN = os.environ.get("SERVICE_TOKEN", "")

VISION_JSON = {
    "subject": "数学",
    "questions": [
        {"question_text": "求 f(x)=x^2 的导数", "student_answer": "2x",
         "correct_answer": "2x", "judgement": "correct", "analysis": "按幂函数求导",
         "knowledge_points": ["导数计算"], "confidence": 0.95, "question_type": "解答题"},
        {"question_text": "判断 f(x)=1/x 的单调性", "student_answer": "在 R 上单调递增",
         "correct_answer": "在 (0,+∞) 与 (-∞,0) 上分别单调递减", "judgement": "incorrect",
         "analysis": "忽略定义域分段", "error_reason": "未考虑定义域",
         "knowledge_points": ["函数单调性"], "confidence": 0.8, "question_type": "解答题"},
    ],
}

PAPER = {
    "title": "函数单调性 专项突破",
    "course": "数学",
    "sections": [
        {"knowledgePoint": "函数单调性",
         "questions": [
             {"stem": "讨论 f(x)=x+1/x 的单调区间", "type": "解答题",
              "answer": "在 (0,1) 递减，(1,+∞) 递增", "analysis": "求导后看符号"},
             {"stem": "下列函数在 (0,+∞) 上单调递增的是", "type": "选择题",
              "options": [{"key": "A", "text": "y=1/x"}, {"key": "B", "text": "y=x^2"}],
              "answer": "B", "analysis": "幂函数性质"},
         ]},
    ],
    "includeAnswers": True,
    "includeAnalysis": True,
}


def post(path, payload, want_bytes=False):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Service-Token": TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        print(f"  HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}")
        raise
    return raw if want_bytes else json.loads(raw.decode("utf-8"))


def main():
    if not TOKEN:
        print("缺少 SERVICE_TOKEN 环境变量：端点会返回 503，无法验证。")
        return 2

    print(f"BASE_URL = {BASE}")

    print("\n[1/3] POST /api/v1/marking/normalize")
    data = post("/api/v1/marking/normalize", VISION_JSON)["data"]
    questions = data["questions"]
    print(f"  questions={len(questions)}  scoreStatus={data['scoreStatus']}  totalScore={data['totalScore']}")
    correct = questions[1]["answers"][0]["correct"]
    print(f"  第 2 题 correct={correct}（预期 False）")
    assert data["totalScore"] is None, "totalScore 必须为 null（无评分细则不给分）"
    assert correct is False, "错题判定未生效"

    print("\n[2/3] POST /api/v1/analysis/weak-points")
    data = post("/api/v1/analysis/weak-points", {"questions": questions})["data"]
    print(f"  weakPoints={json.dumps(data['weakPoints'], ensure_ascii=False)}")
    assert any(item["knowledgePoint"] == "函数单调性" for item in data["weakPoints"]), "薄弱点未识别"

    print("\n[3/3] POST /api/v1/materials/pdf")
    pdf = post("/api/v1/materials/pdf", PAPER, want_bytes=True)
    print(f"  bytes={len(pdf)}  header={pdf[:5]!r}")
    assert pdf[:4] == b"%PDF", "返回的不是 PDF"

    print("\n全部通过：三个新增端点均连通。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
