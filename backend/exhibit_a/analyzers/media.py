"""Image authenticity signals: metadata forensics and JPEG ghost analysis.

None of these signals proves an image was faked. Each one is a reason for a
human examiner to look closer, and each finding says how it can mislead.
"""

from __future__ import annotations

import io
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import ExifTags, Image

from .base import Finding

EDITOR_HINTS = (
    "photoshop",
    "gimp",
    "snapseed",
    "lightroom",
    "picsart",
    "canva",
    "pixlr",
    "affinity",
    "facetune",
    "photoroom",
    "paint.net",
)
_SKIP_TAGS = {"ExifOffset", "GPSInfo", "MakerNote", "UserComment", "PrintImageMatching"}
_EXIF_TIME = "%Y:%m:%d %H:%M:%S"


def read_exif(path: str | Path) -> dict[str, str]:
    """Readable EXIF tags from the main IFD and the Exif sub-IFD."""
    out: dict[str, str] = {}
    with Image.open(path) as image:
        exif = image.getexif()
        groups = [exif]
        try:
            groups.append(exif.get_ifd(ExifTags.IFD.Exif))
        except (KeyError, AttributeError, ValueError):
            pass
        for group in groups:
            for tag, value in group.items():
                name = ExifTags.TAGS.get(tag, f"Tag{tag}")
                if name in _SKIP_TAGS or isinstance(value, (bytes, dict)):
                    continue
                out[name] = str(value).strip("\x00 ").strip()
    return out


def _parse_exif_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], _EXIF_TIME)
    except ValueError:
        return None


def _components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """4-connected components of True cells in a 2D boolean grid."""
    seen = np.zeros_like(mask, dtype=bool)
    groups = []
    rows, cols = mask.shape
    for r in range(rows):
        for c in range(cols):
            if not mask[r, c] or seen[r, c]:
                continue
            queue = deque([(r, c)])
            seen[r, c] = True
            cells = []
            while queue:
                y, x = queue.popleft()
                cells.append((y, x))
                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= ny < rows and 0 <= nx < cols and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            groups.append(cells)
    return groups


GHOST_QUALITIES = tuple(range(50, 100, 5))


def _block_means(error: np.ndarray, block: int) -> np.ndarray:
    height, width = error.shape
    rows, cols = height // block, width // block
    return error[: rows * block, : cols * block].reshape(rows, block, cols, block).mean(axis=(1, 3))


def _resave_error(rgb: Image.Image, quality: int) -> np.ndarray:
    buffer = io.BytesIO()
    rgb.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    with Image.open(buffer) as again:
        resaved = np.asarray(again.convert("RGB"), dtype=np.float32)
    return np.abs(np.asarray(rgb, dtype=np.float32) - resaved).mean(axis=2)


def jpeg_ghost_analysis(path: str | Path, block: int = 16, qualities: tuple[int, ...] = GHOST_QUALITIES) -> dict:
    """Look for JPEG ghosts (Farid, 2009).

    Re-save the image at a range of qualities and measure how much it changes.
    The curve bottoms out at the quality of the last save. A second dip means
    the picture was saved at least twice, and that second dip quality is the
    earlier save. At that quality untouched areas barely change, while
    anything drawn or pasted after the earlier save changes a lot. Dividing by
    the error at a low reference quality cancels out ordinary edges and text,
    so what is left is compression history, not content.
    """
    with Image.open(path) as image:
        source_format = image.format
        rgb = image.convert("RGB")
    result: dict = {"format": source_format, "last_quality": None, "ghost_quality": None, "curve": {}, "regions": []}
    if source_format != "JPEG":
        return result

    errors = {quality: _resave_error(rgb, quality) for quality in qualities}
    curve = {quality: float(error.mean()) for quality, error in errors.items()}
    result["curve"] = {quality: round(value, 4) for quality, value in curve.items()}
    last = min(curve, key=curve.get)
    result["last_quality"] = last

    steps = list(qualities)
    dips = [
        steps[i]
        for i in range(1, len(steps) - 1)
        if steps[i] != last and curve[steps[i]] < 0.6 * min(curve[steps[i - 1]], curve[steps[i + 1]])
    ]
    if not dips:
        result["heatmap"] = errors[last]
        return result
    ghost = min(dips, key=curve.get)
    result["ghost_quality"] = ghost
    result["heatmap"] = errors[ghost]

    ghost_blocks = _block_means(errors[ghost], block)
    reference_blocks = _block_means(errors[min(steps)], block)
    ratio = ghost_blocks / np.maximum(reference_blocks, 0.05)
    hot = (ratio > max(0.35, 4.0 * float(np.median(ratio)))) & (
        ghost_blocks > 3.0 * max(float(np.median(ghost_blocks)), 0.05)
    )

    regions = []
    for cells in _components(hot):
        if len(cells) < 2:
            continue
        ys = [y for y, _ in cells]
        xs = [x for _, x in cells]
        regions.append(
            {
                "x": min(xs) * block,
                "y": min(ys) * block,
                "w": (max(xs) - min(xs) + 1) * block,
                "h": (max(ys) - min(ys) + 1) * block,
                "blocks": len(cells),
                "mean_ratio": round(float(np.mean([ratio[y, x] for y, x in cells])), 2),
                "background_ratio": round(float(np.median(ratio)), 2),
            }
        )
    regions.sort(key=lambda region: region["mean_ratio"] * region["blocks"], reverse=True)
    result["regions"] = regions[:3]
    return result


