# 沅興木業倉庫系統

Flask + Render + PostgreSQL/SQLite 版本。

## 主要功能
- 登入 / 改密碼 / 登出
- 首頁：庫存、訂單、總單、出貨、出貨查詢、倉庫圖、客戶資料
- 今日異動通知中心
- OCR 上傳（低信心仍會輸出到文字欄）
- AI 修正學習
- 庫存 / 訂單 / 總單 / 出貨 / 出貨查詢
- A/B 倉庫圖、拖曳、手動編輯
- PWA 主畫面安裝

## Render
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Python: `3.11.10`
