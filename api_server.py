import os
import sqlite3
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# -----------------------------
# Load env (.env)
# -----------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Please set it in .env or environment variables.")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DB_PATH = os.getenv("RAG_DB_PATH", "rag_admin.db")

# -----------------------------
# OpenAI client
# -----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(title="RAG Assistant API", version="0.1.0")


# -----------------------------
# DB helpers
# -----------------------------
def get_conn() -> sqlite3.Connection:
    """
    DB schema expectation (minimal):
      - projects(project_id TEXT, vector_store_id TEXT, status TEXT)
    """
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=500, detail=f"DB file not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_vector_store_id(project_id: str) -> str:
    """
    Lookup vector_store_id from local DB by project_id.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT vector_store_id FROM projects WHERE project_id=? AND status='active'",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"project_id not found or inactive: {project_id}")

    vs_id = row["vector_store_id"]
    if not vs_id:
        raise HTTPException(status_code=500, detail=f"vector_store_id is empty for project_id: {project_id}")
    return vs_id


# -----------------------------
# Request/Response models
# -----------------------------
class ChatReq(BaseModel):
    project_id: str
    user_id: str
    message: str


class ChatResp(BaseModel):
    answer: str
    citations: list[dict] = []  # POC: keep empty; later parse annotations for filenames/pages


# -----------------------------
# Prompt (instructions)
# -----------------------------
INSTRUCTIONS = """你是一個企業對外的「專案 AI 助理」。

語言規則：
- 一律使用繁體中文回答。

資料規則：
- 只能依據 file_search 檢索到的文件內容回答。
- 不可以臆測、杜撰或補充文件沒有提到的資訊。
- 若文件中沒有相關資訊，請明確回答「文件未提供」，並說明需要哪類文件才能回答。

引用規則：
- 每個重點/結論都必須附「引用」：至少要能指出是哪些文件（檔名）支持該結論。
- 若無法找到對應依據，請不要產生結論。

建議回答格式：
1) 重點結論，150字內
"""


# -----------------------------
# Endpoints
# -----------------------------
@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "model": OPENAI_MODEL,
        "db_path": DB_PATH,
    }


@app.post("/chat", response_model=ChatResp)
def chat(req: ChatReq) -> ChatResp:
    """
    Minimal RAG chat endpoint.
    - Reads vector_store_id from local DB by project_id
    - Calls Responses API with file_search tool bound to that vector store
    """
    vs_id = get_vector_store_id(req.project_id)

    try:
        # IMPORTANT:
        # Use the stable python-sdk-friendly format:
        # Put vector_store_ids directly inside the file_search tool object.
        resp = client.responses.create(
            model=OPENAI_MODEL,
            instructions=INSTRUCTIONS,
            input=req.message,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [vs_id],
                    # Optional knobs (uncomment if you want):
                    # "max_num_results": 8,
                }
            ],
            # POC: stateless. If you want memory later, we can add store/conversation.
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI call failed: {e}")

    answer = getattr(resp, "output_text", None) or ""

    # POC: citations empty for now.
    # Later: parse resp.output[*].content[*].annotations to extract filenames/pages.
    return ChatResp(answer=answer, citations=[])
