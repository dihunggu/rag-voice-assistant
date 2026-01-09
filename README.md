# 支援語音互動的 RAG AI 助理 (RAG AI Assistant with Voice Interaction)

這是一個 RAG (檢索增強生成) AI 助理專案，支援上傳 PDF 文件以建立知識庫。本專案提供 Streamlit 使用者介面，並支援文字與語音 (STT/TTS) 互動功能。

![App Preview](page.png)

## 功能特色

-   **RAG 核心**：上傳 PDF 文件以建立知識庫（使用 OpenAI Vector Stores）。
-   **對話介面**：根據上傳的文件內容進行問答。
-   **語音互動**：
    -   **語音轉文字 (STT)**：使用麥克風直接提問。
    -   **文字轉語音 (TTS)**：聆聽 AI 的語音回覆。
    -   **多服務商支援**：可切換使用 **Google Cloud** 或 **OpenAI** 的語音服務。

## 前置需求

1.  **Python 3.8+**
2.  **OpenAI API Key**：請在 `.env` 中設定 `OPENAI_API_KEY`。
3.  **Google Cloud 服務帳號（選用）**：
    -   若要使用 Google STT/TTS 則為必須。
    -   請將您的 `gcp-sa.json` 金鑰檔放在此專案目錄下。
    -   請至 Google Cloud Console 啟用 "Cloud Speech-to-Text API" 與 "Cloud Text-to-Speech API"。

## 安裝說明

1.  安裝相依套件：
    ```bash
    pip install -r requirements.txt
    pip install google-cloud-speech google-cloud-texttospeech pydub openai watchdog
    ```
    *（註：建議安裝 `watchdog` 以支援 uvicorn 自動重載）*

2.  建立 `.env` 檔案：
    ```env
    OPENAI_API_KEY=sk-proj-...
    API_BASE=http://127.0.0.1:8000
    RAG_DB_PATH=rag_admin.db
    # 若目錄下存在 gcp-sa.json，程式會自動設定 GOOGLE_APPLICATION_CREDENTIALS
    ```

## 使用說明

### 1. 啟動後端 API
後端負責處理 RAG 邏輯與資料庫連線。
開啟終端機並執行：
```powershell
uvicorn api_server:app --reload
```
*預設連接埠為 8000。*

### 2. 啟動前端 UI
前端提供對話介面與語音控制功能。
開啟 **另一個** 終端機並執行：
```powershell
streamlit run ui_streamlit.py
```

### 3. 開始使用
-   **專案管理**：使用側邊欄建立專案並上傳 PDF 檔案。
-   **語音設定**：
    -   在側邊欄找到 "語音設定"。
    -   **STT/TTS 服務商**：選擇 "Google" 或 "OpenAI"。
    -   **語言**：選擇 "zh-TW"（中文）或 "en-US"（英文）。
-   **對話**：
    -   在文字框輸入問題。
    -   或點擊 **麥克風** 圖示 (`st.audio_input`) 用說的。

## 疑難排解 (Troubleshooting)

-   **API Error 404**：確認 `api_server.py` 是否已在 port 8000 執行中。
-   **Google STT/TTS 無法使用**：檢查 `gcp-sa.json` 是否存在，且已啟用相關 Google Cloud API。
-   **麥克風無法使用**：檢查瀏覽器的麥克風權限設定。
