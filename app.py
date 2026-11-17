"""台南市開放資料瀏覽器 — Gradio + PWA + RWD,可部署到 Render

架構:FastAPI 作為外層伺服器
  /manifest.webmanifest  PWA 設定檔
  /sw.js                 Service Worker(必須在根路徑,才能控制整個網站)
  /offline               離線頁面
  /favicon.ico           網站圖示
  /pwa/...               圖示等靜態檔(不可用 /static,會和 Gradio 自己的路徑衝突)
  /healthz               Render 健康檢查
  /                      Gradio 介面
"""

import io
import os
import tempfile
import time
import uuid
import warnings
from pathlib import Path

import gradio as gr
import pandas as pd
import requests
import urllib3
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent
PWA_DIR = BASE_DIR / "pwa"

# 可透過環境變數覆蓋,不必改程式碼
URL = os.environ.get(
    "DATA_URL",
    "https://data.tainan.gov.tw/File/ResourceCsvDownload/6c16b2c8-92b6-49d9-98b5-02966462172c",
)
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "600"))
PORT = int(os.environ.get("PORT", "7860"))

_cache = {"df": pd.DataFrame(), "ts": 0.0}


# ======================================================================
# 資料層
# ======================================================================
def fetch_csv() -> pd.DataFrame:
    response = requests.get(URL, verify=False, timeout=30)
    response.raise_for_status()
    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            return pd.read_csv(io.BytesIO(response.content), encoding=enc)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError("無法判斷 CSV 編碼,請手動指定 encoding。")


def get_data(force: bool = False):
    """回傳 (DataFrame, 狀態訊息);有快取時不重複下載"""
    fresh = (time.time() - _cache["ts"]) < CACHE_SECONDS
    if not force and fresh and not _cache["df"].empty:
        return _cache["df"], "✅ 使用快取資料"
    try:
        _cache["df"] = fetch_csv()
        _cache["ts"] = time.time()
        return _cache["df"], "✅ 資料下載成功"
    except Exception as e:
        if not _cache["df"].empty:
            return _cache["df"], f"⚠️ 下載失敗,顯示舊資料:{e}"
        return pd.DataFrame({"錯誤": [str(e)]}), f"❌ 下載失敗:{e}"


def stats_html(df: pd.DataFrame, status: str = "") -> str:
    cards = [
        ("📄 資料筆數", f"{len(df):,}"),
        ("🧱 欄位數", f"{df.shape[1]}"),
        ("⚠️ 缺值總數", f"{int(df.isna().sum().sum()):,}"),
        ("✅ 完整列數", f"{len(df.dropna()):,}"),
    ]
    html = "<div class='cards'>"
    for title, value in cards:
        html += f"<div class='card'><div class='card-title'>{title}</div><div class='card-value'>{value}</div></div>"
    html += "</div>"
    if status:
        html += f"<div class='status'>{status}</div>"
    return html


def column_summary(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "欄位": df.columns,
            "型別": [str(t) for t in df.dtypes],
            "缺值數": df.isna().sum().values,
            "缺值比例(%)": (df.isna().mean() * 100).round(1).values,
            "不重複值數": df.nunique().values,
        }
    )


# ======================================================================
# 互動功能
# ======================================================================
def query(keyword, cols, drop_na):
    full, _ = get_data()
    d = full.copy()
    if drop_na:
        d = d.dropna()
    if keyword:
        mask = d.astype(str).apply(
            lambda s: s.str.contains(keyword, case=False, na=False, regex=False)
        ).any(axis=1)
        d = d[mask]
    if cols:
        d = d[[c for c in cols if c in d.columns]]
    return d, f"🔎 符合條件:**{len(d):,}** / {len(full):,} 筆"