def save_heatmap(path: str | Path, out_path: str | Path) -> Path | None:
    """Write the ghost (or plain re-save) error map for the examiner to eyeball."""
    analysis = jpeg_ghost_analysis(path)
    heat = analysis.get("heatmap")
    if heat is None:
        return None
    peak = float(np.percentile(heat, 99.5)) or 1.0
    scaled = np.clip(heat / peak * 255.0, 0, 255).astype(np.uint8)
    out = Path(out_path)
    Image.fromarray(scaled).convert("RGB").save(out, "PNG")
    return out


def analyze_image(path: str | Path, exhibit_id: str) -> list[Finding]:
    findings: list[Finding] = []
    exif = read_exif(path)

    software = exif.get("Software", "")
    if software and any(hint in software.lower() for hint in EDITOR_HINTS):
        findings.append(
            Finding(
                exhibit_id=exhibit_id,
                analyzer="media",
                signal="editing-software",
                title="Image passed through editing software",
                detail=f"EXIF Software tag reads '{software}'.",
                locator="exif:Software",
                confidence="medium",
                limitations="Shows the file was saved by an editor, not what was changed. Tags can be added or stripped by anyone.",
                data={"software": software},
            )
        )

    captured = _parse_exif_time(exif.get("DateTimeOriginal"))
    modified = _parse_exif_time(exif.get("DateTime"))
    if captured and modified and (modified - captured).total_seconds() > 60:
        findings.append(
            Finding(
                exhibit_id=exhibit_id,
                analyzer="media",
                signal="modified-after-capture",
                title="File was modified after the photo was taken",
                detail=(
                    f"Captured {exif['DateTimeOriginal']} but last modified {exif['DateTime']} "
                    f"({(modified - captured).total_seconds() / 3600:.1f} hours later)."
                ),
                locator="exif:DateTime",
                confidence="medium",
                limitations="Rotating, cropping or exporting a photo can also update this field.",
                data={"captured": exif["DateTimeOriginal"], "modified": exif["DateTime"]},
            )
        )

    if not exif.get("DateTimeOriginal") and not exif.get("Model"):
        findings.append(
            Finding(
                exhibit_id=exhibit_id,
                analyzer="media",
                signal="no-capture-metadata",
                title="No camera capture metadata",
                detail="The file has no capture time or camera model.",
                locator="exif:DateTimeOriginal",
                confidence="low",
                limitations="Messaging apps and screenshots strip metadata all the time, so this alone means very little.",
            )
        )

    ghost = jpeg_ghost_analysis(path)
    if ghost["ghost_quality"]:
        findings.append(
            Finding(
                exhibit_id=exhibit_id,
                analyzer="media",
                signal="double-compression",
                title="Image was saved as JPEG at least twice",
                detail=(
                    f"It still carries an earlier compression around quality {ghost['ghost_quality']} "
                    f"under a final save around quality {ghost['last_quality']}, so it is not a camera original."
                ),
                locator="image",
                confidence="medium",
                limitations="Forwarding, resizing or re-saving a photo in any app also does this. On its own it does not mean the content changed.",
                data={"ghost_quality": ghost["ghost_quality"], "last_quality": ghost["last_quality"], "curve": ghost["curve"]},
            )
        )
    for number, region in enumerate(ghost["regions"], start=1):
        findings.append(
            Finding(
                exhibit_id=exhibit_id,
                analyzer="media",
                signal="compression-inconsistency",
                title=f"Region does not share the rest of the image's compression history (#{number})",
                detail=(
                    f"At x={region['x']}, y={region['y']}, {region['w']}x{region['h']} px the earlier "
                    f"quality-{ghost['ghost_quality']} compression is missing (ghost ratio {region['mean_ratio']} "
                    f"vs {region['background_ratio']} for the image overall), which fits content drawn or pasted "
                    "after the first save."
                ),
                locator=f"region:{region['x']},{region['y']},{region['w']},{region['h']}",
                confidence="medium" if region["mean_ratio"] >= 0.5 else "low",
                limitations="Strong local filters such as sharpening or blur can do this too. Compare the heatmap with the photo.",
                data=region,
            )
        )
    return findings
