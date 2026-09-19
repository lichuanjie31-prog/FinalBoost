"""测试隔离：不继承开发者 backend/.env 里的真实凭据。

`app.main` 在导入时执行 `load_dotenv()`，而 load_dotenv 不会覆盖已存在的环境变量，
所以在应用被导入之前把这些凭据置空，用例就始终离线且确定 —— 否则一旦开发者配好
真实 Key，整套测试会真的去调外部模型（更慢、要花钱，而且密钥过期时会假失败）。

需要真实模式的用例仍可显式开启：
`create_app(llm_api_key=...)` / `client_for(..., marking_mode='fixture', dashscope_api_key=...)`。
"""
import os

os.environ["LLM_API_KEY"] = ""
os.environ["DASHSCOPE_API_KEY"] = ""
os.environ["TENCENTCLOUD_SECRET_ID"] = ""
os.environ["TENCENTCLOUD_SECRET_KEY"] = ""
os.environ["TENCENTCLOUD_TOKEN"] = ""
# 批改默认关闭；需要批改的用例都会显式传 marking_mode
os.environ["MARKING_MODE"] = "disabled"