def export_csv(keyword, cols, drop_na):
    d, _ = query(keyword, cols, drop_na)
    # 寫到系統暫存資料夾(Gradio 允許提供下載),檔名隨機避免多人互相覆蓋
    path = os.path.join(tempfile.gettempdir(), f"tainan_export_{uuid.uuid4().hex[:8]}.csv")
    d.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def make_chart(col):
    df, _ = get_data()
    if df.empty or not col or col not in df.columns:
        return pd.DataFrame({"類別": [], "數量": []})
    vc = df[col].astype(str).value_counts().head(15).reset_index()
    vc.columns = ["類別", "數量"]
    return vc


def init(force: bool = False):
    df, status = get_data(force)
    cols = list(df.columns)
    table, count = query("", [], False)
    return (
        stats_html(df, status),
        gr.update(choices=cols, value=[]),
        gr.update(choices=cols, value=cols[0]),
        column_summary(df),
        table,
        count,
        make_chart(cols[0]),
    )


def refresh():
    return init(force=True)


# ======================================================================
# PWA:注入 <head>(manifest、圖示、Service Worker、安裝按鈕、離線提示)
# ======================================================================
HEAD = r"""
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#4f46e5">
<meta name="application-name" content="台南資料">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="台南資料">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="/pwa/icons/apple-touch-icon.png">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="192x192" href="/pwa/icons/icon-192.png">
<script>
(function () {
  var root = document.documentElement;
  var mq = window.matchMedia('(display-mode: standalone)');

  // ---- 是否已用 App 視窗開啟(已安裝)----
  function syncStandalone() {
    var on = mq.matches || window.navigator.standalone === true;
    root.classList.toggle('pwa-standalone', on);
  }
  syncStandalone();
  if (mq.addEventListener) mq.addEventListener('change', syncStandalone);

  // ---- 註冊 Service Worker ----
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function (e) {
        console.warn('SW 註冊失敗', e);
      });
    });
  }

  // ---- 提示列(離線 / 已安裝)----
  function banner(text, cls) {
    var el = document.getElementById('pwa-net');
    if (!el) {
      el = document.createElement('div');
      el.id = 'pwa-net';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.className = 'show ' + cls;
    if (cls === 'on') setTimeout(function () { el.className = ''; }, 2500);
  }
  window.addEventListener('offline', function () { banner('⚠️ 目前離線,部分功能無法使用', 'off'); });
  window.addEventListener('online', function () { banner('✅ 已恢復連線', 'on'); });

  // ---- 安裝流程 ----
  var deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();          // 先保留事件,等使用者按「安裝到桌面」再觸發
    deferredPrompt = e;
    root.classList.add('pwa-can-install');
  });

  window.addEventListener('appinstalled', function () {
    deferredPrompt = null;
    root.classList.remove('pwa-can-install');
    closeModal();
    banner('✅ 安裝完成!可從桌面、開始功能表或 Dock 開啟', 'on');
  });

  // 依瀏覽器給出手動安裝步驟
  function guide() {
    var ua = navigator.userAgent;
    var steps;
    var title = '安裝到桌面';
    if (!window.isSecureContext) {
      return { title: '目前無法安裝', steps: ['瀏覽器只允許在 HTTPS(或 localhost)的網站安裝 App。', '請改用 https:// 開頭的網址開啟本頁。'] };
    }
    if (/iPhone|iPad|iPod/.test(ua)) {
      steps = ['用 Safari 開啟本頁。', '點下方的「分享」按鈕。', '選擇「加入主畫面」,再按「新增」。'];
    } else if (/Firefox\//.test(ua)) {
      title = '此瀏覽器不支援安裝';
      steps = ['桌面版 Firefox 目前不支援安裝網頁 App。', '請改用 Chrome 或 Edge 開啟本頁,即可安裝到桌面。'];
    } else if (/Edg\//.test(ua)) {
      steps = ['看網址列最右側的「安裝」圖示(顯示器加號)並點擊,按「安裝」。', '或點右上角「⋯」→「應用程式」→「將此網站安裝為應用程式」。', '安裝時可勾選「建立桌面捷徑」。'];
    } else if (/Chrome\//.test(ua)) {
      steps = ['看網址列最右側的「安裝」圖示(顯示器加下箭頭)並點擊,按「安裝」。', '或點右上角「⋮」→「投放、儲存和分享」→「將網頁安裝為應用程式」。', '想要桌面捷徑:在 chrome://apps 對圖示按右鍵 →「建立捷徑」。'];
    } else if (/Safari\//.test(ua)) {
      steps = ['需要 macOS Sonoma(14)以上的 Safari。', '點選單列「檔案」→「加入 Dock」。'];
    } else {
      steps = ['請改用 Chrome 或 Edge 開啟本頁,再從網址列的「安裝」圖示安裝。'];
    }
    if (root.classList.contains('pwa-standalone')) {
      steps = ['你已經是以 App 視窗開啟,不需要再安裝。'];
    } else if (!/iPhone|iPad|iPod|Firefox\//.test(ua) && /Chrome\/|Edg\//.test(ua)) {
      steps.push('若找不到安裝圖示:可能已經安裝過、正在使用無痕視窗,或請重新整理後再試。');
    }
    return { title: title, steps: steps };
  }

  function closeModal() {
    var m = document.getElementById('pwa-modal');
    if (m) m.remove();
  }

  function openModal() {
    closeModal();
    var g = guide();
    var overlay = document.createElement('div');
    overlay.id = 'pwa-modal';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');

    var box = document.createElement('div');
    box.className = 'pwa-box';
    var h = document.createElement('h3');
    h.textContent = '📲 ' + g.title;
    var ol = document.createElement('ol');
    g.steps.forEach(function (s) {
      var li = document.createElement('li');
      li.textContent = s;
      ol.appendChild(li);
    });
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = '知道了';
    btn.addEventListener('click', closeModal);

    box.appendChild(h);
    box.appendChild(ol);
    box.appendChild(btn);
    overlay.appendChild(box);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModal(); });
    document.body.appendChild(overlay);
    btn.focus();
  }

  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

  // 事件委派:Gradio 會動態產生畫面,所以不直接綁在按鈕上
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-pwa-install]') : null;
    if (!t) return;
    e.preventDefault();
    if (deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function () {
        deferredPrompt = null;
        root.classList.remove('pwa-can-install');
      });
    } else {
      openModal();
    }
  });
})();
</script>
"""

