# NBA 新秀雙世代戰績追蹤中心 (NBA Dual-Class Rookie Tracker)

本專案提供 **去年新秀排行榜 (2025 梯固定新秀年戰績 vs. 目前二年生戰績對比)** 與 **今年新秀排行榜 (2026 梯即時戰績、有無 NBA 出賽紀錄分流)**，具備：
- **選秀順位標籤 (`#1` ~ `#36`)**
- **真實球員官方頭像 (`cdn.nba.com` + `Basketball-Reference` 雙 CDN 自動降級與球衣背號角標)**
- **繁體中文譯名與英文原名對照 (`backend/zh_name_mapper.py`)**
- **成績綜合評分 (`0 ~ 99.9` 加權指標，預設依綜合評分排序並篩選有在 NBA 出賽紀錄 `GP > 0` 的新秀)**
- **GitHub Pages + GitHub Actions 每日免費自動更新**

---

## 資料夾與模組結構

```text
nba-rookie-tracker/
├── index.html                           # 互動式戰情室前端 (包含雙世代排行榜、頭像渲染、CSV 匯出、架構藍圖)
├── data/
│   └── rookies_latest.json              # 每日自動更新之雙世代新秀戰績與成績綜合評分快照
├── backend/
│   ├── fetch_nba_data.py                # 模組 1 & 3：NBA API 數據爬蟲、有無出賽過濾與成績綜合評分計算引擎
│   └── zh_name_mapper.py                # 模組 2：繁體中文譯名、選秀順位、球衣背號與雙 CDN 頭像映射表
├── .github/
│   └── workflows/
│       └── daily_nba_sync.yml           # 模組 4：每日台灣時間 20:00 自動抓取並部署至 GitHub Pages
├── requirements.txt                     # Python 套件清單 (nba_api, pandas, requests)
└── README.md                            # 部署與客製化操作指南
```

---

## 3 分鐘快速部署至 GitHub Pages（每日免費自動更新）

### 步驟 1：建立 GitHub 儲存庫並上傳檔案
1. 登入 GitHub，點擊右上角 **`+` ➔ `New repository`**。
2. 儲存庫名稱輸入 `nba-rookie-tracker`，選擇 **Public**（公開儲存庫可享免費無限次 GitHub Pages 與 Actions 額度），直接建立。
3. 將本壓縮包解壓縮後的所有檔案（包含 `index.html`、`backend/`、`data/`、`.github/workflows/daily_nba_sync.yml`、`requirements.txt`）上傳並 Commit 至 `main` 分支。
   > **注意**：若使用網頁版拖曳上傳，請確保隱藏資料夾 `.github/workflows/daily_nba_sync.yml` 有一起上傳，或直接在 GitHub 介面點擊 `Add file` ➔ `Create new file`，輸入 `.github/workflows/daily_nba_sync.yml` 貼上內容。

### 步驟 2：開啟 GitHub Pages 與 Actions 讀寫權限
1. 進入儲存庫的 **`Settings` ➔ `Pages`**。
2. 在 **Build and deployment** 下方的 **Source** 選擇 **`GitHub Actions`**。
3. 進入 **`Settings` ➔ `Actions` ➔ `General`**，捲動至下方 **Workflow permissions**，確認勾選 **`Read and write permissions`** 並點擊 **Save**。

### 步驟 3：手動觸發第一次更新與部署
1. 點擊儲存庫頂端導覽列的 **`Actions`**。
2. 點選左側的 **`Daily NBA Rookie Data Sync & GitHub Pages Deploy`**。
3. 點擊右側 **`Run workflow` ➔ `Run workflow`**。
4. 等待約 40 秒執行完成後，即可在 **`Settings ➔ Pages`** 看到您的專屬網址：
   `https://<您的GitHub帳號>.github.io/nba-rookie-tracker/`
5. 之後每天台灣時間晚上 **20:00**（美國例行賽結束後），GitHub Actions 會自動執行 `backend/fetch_nba_data.py` 更新數據並重新發布網頁！
