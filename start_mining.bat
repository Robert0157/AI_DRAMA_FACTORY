@echo off
chcp 65001 >nul
echo =======================================================
echo 🚀 提線社畜 - 齒輪二 (代號：智譜 2000 萬 免費Token 計畫)
echo =======================================================

echo 啟動虛擬環境 (venv)...
call .\venv\Scripts\activate

echo.
echo [1/2] 🧠 喚醒 AI 藝術總監 (生成關鍵字)...
python scripts\gear2_rnd\daily_keyword_mutator.py

echo.
echo [2/2] 🚂 啟動多模態礦車 (開始收割與分析寫入miner_output.log)...
python scripts\gear2_rnd\batch_style_analyzer_sqlite.py > miner_output.log 2>&1

echo.
echo 🎉 本輪挖礦完畢！請檢查 assets\data\style_vault.db
pause