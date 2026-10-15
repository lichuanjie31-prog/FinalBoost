# 三题检验流程更新与验收

## 本次流程

自评达到7分后准备当前原题的三道变式，以实际作答检验掌握情况。三题分别为同构运用、逆向推理和一步拓展；全部核验正确后再进入下一道原题。辅助角、凑角求值固定围绕第17题(1)，不扩展到其他小问。

优先调用现有 `generate_practice_pdf` 原题模式。工具总数仍为6，既有 sections、别名、base64 调用保留。

```json
{
  "sourceQuestion": "第17题(1)：f(t)=sin(t)cos(t)+sqrt(3)/2*cos(2t)，f(x/2-pi/12)=3/5，pi/3<x<5pi/6，求cos(x)。",
  "sourceKnowledgePoint": "辅助角公式与凑角求值",
  "includeAnswers": false,
  "includeAnalysis": false,
  "delivery": "download"
}
```

此题型由可独立验算的生成器准备三题，无外部模型调用。其他题型使用三请求并发生成，单请求最多20秒，关闭SDK自动重试；最多三轮质量修正受统一预算限制。题数不足、pending或failed不交付整组。

服务端原题到PDF总预算145秒；下载CLI整段15秒截止，覆盖DNS、连接与慢流。DuMate的规划、附件保存和平台调度仍需在线验收，不能把本地服务计时等同于线上整段延迟。

## 更新运行环境

1. 将本次后端提交部署到实际MCP服务，安装锁定依赖并重启既有服务。仅推送仓库不会重启线上MCP。
2. 配置 `MATERIAL_PUBLIC_BASE_URL` 为DuMate实际可访问的HTTPS服务源站，例如现有 `https://dumate.codehive.asia`。代理需允许 `/api/v1/materials/artifacts/` 路径。
3. 可用 `MATERIAL_ARTIFACT_DIR` 指定持久、可写的临时题卷目录。所有服务进程必须访问同一目录。默认使用系统临时目录。
4. 题卷能力链接有效15分钟，使用不可猜测token，仅授予单份文件读取权限。链接与工具元数据应按学生资料处理，不公开转发。定时链接只包含本次生成题目，无模型凭据。
5. 将 `.agents/skills/paper-boost-assistant/` 整个目录重新导入DuMate，包含 `SKILL.md` 和 `scripts/download_practice_pdf.py`。只更新提示词会丢失下载校验脚本。
6. 刷新DuMate的MCP工具发现，确认 `generate_practice_pdf` 能看到 `sourceQuestion`、`sourceKnowledgePoint`、`delivery` 三个新增参数。

## 真实文件交付

download模式返回 downloadUrl、sha256、sizeBytes、questionCount、expiresAt。将返回JSON原样保存，再运行随Skill提供的脚本：

```text
python <Skill目录>/scripts/download_practice_pdf.py metadata.json 新练习卷.pdf
```

脚本下载原始字节、校验三题数量与SHA，超时会终止子进程；失败不写最终PDF，不覆盖已有不同文件。禁止让模型手抄base64、修改PDF内容流或把文本文件改扩展名交付。

服务端在生成后解码每页内容流，提取并核对全部题干，空题或损坏流不会返回成功。渲染采用Flate流，避免已反馈损坏文件的ASCII85编码形式。

## 在线验收

- 自评8分后直接准备三题，不先叠加额外一道微型题，不提前宣称掌握。
- 三题全部针对当前题的同一方法，条件充分、符号区间完整；学生卷隐藏答案。
- 从学生回复自评分到真实附件就绪记录完整耗时，应在180秒内。若只测本地后端，明确标注范围。
- 下载后检查每道题可见；三题答案经check_answer全部correct后才通关。错误或uncertain保留原始作答，不改写成参考答案。
- 复盘卷复用已完成的三题，答案解析独立分页，不再次调用生成器。
- 超时、存储满或不可用时保留标准MCP错误，不重复整链调用，不交付空白PDF。
