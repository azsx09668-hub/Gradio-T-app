# 🏙️ 台南市開放資料瀏覽器 (PWA + RWD)

使用 [Gradio](https://www.gradio.app/) + FastAPI 打造的互動式網頁:即時下載台南市政府資料開放平台的 CSV,
提供搜尋、篩選、欄位摘要、統計圖與 CSV 匯出。支援**安裝成手機 / 桌面 App**,並針對**手機、平板、桌機**自動調整版面。

## 功能

- 📋 **資料表**:關鍵字搜尋所有欄位、選擇顯示欄位、可選擇刪除含空值的列、匯出目前結果
- 🧮 **欄位摘要**:各欄位型別、缺值數與比例、不重複值數
- 📊 **統計圖**:任選欄位,顯示出現次數最多的前 15 項
- ⚡ **資料快取**:預設 10 分鐘內不重複下載;下載失敗時沿用舊資料

### PWA

- 提供 `manifest.webmanifest`,可「加入主畫面 / 安裝」(Android、桌面 Chrome / Edge、iOS Safari)
- Service Worker 快取靜態資源,加快二次載入
- 離線時顯示專屬離線頁面,並有「離線 / 已恢復連線」提示
- 標題下方的「📲 安裝到桌面」按鈕:瀏覽器支援時一鍵安裝;不支援時彈出該瀏覽器的操作教學
- 已安裝並以 App 視窗開啟時,安裝按鈕會自動隱藏

> ⚠️ 資料每次都要即時下載,所以 **離線時無法查詢資料**。PWA 在這裡的價值是「可安裝、載入快、體驗像 App」,而不是離線使用。

### RWD

- 統計卡片:桌機 4 欄 → 平板 2×2 → 手機緊湊排列
- 搜尋列與按鈕在窄螢幕自動換行堆疊
- 手機輸入框字級 16px(避免 iOS 聚焦時自動放大)、按鈕加高方便點擊
- 支援瀏覽器瀏海 / 手勢列的安全區域 (safe-area)
- 自動跟隨系統深色模式

## 🖥️ 安裝到桌面

部署到 Render(HTTPS)後,用以下任一方式安裝:

| 瀏覽器 | 方式 |
| --- | --- |
| **Chrome**(Windows / macOS / Linux) | 點頁面上的「📲 安裝到桌面」,或網址列右側的安裝圖示 |
| **Edge** | 點「📲 安裝到桌面」,或網址列安裝圖示;也可「⋯ → 應用程式 → 將此網站安裝為應用程式」 |
| **Safari**(macOS 14 以上) | 選單列「檔案 → 加入 Dock」 |
| **iOS Safari** | 分享按鈕 → 加入主畫面 |
| **Firefox 桌面版** | 不支援安裝,請改用 Chrome 或 Edge |

安裝後會以獨立視窗開啟(沒有網址列),並出現在開始功能表 / Launchpad / Dock。想要**桌面捷徑**:

- **Windows**:安裝時勾選「建立桌面捷徑」;或在 `chrome://apps` 對圖示按右鍵 →「建立捷徑」。
- **macOS**:Chrome 會把 App 放在 `~/Applications/Chrome Apps`,可拖曳到桌面或 Dock。

**解除安裝**:在 App 視窗右上角「⋮」→「解除安裝」,或到 `chrome://apps` 按右鍵移除。

### 沒看到安裝圖示?

1. 必須是 **HTTPS**(Render 預設有)或 `localhost`;用 `http://區網IP` 開啟不能安裝。
2. 已經安裝過的話,瀏覽器不會再提示。
3. 無痕視窗通常不會出現安裝提示。
4. 重新整理一次,等 Service Worker 啟動後再試(F12 → Application 可確認狀態)。
5. 點頁面上的「📲 安裝到桌面」按鈕,會依你的瀏覽器顯示對應的手動步驟。

## 專案結構

```
.
├── app.py                         # 主程式(FastAPI 外層 + Gradio 介面)
├── requirements.txt
├── render.yaml                    # Render Blueprint(選用)
├── README.md
└── pwa/
    ├── manifest.webmanifest       # PWA 設定
    ├── sw.js                      # Service Worker(由 /sw.js 提供)
    ├── offline.html               # 離線頁面
    └── icons/                     # 192 / 512 / maskable / apple-touch-icon / favicon.ico
```

## 路由

| 路徑 | 說明 |
| --- | --- |
| `/` | Gradio 介面 |
| `/manifest.webmanifest` | PWA 設定檔 |
| `/sw.js` | Service Worker(必須在根路徑,才能控制整個網站) |
| `/offline` | 離線頁面 |
| `/favicon.ico` | 網站圖示 |
| `/pwa/*` | 圖示等靜態檔 |
| `/healthz` | 健康檢查 |

## 本機執行

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

開啟 <http://localhost:7860>。`localhost` 被瀏覽器視為安全來源,可以直接測試 PWA。

## 部署到 Render

### 方法一:Blueprint

1. 將專案推上 GitHub。
2. Render → **New → Blueprint**,選擇你的 repo,會讀取 `render.yaml` 自動建立服務。

### 方法二:手動建立 Web Service

| 欄位 | 值 |
| --- | --- |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python app.py` |
| Health Check Path | `/healthz` |
| Environment | `PYTHON_VERSION` = `3.11.9` |

Render 預設提供 HTTPS,滿足 PWA 的安全來源要求。

## 如何測試 PWA

1. 用 Chrome 開啟部署後的網址,按 F12 → **Application** 分頁。
2. **Manifest**:確認名稱、圖示、沒有錯誤。
3. **Service Workers**:狀態應為 *activated and running*。
4. 網址列右側會出現安裝圖示,或點頁面右下角「📲 安裝 App」。
5. 勾選 Service Workers 的 **Offline**,重新整理,應看到離線頁面。
6. **Lighthouse** 可產生 PWA 檢查報告。

### iOS 安裝方式

iOS Safari 不會觸發安裝提示:點分享按鈕 → **加入主畫面**。

> 想讓 Chrome / Edge 的安裝對話框顯示預覽畫面,可在 `manifest.webmanifest` 加上 `screenshots`(桌面寬螢幕與手機直式各一張真實截圖)。這是選用功能,不影響能否安裝。

## 自訂

- **換圖示**:直接覆蓋 `pwa/icons/` 內的 PNG(尺寸不變)。maskable 圖的重要內容請留在中央 80% 安全區。
- **換主題色**:同步修改 `manifest.webmanifest` 的 `theme_color`、`app.py` 的 `<meta name="theme-color">` 與 CSS 的 `--brand`。
- **更新快取**:修改 `pwa/sw.js` 後,把 `VERSION` 加 1(如 `v2`),舊快取會自動清除。
- **換資料來源**:設定環境變數 `DATA_URL`。

## 環境變數

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `DATA_URL` | 台南市資料集網址 | CSV 下載連結 |
| `CACHE_SECONDS` | `600` | 資料快取秒數 |
| `PORT` | `7860` | 服務埠號(Render 自動注入) |

## 注意事項

- **Free 方案會休眠**:閒置後第一次開啟需等待約 30–60 秒。
- **SSL 驗證**:政府網站憑證鏈常不完整,程式使用 `verify=False`;若來源憑證正常,建議到 `fetch_csv()` 移除。
- **匯出檔案**:存放在暫存資料夾,重新部署後會消失。
- **多人共用快取**:所有訪客共用同一份資料快取,適合公開資料集。

## 授權

MIT
