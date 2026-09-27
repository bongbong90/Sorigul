"""Apply the approved pixel-native Sorigul glyph to small Windows icon surfaces.

Run this after the official ``npx tauri icon`` command. The 256px ICO frame and
all large PNG assets remain generated from the transparent canonical derivative.
Only 16-64px frames and equivalent small Appx PNGs are replaced. Their compact
geometry prevents the waveform-to-text contract from disappearing after Windows
downsampling, while the one-pixel Primary Soft underlay preserves contrast on
dark taskbar and tray surfaces without adding a background tile.
"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import struct

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = REPO_ROOT / "frontend/src-tauri/icons"
CANONICAL = REPO_ROOT / "docs/design/reference/app-icon-v1.png"
TRANSPARENT_RUNTIME = (
    REPO_ROOT / "docs/design/reference/app-icon-v1-transparent-runtime.png"
)

EXPECTED_CANONICAL_SHA256 = (
    "38ca2d8f0aec3409cf9a57f60ed86d26881eace76476803a05c4ffa7a8fab612"
)
EXPECTED_RUNTIME_SHA256 = (
    "07577961e495d1dbc786b7b5367f3cdc67731f3f9c91bd37ca8a92c33f62819a"
)

QUIET_TEAL = (62, 104, 116)  # #3E6874
PRIMARY_SOFT = (220, 233, 233)  # #DCE9E9
SMALL_PNGS = (
    "32x32.png",
    "64x64.png",
    "Square30x30Logo.png",
    "Square44x44Logo.png",
    "StoreLogo.png",
)
EXPECTED_ICO_SIZES = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)}


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def verify_sources() -> None:
    checks = (
        (CANONICAL, EXPECTED_CANONICAL_SHA256),
        (TRANSPARENT_RUNTIME, EXPECTED_RUNTIME_SHA256),
    )
    for path, expected in checks:
        actual = file_sha256(path)
        if actual != expected:
            raise RuntimeError(
                f"source hash mismatch: {path.relative_to(REPO_ROOT)} "
                f"expected={expected} actual={actual}"
            )


def small_surface_glyph(size: int) -> Image.Image:
    """Render Audio Waveform -> Text Lines on an RGBA transparent canvas."""

    core = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    underlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    bar_width = max(1, round(size * 0.075))
    center_y = size // 2
    bar_centers = [round(size * ratio) for ratio in (0.08, 0.17, 0.26, 0.35, 0.44)]
    bar_heights = [
        max(3, round(size * ratio))
        for ratio in (0.28, 0.52, 0.78, 0.52, 0.28)
    ]

    line_left = round(size * 0.57)
    line_right = size - max(1, round(size * 0.06))
    line_height = max(2, round(size * 0.09))
    line_centers = [round(size * ratio) for ratio in (0.27, 0.50, 0.73)]

    for layer, color, offset in (
        (underlay, PRIMARY_SOFT, 1),
        (core, QUIET_TEAL, 0),
    ):
        draw = ImageDraw.Draw(layer)
        for x, height in zip(bar_centers, bar_heights):
            draw.rounded_rectangle(
                (
                    x - bar_width // 2 + offset,
                    center_y - height // 2 + offset,
                    x - bar_width // 2 + bar_width - 1 + offset,
                    center_y - height // 2 + height - 1 + offset,
                ),
                radius=max(0, bar_width // 2),
                fill=(*color, 255),
            )
        for y in line_centers:
            draw.rounded_rectangle(
                (
                    line_left + offset,
                    y - line_height // 2 + offset,
                    line_right + offset,
                    y - line_height // 2 + line_height - 1 + offset,
                ),
                radius=line_height // 2,
                fill=(*color, 255),
            )

    underlay.alpha_composite(core)
    return underlay


def write_small_pngs() -> None:
    for name in SMALL_PNGS:
        path = ICON_DIR / name
        with Image.open(path) as image:
            if image.width != image.height:
                raise RuntimeError(f"expected square PNG: {path}")
            size = image.width
        small_surface_glyph(size).save(path, optimize=True)
        print(f"small-surface PNG: {path.relative_to(REPO_ROOT)}")


def write_ico() -> None:
    ico_path = ICON_DIR / "icon.ico"
    with Image.open(ico_path) as ico:
        sizes = set(ico.ico.sizes())
        if sizes != EXPECTED_ICO_SIZES:
            raise RuntimeError(f"unexpected ICO sizes: {sorted(sizes)}")

        frames: list[tuple[tuple[int, int], bytes]] = []
        for size in sorted(sizes):
            frame = ico.ico.getimage(size).convert("RGBA")
            if size[0] <= 64:
                frame = small_surface_glyph(size[0])
            stream = BytesIO()
            frame.save(stream, format="PNG", optimize=True)
            frames.append((size, stream.getvalue()))

    header_size = 6 + 16 * len(frames)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    payload = bytearray()
    offset = header_size
    for (width, height), frame_data in frames:
        directory.extend(
            struct.pack(
                "<BBBBHHII",
                0 if width == 256 else width,
                0 if height == 256 else height,
                0,
                0,
                0,
                32,
                len(frame_data),
                offset,
            )
        )
        payload.extend(frame_data)
        offset += len(frame_data)

    ico_path.write_bytes(directory + payload)
    print(f"small-surface ICO: {ico_path.relative_to(REPO_ROOT)} {sorted(EXPECTED_ICO_SIZES)}")


def main() -> None:
    verify_sources()
    write_small_pngs()
    write_ico()


if __name__ == "__main__":
    main()