# ======================================================================
# RWD:行動優先的樣式
# ======================================================================
CSS = """
:root { --brand:#4f46e5; --brand2:#14b8a6; }
html { -webkit-text-size-adjust: 100%; }
.gradio-container {
  max-width: 1200px !important; margin: auto;
  padding-left: max(12px, env(safe-area-inset-left)) !important;
  padding-right: max(12px, env(safe-area-inset-right)) !important;
  padding-bottom: calc(24px + env(safe-area-inset-bottom)) !important;
}
footer { opacity: .6; }

.hero { text-align: center; padding: 24px 8px 6px; }
.hero h1 { font-size: clamp(1.45rem, 4.5vw, 2.2rem); margin: 0 0 4px; line-height: 1.25; }
.hero p  { opacity: .75; margin: 0; font-size: clamp(.85rem, 2.6vw, 1rem); }

.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 14px 0; }
.card { border-radius: 16px; padding: 16px 18px; color: #fff;
        background: linear-gradient(135deg, #4f8cff, #7a5cff); box-shadow: 0 6px 18px rgba(79,140,255,.28); }
.card:nth-child(2) { background: linear-gradient(135deg, #11b5a4, #3ddc97); box-shadow: 0 6px 18px rgba(17,181,164,.25); }
.card:nth-child(3) { background: linear-gradient(135deg, #ff8a5c, #ff5c8a); box-shadow: 0 6px 18px rgba(255,92,138,.25); }
.card:nth-child(4) { background: linear-gradient(135deg, #f7b733, #fc7b3f); box-shadow: 0 6px 18px rgba(252,123,63,.25); }
.card-title { font-size: .85rem; opacity: .92; }
.card-value { font-size: clamp(1.4rem, 4vw, 1.9rem); font-weight: 700; margin-top: 4px; word-break: break-all; }
.status { text-align: center; opacity: .8; font-size: .88rem; margin-bottom: 6px; }

/* 大螢幕(桌面 App 視窗全螢幕)*/
@media (min-width: 1500px) {
  .gradio-container { max-width: 1400px !important; }
}
/* 以 App 視窗開啟時,標題區少一點上方留白 */
html.pwa-standalone .hero { padding-top: 14px; }

/* 平板:卡片 2x2 */
@media (max-width: 900px) {
  .cards { grid-template-columns: repeat(2, 1fr); gap: 10px; }
}
/* 手機:更緊湊,按鈕與輸入框更好點 */
@media (max-width: 600px) {
  .hero { padding-top: 16px; }
  .card { padding: 12px 14px; border-radius: 14px; }
  .card-title { font-size: .78rem; }
  button, .gr-button { min-height: 46px; }
  input, textarea, select { font-size: 16px !important; }  /* 避免 iOS 聚焦時自動放大 */
  .tab-nav button, [role="tab"] { padding: 10px 12px !important; font-size: .92rem; }
}

/* 安裝按鈕(標題下方) */
.install-wrap { display: flex; justify-content: center; margin: 10px 0 2px; }
.install-btn {
  border: 0; border-radius: 999px; padding: 11px 24px; font-weight: 600; font-size: .95rem; color: #fff; cursor: pointer;
  background: linear-gradient(135deg, var(--brand), var(--brand2)); box-shadow: 0 8px 22px rgba(79,70,229,.35);
  transition: transform .15s ease, box-shadow .15s ease;
}
.install-btn:hover { transform: translateY(-1px); box-shadow: 0 10px 26px rgba(79,70,229,.45); }
.install-btn:active { transform: scale(.98); }
/* 已安裝(App 視窗)時不再顯示安裝按鈕 */
html.pwa-standalone .install-wrap { display: none; }

/* 安裝教學視窗 */
#pwa-modal {
  position: fixed; inset: 0; z-index: 10001; display: grid; place-items: center; padding: 20px;
  background: rgba(15, 17, 40, .55); backdrop-filter: blur(3px);
}
#pwa-modal .pwa-box {
  width: min(440px, 100%); background: #fff; color: #1f2340; border-radius: 20px; padding: 24px 24px 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,.35);
}
#pwa-modal h3 { margin: 0 0 12px; font-size: 1.15rem; }
#pwa-modal ol { margin: 0 0 18px; padding-left: 1.3em; line-height: 1.75; font-size: .95rem; }
#pwa-modal button {
  width: 100%; border: 0; border-radius: 12px; padding: 12px; font-weight: 600; color: #fff; cursor: pointer;
  background: linear-gradient(135deg, var(--brand), var(--brand2));
}
@media (prefers-color-scheme: dark) {
  #pwa-modal .pwa-box { background: #1c1f3d; color: #eceeff; }
}

/* 離線 / 上線提示列 */
#pwa-net {
  position: fixed; left: 50%; transform: translate(-50%, -120%); z-index: 10000;
  top: calc(10px + env(safe-area-inset-top)); padding: 10px 18px; border-radius: 999px; color: #fff;
  font-size: .9rem; transition: transform .25s ease; max-width: 92vw; text-align: center;
}
#pwa-net.show { transform: translate(-50%, 0); }
#pwa-net.off { background: #e11d48; }
#pwa-net.on  { background: #059669; }

@media (prefers-reduced-motion: reduce) { #pwa-net { transition: none; } }
"""

