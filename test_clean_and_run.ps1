# 清空舊 MP3 檔 (完全零庫存狀態)
Write-Host "========== 清空舊檔案 ==========" -ForegroundColor Yellow
Remove-Item "f:\AI_DRAMA_FACTORY\assets\audio\ceo_approved_beats\*.mp3" -Force -ErrorAction SilentlyContinue
Remove-Item "f:\AI_DRAMA_FACTORY\assets\audio\mastered_tracks\*.wav" -Force -ErrorAction SilentlyContinue
Write-Host "✓ 清空完成" -ForegroundColor Green

# 驗證零庫存狀態
Write-Host "`n========== 驗證狀態 ==========" -ForegroundColor Yellow
$mp3Count = (Get-ChildItem "f:\AI_DRAMA_FACTORY\assets\audio\ceo_approved_beats\*.mp3" -ErrorAction SilentlyContinue | Measure-Object).Count
$wavCount = (Get-ChildItem "f:\AI_DRAMA_FACTORY\assets\audio\mastered_tracks\*.wav" -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "MP3 檔案: $mp3Count" -ForegroundColor Cyan
Write-Host "WAV 檔案: $wavCount" -ForegroundColor Cyan

# 執行 pipeline
Write-Host "`n========== 執行 Pipeline ==========" -ForegroundColor Yellow
cd "f:\AI_DRAMA_FACTORY"
python scripts/gear1_prod/pipeline_runner.py --skip-cleanup *>&1 | Out-String | Write-Host

# 檢查最終結果
Write-Host "`n========== 最終結果 ==========" -ForegroundColor Yellow
$mp3Final = (Get-ChildItem "f:\AI_DRAMA_FACTORY\assets\audio\ceo_approved_beats\*.mp3" -ErrorAction SilentlyContinue | Measure-Object).Count
$wavFinal = (Get-ChildItem "f:\AI_DRAMA_FACTORY\assets\audio\mastered_tracks\*.wav" -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "生成 MP3: $mp3Final" -ForegroundColor Green
Write-Host "生成 WAV: $wavFinal" -ForegroundColor Green
