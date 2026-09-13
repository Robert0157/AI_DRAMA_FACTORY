# -*- coding: utf-8 -*-
"""
Storyboard animatic preview generator.

Turns a Stage-1 storyboard JSON into a REAL playable MP4 where each shot is a
text card (shot type / dialogue / emotion tag / timing) with its true duration.
Purpose: let the CEO preview script rhythm & emotion flow BEFORE expensive AI
video generation (Stage 2/3). This is NOT the final AI video — it is a
script-level animatic produced by Auto_Drama + ffmpeg.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

# Card geometry (landscape 16:9 preview).
W, H = 1280, 720
FPS = 24
MARGIN = 60

# Dark cinematic background per canonical emotion tag.
EMOTION_BG: Dict[str, Tuple[int, int, int]] = {
    "suspense": (24, 24, 46),
    "sad": (17, 27, 38),
    "tense": (46, 22, 22),
    "horror": (22, 8, 12),
    "joyful": (50, 40, 16),
    "epic": (32, 26, 50),
    "warm": (44, 34, 22),
    "conflict": (48, 18, 16),
    "relief": (18, 42, 36),
    "romance": (46, 22, 42),
}
EMOTION_ACCENT: Dict[str, Tuple[int, int, int]] = {
    "suspense": (150, 170, 255),
    "sad": (140, 180, 210),
    "tense": (255, 120, 100),
    "horror": (200, 60, 60),
    "joyful": (255, 220, 120),
    "epic": (255, 200, 120),
    "warm": (255, 200, 150),
    "conflict": (255, 110, 90),
    "relief": (150, 220, 190),
    "romance": (255, 160, 220),
}
FALLBACK_BG = (30, 30, 34)

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",   # 微軟雅黑 (Windows)
    "C:/Windows/Fonts/msjh.ttc",   # 微軟正黑體
    "/System/Library/Fonts/PingFang.ttc",      # Mac
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
]


def _load_font(size: int) -> "ImageFont.ImageFont":
    """Load a CJK-capable font; fall back to PIL default if none found."""
    if ImageFont is None:
        raise RuntimeError("Pillow is required (pip install pillow)")
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap(draw: "ImageDraw.ImageDraw", text: str, font, max_w: int) -> List[str]:
    """Wrap CJK text to fit max_w pixels using measured glyph widths."""
    lines: List[str] = []
    for raw_line in str(text).splitlines():
        if not raw_line:
            lines.append("")
            continue
        cur = ""
        for ch in raw_line:
            trial = cur + ch
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    return lines


def _truncate_to(draw, text: str, font, max_w: int, max_lines: int) -> List[str]:
    lines = _wrap(draw, text, font, max_w)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def _draw_card(shot: dict, idx: int, total: int, episode_title: str,
               fonts: dict) -> Path:
    """Render one shot card PNG into a temp dir; returns the PNG path."""
    emotion = str(shot.get("emotion") or "suspense")
    bg = EMOTION_BG.get(emotion, FALLBACK_BG)
    accent = EMOTION_ACCENT.get(emotion, (220, 220, 220))
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    white = (245, 245, 245)
    grey = (200, 200, 200)

    # Header: episode + shot counter.
    d.text((MARGIN, 42), f"AUTO_DRAMA 分鏡預覽  ·  {episode_title}",
           font=fonts["small"], fill=grey)
    d.text((W - MARGIN, 42), f"SHOT {idx}/{total}", font=fonts["small"],
           fill=grey, anchor="ra")

    # Emotion accent bar.
    d.rectangle([MARGIN, 92, W - MARGIN, 100], fill=accent)

    # Shot title.
    d.text((MARGIN, 120), shot.get("title") or f"鏡頭 {idx}",
           font=fonts["title"], fill=white)

    # Meta line: emotion + intensity + shot type + duration.
    intensity = int(shot.get("emotion_intensity") or 0)
    arrows = "↑" * max(0, intensity) if intensity >= 0 else "↓"
    meta = (f"情緒: {emotion} {arrows}   |   景別: {shot.get('shot_type', '')}   |   "
            f"運鏡: {shot.get('movement', '')}   |   時長: {shot.get('duration', '')}s   |   "
            f"時間: {shot.get('time', '')}")
    d.text((MARGIN, 200), meta, font=fonts["body_small"], fill=accent)

    y = 260
    # Location.
    loc = shot.get("location") or shot.get("atmosphere") or ""
    if loc:
        for line in _truncate_to(d, f"場景: {loc}", fonts["body"], W - 2 * MARGIN, 2):
            d.text((MARGIN, y), line, font=fonts["body"], fill=grey)
            y += fonts["body"].size + 12
        y += 10

    # Dialogue (highlighted, centered emphasis).
    dialogue = shot.get("dialogue") or ""
    if dialogue:
        d.text((MARGIN, y), "台詞", font=fonts["small"], fill=accent)
        y += fonts["small"].size + 6
        for line in _truncate_to(d, dialogue, fonts["body"], W - 2 * MARGIN, 4):
            d.text((MARGIN, y), line, font=fonts["body"], fill=white)
            y += fonts["body"].size + 10
        y += 10

    # Action.
    action = shot.get("action") or ""
    if action:
        for line in _truncate_to(d, f"動作: {action}", fonts["body"], W - 2 * MARGIN, 3):
            d.text((MARGIN, y), line, font=fonts["body"], fill=grey)
            y += fonts["body"].size + 10

    # Image-prompt hint at bottom (small).
    ip = shot.get("image_prompt") or ""
    if ip:
        y = H - 150
        d.line([MARGIN, y - 6, W - MARGIN, y - 6], fill=(120, 120, 120))
        for line in _truncate_to(d, "視覺提示: " + ip, fonts["small"], W - 2 * MARGIN, 3):
            d.text((MARGIN, y), line, font=fonts["small"], fill=(170, 170, 170))
            y += fonts["small"].size + 8

    png = Path(tempfile.gettempdir()) / f"ad_card_{idx:03d}.png"
    img.save(png)
    return png


def make_animatic(storyboard_path: Path, out_mp4: Path,
                  episode_title: str = "", fps: int = FPS,
                  width: int = W, height: int = H) -> Path:
    """Build a real MP4 animatic from a Stage-1 storyboard JSON."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH")
    if Image is None:
        raise RuntimeError("Pillow is required (pip install pillow)")

    data = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    shots: List[dict] = data.get("shots") or []
    if not shots:
        raise ValueError(f"storyboard has no shots: {storyboard_path}")
    title = episode_title or data.get("title") or data.get("episode_id") or "ep"

    fonts = {
        "title": _load_font(64),
        "body": _load_font(34),
        "body_small": _load_font(28),
        "small": _load_font(24),
    }

    # 1) Render one PNG card per shot.
    cards: List[Path] = []
    for i, shot in enumerate(shots, start=1):
        cards.append(_draw_card(shot, i, len(shots), title, fonts))

    # 2) Encode each card to a silent clip of its real duration.
    tmpdir = Path(tempfile.mkdtemp(prefix="ad_animatic_"))
    clips: List[Path] = []
    try:
        for i, (shot, card) in enumerate(zip(shots, cards), start=1):
            dur = max(1.2, float(shot.get("duration") or 5.0))
            clip = tmpdir / f"clip_{i:03d}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-framerate", str(fps),
                "-i", str(card), "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", str(fps),
                str(clip),
            ], check=True, capture_output=True)
            clips.append(clip)
            card.unlink(missing_ok=True)

        # 3) Sequential lossless concat (broadcast discipline: no loops).
        list_path = tmpdir / "concat.txt"
        list_path.write_text(
            "\n".join(f"file '{c.resolve().as_posix()}'" for c in clips) + "\n",
            encoding="utf-8",
        )
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            "-c:v", "copy",
            str(out_mp4),
        ], check=True, capture_output=True)
    finally:
        # Clean up per-shot clips and temp dir (zero-waste rule).
        import shutil as _sh

        _sh.rmtree(tmpdir, ignore_errors=True)
    return out_mp4