theme = gr.themes.Soft(primary_hue="indigo", secondary_hue="teal", radius_size="lg")

# ======================================================================
# Gradio 介面
# ======================================================================
with gr.Blocks(theme=theme, css=CSS, head=HEAD, title="台南市開放資料瀏覽器") as demo:
    gr.HTML(
        "<div class='hero'><h1>🏙️ 台南市開放資料瀏覽器</h1>"
        "<p>即時下載政府資料開放平台 CSV,搜尋、篩選、統計與匯出</p>"
        "<div class='install-wrap'><button type='button' class='install-btn' data-pwa-install>📲 安裝到桌面</button></div></div>"
    )

    stats = gr.HTML()
    refresh_btn = gr.Button("🔄 重新下載資料", variant="primary")

    with gr.Tabs():
        with gr.Tab("📋 資料表"):
            with gr.Row():  # 窄螢幕時 min_width 不夠會自動換行堆疊
                keyword = gr.Textbox(
                    label="關鍵字搜尋", placeholder="輸入文字,搜尋所有欄位…", scale=3, min_width=240
                )
                drop_na = gr.Checkbox(label="刪除含空值的列 (dropna)", value=False, scale=1, min_width=200)
            col_select = gr.Dropdown(label="顯示欄位(不選 = 全部)", choices=[], multiselect=True)
            count_md = gr.Markdown()
            table = gr.Dataframe(interactive=False, wrap=True, max_height=480)
            with gr.Row():
                export_btn = gr.Button("💾 匯出目前結果為 CSV", min_width=220)
                export_file = gr.File(label="下載檔案", interactive=False, min_width=220)

        with gr.Tab("🧮 欄位摘要"):
            gr.Markdown("檢查每個欄位的型別與缺值情況,再決定 `dropna()` 要怎麼用。")
            summary = gr.Dataframe(interactive=False, wrap=True, max_height=480)

        with gr.Tab("📊 統計圖"):
            chart_col = gr.Dropdown(label="選擇欄位(顯示出現次數最多的前 15 項)", choices=[])
            chart = gr.BarPlot(
                x="類別", y="數量", title="類別分布", x_title="類別", y_title="數量",
                height=380, sort="-y",
            )

    filter_inputs = [keyword, col_select, drop_na]
    filter_outputs = [table, count_md]
    for comp in (keyword, col_select, drop_na):
        comp.change(query, filter_inputs, filter_outputs)

    export_btn.click(export_csv, filter_inputs, export_file)
    chart_col.change(make_chart, chart_col, chart)

    init_outputs = [stats, col_select, chart_col, summary, table, count_md, chart]
    demo.load(init, None, init_outputs)
    refresh_btn.click(refresh, None, init_outputs)


# ======================================================================
# FastAPI 外層:PWA 檔案 + 掛載 Gradio
# ======================================================================
api = FastAPI(title="Tainan Open Data PWA")


@api.get("/healthz", include_in_schema=False)
def healthz():
    return PlainTextResponse("ok")


@api.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(PWA_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@api.get("/sw.js", include_in_schema=False)
def service_worker():
    # no-cache:讓瀏覽器每次都檢查 SW 是否有更新;Service-Worker-Allowed:允許控制整個網站
    return FileResponse(
        PWA_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@api.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(PWA_DIR / "icons" / "favicon.ico", media_type="image/x-icon")


@api.get("/offline", include_in_schema=False)
def offline():
    return FileResponse(PWA_DIR / "offline.html", media_type="text/html")


api.mount("/pwa", StaticFiles(directory=PWA_DIR), name="pwa")

# 一定要最後掛載在 "/",否則會蓋掉上面的路由
app = gr.mount_gradio_app(api, demo.queue(), path="/")


if __name__ == "__main__":
    # Render 要求綁定 0.0.0.0 與環境變數 PORT;proxy_headers 讓 https 網址正確判斷
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")
