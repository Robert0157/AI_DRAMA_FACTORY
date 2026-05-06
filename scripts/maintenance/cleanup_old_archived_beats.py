import shutil
from pathlib import Path
import time
import zipfile

ARCHIVE_ROOT = Path("assets/audio/ceo_archived_beats")
BACKUP_ROOT = Path("assets/audio/archived_beats_backup")
DAYS_KEEP = 30  # 只保留30天內的檔案

BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
now = time.time()

for channel_dir in ARCHIVE_ROOT.iterdir():
    if not channel_dir.is_dir():
        continue
    zip_name = f"{channel_dir.name}_backup_{time.strftime('%Y%m%d')}.zip"
    zip_path = BACKUP_ROOT / zip_name
    with zipfile.ZipFile(zip_path, 'a', zipfile.ZIP_DEFLATED) as zipf:
        for f in channel_dir.glob("*.mp3"):
            if now - f.stat().st_mtime > DAYS_KEEP * 86400:
                zipf.write(f, arcname=f.name)
                f.unlink()
    print(f"頻道 {channel_dir.name}：已備份並刪除超過30天的檔案 → {zip_path}")