# ---------------------------------------------------------------------------
# Visual preview (Stage 1 + Stage 2): each shot card uses the REAL AI keyframe
# generated in Stage 2, overlaid with shot/emotion/dialogue captions.
# ---------------------------------------------------------------------------
def _cover_resize(img: "Image.Image", w: int, h: int) -> "Image.Image":
    """Resize + center-crop an image to exactly w x h (cover fit)."""
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)),
                     getattr(Image, "LANCZOS", Image.BILINEAR))
    x = (img.width - w) // 2
    y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _find_shot_image(image_dir: Path, i: int) -> Path:
    """Locate stage-2 keyframe file shot_XX.(png|jpg|jpeg)."""
    for suf in (".png", ".jpg", ".jpeg"):
        cand = image_dir / f"shot_{i:02d}{suf}"
        if cand.exists():
            return cand
    raise FileNotFoundError(f"stage2 keyframe not found for shot {i} in {image_dir}")


def _caption_card(shot: dict, idx: int, total: int, episode_title: str,
                  keyframe_path: Path, fonts: dict) -> "Image.Image":
    """Compose one 1280x720 card from the generated keyframe + captions."""
    img = _cover_resize(Image.open(keyframe_path).convert("RGB"), W, H)
    d = ImageDraw.Draw(img, "RGBA")
    emotion = str(shot.get("emotion") or "suspense")
    accent = EMOTION_ACCENT.get(emotion, (220, 220, 220))
    white = (245, 245, 245)

    # Top translucent caption bar.
    d.rectangle([0, 0, W, 96], fill=(0, 0, 0, 170))
    d.text((MARGIN, 16), f"{episode_title}", font=fonts["small"], fill=(200, 200, 200))
    d.text((MARGIN, 44),
           f"SHOT {idx}/{total}  ·  {shot.get('title') or ''}  ·  "
           f"{shot.get('shot_type', '')}",
           font=fonts["body"], fill=white)
    intensity = int(shot.get("emotion_intensity") or 0)
    arrows = "↑" * max(0, intensity) if intensity >= 0 else "↓"
    meta = (f"情緒: {emotion} {arrows}   |   時長: {shot.get('duration', '')}s   |   "
            f"時間: {shot.get('time', '')}")
    d.text((W - MARGIN, 48), meta, font=fonts["small"], fill=accent, anchor="ra")

    # Bottom caption band with dialogue + action.
    d.rectangle([0, H - 190, W, H], fill=(0, 0, 0, 205))
    d.rectangle([MARGIN, H - 172, W - MARGIN, H - 170], fill=accent)
    dialogue = shot.get("dialogue") or ""
    if dialogue:
        for line in _truncate_to(d, dialogue, fonts["body"], W - 2 * MARGIN, 2):
            d.text((MARGIN, H - 158), line, font=fonts["body"], fill=white)
            break  # show first wrapped line pair only at the caption baseline
    loc = shot.get("location") or ""
    if loc:
        d.text((MARGIN, H - 78), f"場景: {loc}", font=fonts["small"], fill=(200, 200, 200))
    return img


