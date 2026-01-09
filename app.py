import os
import sqlite3
import hashlib
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# -----------------------------
# Boot
# -----------------------------
load_dotenv()
st.set_page_config(page_title="RAG 專案管理後台（極簡版）", layout="wide")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def get_db_path() -> str:
    return os.getenv("RAG_DB_PATH", "rag_admin.db")

@st.cache_resource
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
      project_id TEXT PRIMARY KEY,
      project_name TEXT NOT NULL,
      vector_store_id TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS project_files (
      project_id TEXT NOT NULL,
      file_id TEXT NOT NULL,
      filename TEXT NOT NULL,
      sha256 TEXT,
      added_at TEXT NOT NULL,
      PRIMARY KEY (project_id, file_id),
      FOREIGN KEY (project_id) REFERENCES projects(project_id)
    );

    CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files(project_id);
    CREATE INDEX IF NOT EXISTS idx_project_files_sha256 ON project_files(sha256);
    """)
    conn.commit()

@st.cache_resource
def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("找不到 OPENAI_API_KEY。請在 .env 設定 OPENAI_API_KEY=xxx")
        st.stop()
    return OpenAI()

conn = get_conn()
init_db(conn)
client = get_client()

# -----------------------------
# DB helpers
# -----------------------------
def db_list_projects(active_only: bool = True) -> List[dict]:
    if active_only:
        cur = conn.execute("SELECT * FROM projects WHERE status='active' ORDER BY updated_at DESC")
    else:
        cur = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC")
    return [dict(r) for r in cur.fetchall()]

def db_create_project(name: str, vector_store_id: str) -> str:
    pid = str(uuid.uuid4())
    ts = now_iso()
    conn.execute("""
        INSERT INTO projects(project_id, project_name, vector_store_id, status, created_at, updated_at)
        VALUES(?,?,?,?,?,?)
    """, (pid, name, vector_store_id, "active", ts, ts))
    conn.commit()
    return pid

def db_rename_project(project_id: str, new_name: str):
    ts = now_iso()
    conn.execute("UPDATE projects SET project_name=?, updated_at=? WHERE project_id=?",
                 (new_name, ts, project_id))
    conn.commit()

def db_archive_project(project_id: str):
    ts = now_iso()
    conn.execute("UPDATE projects SET status='archived', updated_at=? WHERE project_id=?",
                 (ts, project_id))
    conn.commit()

def db_list_project_files(project_id: str) -> List[dict]:
    cur = conn.execute("""
        SELECT project_id, file_id, filename, sha256, added_at
        FROM project_files
        WHERE project_id=?
        ORDER BY added_at DESC
    """, (project_id,))
    return [dict(r) for r in cur.fetchall()]

def db_add_project_file(project_id: str, file_id: str, filename: str, sha256: Optional[str]):
    ts = now_iso()
    conn.execute("""
        INSERT OR REPLACE INTO project_files(project_id, file_id, filename, sha256, added_at)
        VALUES(?,?,?,?,?)
    """, (project_id, file_id, filename, sha256, ts))
    conn.commit()

def db_remove_project_file(project_id: str, file_id: str):
    conn.execute("DELETE FROM project_files WHERE project_id=? AND file_id=?",
                 (project_id, file_id))
    conn.commit()

def db_has_sha_in_project(project_id: str, sha: str) -> bool:
    cur = conn.execute("""
        SELECT 1 FROM project_files WHERE project_id=? AND sha256=? LIMIT 1
    """, (project_id, sha))
    return cur.fetchone() is not None

# -----------------------------
# Sidebar: project selection & CRUD
# -----------------------------
st.sidebar.title("專案管理（多專案）")

projects = db_list_projects(active_only=True)
label_to_pid: Dict[str, str] = {}
labels = ["（請選擇專案）"]
for p in projects:
    label = f"{p['project_name']} · {p['project_id'][:8]} · {p['vector_store_id']}"
    label_to_pid[label] = p["project_id"]
    labels.append(label)

if "selected_project_id" not in st.session_state:
    st.session_state.selected_project_id = None

selected_label = st.sidebar.selectbox("選擇專案", labels, index=0)
if selected_label == "（請選擇專案）":
    st.session_state.selected_project_id = None
else:
    st.session_state.selected_project_id = label_to_pid[selected_label]

with st.sidebar.expander("➕ 新增專案", expanded=False):
    new_name = st.text_input("專案名稱", value="Project-A-public")
    if st.button("建立專案（同時建立 Vector Store）"):
        try:
            vs = client.vector_stores.create(name=new_name.strip())
            pid = db_create_project(new_name.strip(), vs.id)
            st.success(f"已建立專案：{new_name} / VS={vs.id}")
            st.session_state.selected_project_id = pid
            st.rerun()
        except Exception as e:
            st.error(f"建立失敗：{e}")

with st.sidebar.expander("✏️ 專案改名 / 封存", expanded=False):
    pid = st.session_state.selected_project_id
    if not pid:
        st.info("先選一個專案")
    else:
        proj = [p for p in db_list_projects(active_only=False) if p["project_id"] == pid][0]
        rename_to = st.text_input("新名稱", value=proj["project_name"])
        if st.button("更新名稱"):
            db_rename_project(pid, rename_to.strip())
            st.success("已更新")
            st.rerun()

        st.divider()
        confirm = st.checkbox("我確認要封存此專案（不會刪 OpenAI Vector Store）")
        if st.button("封存專案", disabled=not confirm):
            db_archive_project(pid)
            st.success("已封存")
            st.session_state.selected_project_id = None
            st.rerun()

# -----------------------------
# Main
# -----------------------------
st.title("RAG 專案管理後台（極簡版：只存對應關係）")

pid = st.session_state.selected_project_id
if not pid:
    st.warning("請先在左側選擇或建立專案。")
    st.stop()

project = [p for p in db_list_projects(active_only=False) if p["project_id"] == pid][0]
vs_id = project["vector_store_id"]

st.subheader(f"目前專案：{project['project_name']}  |  VS: {vs_id}")

tab_upload, tab_list, tab_sync = st.tabs(["① 上傳 PDF 到專案", "② 專案檔案清單", "③ 同步校正（可選）"])

# -----------------------------
# Tab 1: upload -> files.create -> add to vector store -> record mapping
# -----------------------------
with tab_upload:
    st.markdown("### ① 上傳 PDF（需先選專案）")
    uploads = st.file_uploader("選擇 PDF（可多檔）", type=["pdf"], accept_multiple_files=True)

    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        st.caption("POC 建議：檔名包含版本號（例如 PRD_v1.2.pdf），避免引用混亂。")
        dedup = st.checkbox("同專案內若 sha256 相同則略過（避免重複）", value=True)

    with col2:
        do = st.button("🚀 上傳並加入 Vector Store（開始索引）", disabled=not uploads)

    if do:
        for uf in uploads:
            try:
                data = uf.getvalue()
                sha = sha256_bytes(data)

                if dedup and db_has_sha_in_project(pid, sha):
                    st.info(f"略過（同專案已存在相同內容）：{uf.name}")
                    continue

                # 1) upload to OpenAI Files
                f = client.files.create(file=(uf.name, data), purpose="assistants")

                # 2) add to vector store (index)
                client.vector_stores.file_batches.create(vector_store_id=vs_id, file_ids=[f.id])

                # 3) record mapping locally
                db_add_project_file(pid, f.id, uf.name, sha)

                st.success(f"✅ {uf.name} → file_id={f.id}（已加入索引）")
            except Exception as e:
                st.error(f"❌ {uf.name} 失敗：{e}")

# -----------------------------
# Tab 2: list project files from DB, remove from vector store + db
# -----------------------------
with tab_list:
    st.markdown("### ② 專案檔案清單（地端 mapping）")
    rows = db_list_project_files(pid)
    if not rows:
        st.info("此專案尚未加入任何檔案。")
    else:
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### 從專案移除檔案（不刪 OpenAI 全域檔案）")
    file_id = st.text_input("輸入要移除的 file_id", value="")
    confirm = st.checkbox("我確認要從此專案移除（仍可在其他專案使用）", value=False)

    if st.button("➖ 移除", disabled=(not file_id.strip() or not confirm)):
        try:
            # 注意：OpenAI 的 vector store 移除有兩種 API 物件表示
            # 這裡採用 vector_stores.files.delete( vector_store_id, file_id=... )
            client.vector_stores.files.delete(vector_store_id=vs_id, file_id=file_id.strip())
            db_remove_project_file(pid, file_id.strip())
            st.success("已從專案移除")
            st.rerun()
        except Exception as e:
            st.error(f"移除失敗：{e}")

# -----------------------------
# Tab 3: optional reconciliation (OpenAI list vs local mapping)
# -----------------------------
with tab_sync:
    st.markdown("### ③ 同步校正（可選）")
    st.caption("用途：避免手動操作造成 DB 與 OpenAI vector store 不一致。")

    if st.button("🔄 從 OpenAI 讀取 vector store 檔案並對帳"):
        try:
            # OpenAI: list files in vector store
            remote = client.vector_stores.files.list(vector_store_id=vs_id, limit=200).data
            remote_file_ids = set([r.file_id for r in remote])

            local = db_list_project_files(pid)
            local_file_ids = set([x["file_id"] for x in local])

            missing_in_remote = sorted(list(local_file_ids - remote_file_ids))
            missing_in_local = sorted(list(remote_file_ids - local_file_ids))

            colA, colB = st.columns(2)
            with colA:
                st.markdown("#### DB 有，但 OpenAI VS 沒有（疑似被移除）")
                st.write(missing_in_remote if missing_in_remote else "無")

            with colB:
                st.markdown("#### OpenAI VS 有，但 DB 沒有（疑似未登錄）")
                st.write(missing_in_local if missing_in_local else "無")

            # Optional: auto-fix DB from remote (only add missing_in_local)
            st.divider()
            if missing_in_local:
                st.warning("你可以選擇把『OpenAI 有但 DB 沒有』的檔案補回 DB（只補 mapping，不影響 OpenAI）。")
                if st.button("➕ 補回 DB mapping（用 file_id 當 filename）"):
                    for fid in missing_in_local:
                        db_add_project_file(pid, fid, filename=fid, sha256=None)
                    st.success("已補回 DB")
                    st.rerun()

        except Exception as e:
            st.error(f"同步失敗：{e}")
