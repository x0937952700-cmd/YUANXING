# 沅興木業 APP

這是一份可直接覆蓋舊專案的 Flask + PostgreSQL / SQLite + Socket.IO 版本，重點包含：

- 首頁工作台
- 今日異動 badge 歸零
- 異常紀錄卡片完全刪除
- 庫存直接顯示商品
- 總單不顯示客戶名稱
- 拍照 / 相簿上傳
- 區域式 OCR 流程
- 低信心 OCR 仍輸出到可編輯文字框
- 倉庫圖 A/B 直式結構
- 商品跳轉倉庫圖高亮
- 多人即時同步
- 稽核紀錄
- PWA 安裝

## 本機啟動

```bash
python -m venv .venv
source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## Render 環境變數

至少設定：

- `SECRET_KEY`
- `DATABASE_URL`
- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`

若要讓 OCR 直接使用 OCR.Space API，可另外設定：

- `OCR_SPACE_API_KEY`

沒有設定 `OCR_SPACE_API_KEY` 時，程式會改用本機 `pytesseract`；若部署環境沒有安裝 Tesseract，OCR 會只能回傳提示而非完整辨識。

## 覆蓋建議

你可以直接用這份檔案樹覆蓋舊專案根目錄，再把 `DATABASE_URL` 指到 Render PostgreSQL。

## 預設登入

- 帳號：`admin`
- 密碼：`admin1234`

請部署後立刻改掉。