def make_visual_preview(storyboard_path: Path, image_dir: Path, out_mp4: Path,
                        fps: int = FPS) -> Path:
    """
    Build a Stage1+2 preview MP4 where every shot shows its real generated
    keyframe for its true duration (shot dialogue/emotion overlaid).
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH")
    if Image is None:
        raise RuntimeError("Pillow is required (pip install pillow)")
    data = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    shots: List[dict] = data.get("shots") or []
    if not shots:
        raise ValueError(f"storyboard has no shots: {storyboard_path}")
    title = data.get("title") or data.get("episode_id") or "ep"

    fonts = {
        "body": _load_font(34),
        "small": _load_font(24),
        "smaller": _load_font(20),
    }

    tmpdir = Path(tempfile.mkdtemp(prefix="ad_visual_"))
    clips: List[Path] = []
    try:
        for i, shot in enumerate(shots, start=1):
            key = _find_shot_image(image_dir, i)
            card = _caption_card(shot, i, len(shots), title, key, fonts)
            card_png = tmpdir / f"card_{i:03d}.png"
            card.save(card_png)
            dur = max(1.2, float(shot.get("duration") or 5.0))
            clip = tmpdir / f"clip_{i:03d}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-framerate", str(fps),
                "-i", str(card_png), "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", str(fps),
                str(clip),
            ], check=True, capture_output=True)
            clips.append(clip)
            card_png.unlink(missing_ok=True)

        list_path = tmpdir / "concat.txt"
        list_path.write_text(
            "\n".join(f"file '{c.resolve().as_posix()}'" for c in clips) + "\n",
            encoding="utf-8",
        )
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_path), "-c:v", "copy", str(out_mp4),
        ], check=True, capture_output=True)
    finally:
        import shutil as _sh

        _sh.rmtree(tmpdir, ignore_errors=True)
    return out_mp4


# ---------------------------------------------------------------------------
# Contact sheet: one REAL screenshot per shot, extracted from the animatic MP4
# and tiled into a single PNG grid for quick CEO review.
# ---------------------------------------------------------------------------
def _shot_schedule(shots: List[dict]) -> Tuple[List[dict], float]:
    """Return (per-shot start/duration/mid sample time) + total duration."""
    schedule = []
    acc = 0.0
    for s in shots:
        dur = max(1.2, float(s.get("duration") or 5.0))
        schedule.append({"start": acc, "duration": dur, "mid": acc + dur / 2.0})
        acc += dur
    return schedule, acc


def _extract_frame(video_path: Path, t_sec: float, out_png: Path,
                   thumb_w: int) -> None:
    """Grab one frame at t_sec from the animatic, scaled to thumb_w width."""
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{t_sec:.3f}", "-i", str(video_path),
        "-frames:v", "1", "-vf", f"scale={thumb_w}:-2",
        str(out_png),
    ], check=True, capture_output=True)


def make_contact_sheet(storyboard_path: Path, video_path: Path, out_png: Path,
                       cols: int = 3, thumb_w: int = 480) -> Path:
    """Tile one screenshot per storyboard shot into a labeled PNG grid."""
    if Image is None:
        raise RuntimeError("Pillow is required (pip install pillow)")
    data = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    shots: List[dict] = data.get("shots") or []
    if not shots:
        raise ValueError(f"storyboard has no shots: {storyboard_path}")
    if not Path(video_path).exists():
        raise ValueError(f"animatic video not found: {video_path}")

    schedule, total = _shot_schedule(shots)
    n = len(shots)
    rows = (n + cols - 1) // cols
    thumb_h = round(thumb_w * 720 / 1280)          # animatic is 1280x720
    label_h = 52
    pad = 16
    header_h = 74

    tmpdir = Path(tempfile.mkdtemp(prefix="ad_sheet_"))
    font_header = _load_font(30)
    font_sub = _load_font(22)
    font_label1 = _load_font(24)
    font_label2 = _load_font(19)
    try:
        # 1) Extract one frame per shot.
        thumbs: List[Path] = []
        for i, seg in enumerate(schedule, start=1):
            fp = tmpdir / f"thumb_{i:03d}.png"
            _extract_frame(video_path, seg["mid"], fp, thumb_w)
            thumbs.append(fp)

        # 2) Compose the grid.
        Wsheet = cols * thumb_w + pad * (cols + 1)
        Hsheet = header_h + rows * (thumb_h + label_h) + pad * (rows + 1)
        canvas = Image.new("RGB", (Wsheet, Hsheet), (18, 18, 20))
        d = ImageDraw.Draw(canvas)
        white = (245, 245, 245)

        title = data.get("title") or data.get("episode_id") or "episode"
        d.text((pad, 16), f"{title}  ·  分鏡靜態截圖組合圖 (共 {n} 鏡 / {total:.0f}s)",
               font=font_header, fill=white)
        d.text((Wsheet - pad, 20), f"{Wsheet}x{Hsheet}", font=font_sub,
               fill=(140, 140, 140), anchor="ra")
        d.line([pad, header_h - 8, Wsheet - pad, header_h - 8], fill=(90, 90, 90))

        for i, (shot, seg) in enumerate(zip(shots, schedule)):
            col = i % cols
            row = i // cols
            x = pad + col * (thumb_w + pad)
            y = header_h + pad + row * (thumb_h + label_h)

            thumb = Image.open(thumbs[i]).convert("RGB")
            canvas.paste(thumb, (x, y))

            emotion = str(shot.get("emotion") or "suspense")
            accent = EMOTION_ACCENT.get(emotion, (220, 220, 220))
            intensity = int(shot.get("emotion_intensity") or 0)
            arrows = "↑" * max(0, intensity) if intensity >= 0 else "↓"
            line1 = f"{i + 1:02d}. {emotion} {arrows}  ·  {seg['duration']:.1f}s  ·  {shot.get('shot_type', '')}"
            d.text((x + 4, y + thumb_h + 4), line1, font=font_label1, fill=accent)
            line2 = (shot.get("title") or "")[:16]
            d.text((x + 4, y + thumb_h + 30), line2, font=font_label2, fill=(170, 170, 170))

        canvas.save(out_png)
    finally:
        import shutil as _sh

        _sh.rmtree(tmpdir, ignore_errors=True)
    return out_png


if __name__ == "__main__":
    print("此模組請透過: python run.py preview --storyboard <json> 使用", file=sys.stderr)
    sys.exit(0)
