"""Pi Camera capture with mock fallback for development."""
from __future__ import annotations

import logging
import math
import platform
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

IS_PI = platform.machine() == "aarch64"


@dataclass
class PhotoResult:
    plant_name: str
    timestamp: datetime
    path: Path


async def capture_photo(plant_name: str, save_dir: Path) -> PhotoResult | None:
    """Capture a photo of a plant. Returns None on failure."""
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow()
    filename = f"{plant_name}_{ts.strftime('%Y%m%d_%H%M%S')}.jpg"
    path = save_dir / filename

    if IS_PI:
        return await _capture_real(plant_name, path, ts)
    return _capture_mock(plant_name, path, ts)


async def _capture_real(plant_name: str, path: Path, ts: datetime) -> PhotoResult | None:
    try:
        from picamera2 import Picamera2  # type: ignore[import]
        cam = Picamera2()
        cam.configure(cam.create_still_configuration())
        cam.start()
        cam.capture_file(str(path))
        cam.stop()
        cam.close()
        logger.info("Photo captured: %s", path)
        return PhotoResult(plant_name=plant_name, timestamp=ts, path=path)
    except Exception as exc:
        logger.error("Camera capture failed: %s", exc)
        return None


def _capture_mock(plant_name: str, path: Path, ts: datetime) -> PhotoResult:
    try:
        img = _render_plant(plant_name, seed=hash(plant_name) & 0xFFFF)
        img.save(str(path), format="JPEG", quality=88)
        logger.info("[MOCK] Generated plant photo: %s", path)
    except ImportError:
        # Pillow unavailable — write a raw placeholder so the file exists
        path.write_bytes(b"MOCK_IMAGE")
        logger.warning("[MOCK] Pillow not installed — wrote placeholder: %s", path)
    return PhotoResult(plant_name=plant_name, timestamp=ts, path=path)


def _render_plant(plant_name: str, seed: int = 42) -> "Image.Image":
    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(seed)
    W, H = 640, 480
    img = Image.new("RGB", (W, H), color=(12, 24, 16))
    draw = ImageDraw.Draw(img)

    # Subtle soil/ground gradient strip
    for y in range(H - 60, H):
        t = (y - (H - 60)) / 60
        r = int(30 + t * 18)
        g = int(18 + t * 10)
        b = int(8 + t * 4)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Terracotta pot
    cx, base_y = W // 2, H - 40
    pot_w, pot_h = 90, 70
    draw.ellipse([cx - pot_w // 2, base_y - 8, cx + pot_w // 2, base_y + 8], fill=(120, 62, 38))
    draw.polygon([
        (cx - pot_w // 2, base_y),
        (cx + pot_w // 2, base_y),
        (cx + pot_w // 2 - 10, base_y - pot_h),
        (cx - pot_w // 2 + 10, base_y - pot_h),
    ], fill=(148, 76, 46))
    # Pot rim highlight
    draw.ellipse([cx - pot_w // 2 + 10, base_y - pot_h - 6,
                  cx + pot_w // 2 - 10, base_y - pot_h + 6], fill=(164, 90, 58))

    # Dark soil surface
    draw.ellipse([cx - pot_w // 2 + 14, base_y - pot_h - 4,
                  cx + pot_w // 2 - 14, base_y - pot_h + 4], fill=(28, 18, 10))

    # Stem + leaves (recursive branching)
    stem_top = base_y - pot_h - 4
    _draw_branch(draw, rng, cx, stem_top, angle=-math.pi / 2, length=80 + rng.randint(-10, 20), depth=4)

    # Soft vignette overlay
    vignette = Image.new("L", (W, H), 0)
    vdraw = ImageDraw.Draw(vignette)
    steps = 60
    for i in range(steps):
        t = i / steps
        lum = int(200 * (1 - t) ** 2.0)
        margin = int(t * min(W, H) * 0.6)
        vdraw.rectangle([margin, margin, W - margin, H - margin], fill=lum)
    vignette_rgb = Image.merge("RGB", (vignette, vignette, vignette))
    img = Image.blend(img, vignette_rgb, alpha=0.28)

    # Plant name label
    draw2 = ImageDraw.Draw(img)
    draw2.text((14, 14), plant_name.upper(), fill=(60, 120, 70))
    draw2.text((14, 30), "[MOCK]", fill=(40, 80, 50))

    # Slight blur for softness
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    return img


def _draw_branch(
    draw: "ImageDraw.ImageDraw",
    rng: random.Random,
    x: float,
    y: float,
    angle: float,
    length: float,
    depth: int,
) -> None:
    if depth == 0 or length < 6:
        # Terminal leaf — colour based on original call depth (captured via length proxy)
        lw = max(5, int(length * 0.55))
        lh = max(8, int(length * 1.1))
        brightness = min(int(length * 1.2), 60)  # longer remaining length → lighter leaf
        _draw_rotated_ellipse(draw, x, y, lw, lh, angle, fill=(20 + brightness, 90 + brightness, 35))
        return

    # Stem segment
    ex = x + math.cos(angle) * length
    ey = y + math.sin(angle) * length
    green = min(255, 60 + depth * 22)
    sw = max(1, depth - 1)
    draw.line([(int(x), int(y)), (int(ex), int(ey))], fill=(18, green, 28), width=sw)

    spread = 0.38 + rng.uniform(-0.05, 0.05)
    shrink = 0.62 + rng.uniform(-0.04, 0.04)
    _draw_branch(draw, rng, ex, ey, angle - spread, length * shrink, depth - 1)
    _draw_branch(draw, rng, ex, ey, angle + spread, length * shrink, depth - 1)
    if depth >= 3:
        mid_angle = angle + rng.uniform(-0.12, 0.12)
        _draw_branch(draw, rng, ex, ey, mid_angle, length * shrink * 0.78, depth - 2)


def _draw_rotated_ellipse(
    draw: "ImageDraw.ImageDraw",
    cx: float, cy: float,
    rw: int, rh: int,
    angle: float,
    fill: tuple[int, int, int],
) -> None:
    """Approximate a rotated ellipse by drawing a small polygon."""
    points = []
    steps = 14
    for i in range(steps):
        t = 2 * math.pi * i / steps
        lx = rw * math.cos(t)
        ly = rh * math.sin(t)
        rx = lx * math.cos(angle) - ly * math.sin(angle) + cx
        ry = lx * math.sin(angle) + ly * math.cos(angle) + cy
        points.append((int(rx), int(ry)))
    draw.polygon(points, fill=fill)
