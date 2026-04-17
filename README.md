# 沅興木業智慧倉庫系統

## Render 環境變數
- `PYTHON_VERSION=3.11.10`
- `SECRET_KEY=...`（Render 自動產生即可）
- `DATABASE_URL=...`（Render Postgres 的 Internal Database URL）

## 啟動
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`

## 主要頁面
- `/` 首頁
- `/inventory` 庫存
- `/order` 訂單
- `/master-order` 總單
- `/ship` 出貨
- `/shipping-records` 出貨查詢
- `/warehouse` 倉庫圖
- `/customers` 客戶資料
- `/settings` 設定/改密碼/備份
