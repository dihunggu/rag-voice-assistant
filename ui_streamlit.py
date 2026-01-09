import os
import sqlite3
import requests
import streamlit as st
from dotenv import load_dotenv

# 新增引用: STT/TTS 工具模組
import stt_tts_utils

load_dotenv()
st.set_page_config(page_title="API 測試 UI（RAG 助理 + 語音）", layout="wide")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
DB_PATH = os.getenv("RAG_DB_PATH", "rag_admin.db")

# 初始化 Google Clients (Lazy load or at startup)
@st.cache_resource
def get_google_clients():
    try:
        return stt_tts_utils.init_google_clients()
    except Exception as e:
        st.error(f"Google Cloud 初始化失敗（將無法使用語音功能）: {e}")
        return None, None

speech_client, tts_client = get_google_clients()

@st.cache_resource
def get_openai_client():
    return stt_tts_utils.init_openai_client()

openai_client = get_openai_client()

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def list_projects():
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT project_id, project_name, vector_store_id FROM projects WHERE status='active' ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        # 如果你還沒用 DB，也可以改成手動輸入 project_id / vector_store_id
        return []

st.title("API 測試 (Text & Voice)")

with st.sidebar:
    st.header("設定")
    st.text_input("API Base", value=API_BASE, key="api_base")
    st.text_input("User ID（測試用）", value="test-user-001", key="user_id")

    projects = list_projects()
    if projects:
        labels = [f"{p['project_name']} · {p['project_id'][:8]}" for p in projects]
        idx = st.selectbox("選擇專案", range(len(labels)), format_func=lambda i: labels[i])
        project_id = projects[idx]["project_id"]
        st.caption(f"project_id: {project_id}")
        st.caption(f"vector_store_id: {projects[idx]['vector_store_id']}")
    else:
        st.warning("找不到 projects（若你沒用 DB：請改成手動輸入 project_id）")
        project_id = st.text_input("project_id", value="")
    
    st.divider()
    st.header("語音設定")
    stt_provider = st.selectbox("STT/TTS 服務商", ["Google", "OpenAI"], index=0)
    enable_voice_response = st.checkbox("啟用 AI 語音回應 (TTS)", value=True)
    voice_language = st.selectbox("STT/TTS 語言", ["zh-TW", "en-US"], index=0)

st.divider()

# Migrate history structure if needed (tuple -> dict)
if "history" not in st.session_state:
    st.session_state.history = []
else:
    # Quick fix for existing session state format compatibility
    new_history = []
    for item in st.session_state.history:
        if isinstance(item, tuple):
            new_history.append({"role": item[0], "content": item[1], "audio": None})
        elif isinstance(item, dict):
            new_history.append(item)
    st.session_state.history = new_history

# 顯示歷史
for msg in st.session_state.history:
    role = msg["role"]
    content = msg["content"]
    audio = msg.get("audio")
    
    with st.chat_message(role):
        st.markdown(content)
        if audio:
            st.audio(audio, format="audio/mp3")

# --------------------------
# 輸入區：支援 文字 (`st.chat_input`) 與 語音 (`st.audio_input`)
# --------------------------

# 1. 語音輸入
audio_prompt = None
if speech_client:
    # 這裡使用 st.audio_input (Streamlit 1.40+)
    # 若版本較舊可能會報錯，請 user 升級
    audio_wav = st.audio_input("🎤 按下錄音發問")
    if audio_wav:
        # 當有錄音時，進行 STT
        with st.spinner("語音辨識中..."):
            audio_bytes = audio_wav.getvalue()
            # 簡單做個 cache check 機制避免重複送出? 
            # Streamlit 每次 rerun 若 audio_wav 沒變，會重複 process?
            # 通常 st.audio_input 在錄製完後會觸發 rerun。
            # 為了避免同一段錄音重複觸發，可以在 session_state 記住上一次處理的 audio bytes
            
            # (這裡做個簡易判斷：計算 hash 或直接比對 bytes)
            # 但為了簡單，這裡先不做過度複雜的防呆，假設使用者錄完就是想問。
            # 不過 Streamlit 的 audio_input 會保留狀態，直到點叉叉。
            # 我們需要一個機制來判斷「這是新錄的」。
            pass # 後面邏輯處理

# 2. 文字輸入
text_prompt = st.chat_input("輸入問題（例如：請列出目前專案 Top 3 風險並附引用）")

final_prompt = None
is_voice_input = False

# 判斷邏輯
if text_prompt:
    final_prompt = text_prompt
elif speech_client and audio_wav:
    # 檢查是否已處理過這段音訊
    if "last_audio_bytes" not in st.session_state:
        st.session_state.last_audio_bytes = None
    
    current_audio_bytes = audio_wav.getvalue()
    if current_audio_bytes != st.session_state.last_audio_bytes:
        # 這是新的錄音 -> 執行 STT
        # 根據選擇的 Provider 傳入對應 Client
        # Google: speech_client, OpenAI: openai_client
        current_client = speech_client if stt_provider == "Google" else openai_client
        provider_code = stt_provider.lower()
        
        transcript = stt_tts_utils.speech_to_text(
            current_client, 
            current_audio_bytes, 
            provider=provider_code,
            language_code="cmn-Hant-TW" if voice_language=="zh-TW" else "en-US"
        )
        if transcript:
            final_prompt = transcript
            is_voice_input = True
            st.session_state.last_audio_bytes = current_audio_bytes
        else:
            st.warning("無法辨識語音，請重試。")
    else:
        # 雖然有 audio_wav，但跟上次一樣 -> 視為沒動作 (或使用者未清除)
        pass

if final_prompt:
    # 1. 顯示使用者問題
    st.session_state.history.append({"role": "user", "content": final_prompt, "audio": None})
    with st.chat_message("user"):
        st.markdown(final_prompt)

    # 2. 呼叫 RAG API
    payload = {
        "project_id": project_id,
        "message": final_prompt,
        "user_id": st.session_state.user_id
    }

    try:
        with st.chat_message("assistant"):
            with st.spinner("呼叫 API 中..."):
                r = requests.post(f"{st.session_state.api_base}/chat", json=payload, timeout=60)
                r.raise_for_status()
                data = r.json()

            answer = data.get("answer", "")
            citations = data.get("citations", [])

            st.markdown(answer if answer else "(無回覆)")

            if citations:
                st.markdown("#### 引用")
                for c in citations:
                    filename = c.get("filename", "(unknown)")
                    page = c.get("page")
                    quote = c.get("quote")
                    line = f"- {filename}"
                    if page is not None:
                        line += f"（p.{page}）"
                    st.markdown(line)
                    if quote:
                        st.caption(quote)

            # 3. TTS (若啟用)
            tts_audio = None
            if enable_voice_response and answer:
                # 根據 Provider 選擇 Client
                # Google: tts_client, OpenAI: openai_client
                current_client = tts_client if stt_provider == "Google" else openai_client
                provider_code = stt_provider.lower()
                
                # 若 client 存在才執行
                if current_client:
                    with st.spinner("生成語音中..."):
                        tts_audio = stt_tts_utils.text_to_speech(
                            current_client, 
                            answer, 
                            provider=provider_code, 
                            language_code=voice_language
                        )
                        if tts_audio:
                            st.audio(tts_audio, format="audio/mp3")

            st.session_state.history.append({
                "role": "assistant", 
                "content": answer if answer else "(無回覆)",
                "audio": tts_audio
            })

    except Exception as e:
        err = f"API 呼叫失敗：{e}"
        with st.chat_message("assistant"):
            st.error(err)
        st.session_state.history.append({"role": "assistant", "content": err, "audio": None})

