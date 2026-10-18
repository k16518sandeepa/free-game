#!/usr/bin/env python3
"""Generate MPM launcher + notification icons for a Flutter Android project.

usage: make_icons.py <flutter_project_dir>

- If <project>/assets/logo.png exists (square, ideally 512px+), it is used as the app logo/icon.
- Otherwise a red "M" monogram in MPM brand red is generated and written to assets/logo.png.
- The notification (status bar) icon is always a white "M" silhouette, because Android
  requires a single-colour transparent icon there.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_RED = (229, 0, 0, 255)
DARK_BG = "#0B0B0F"
RED_HEX = "#E50000"

M_POINTS = [
    (0.12, 0.80), (0.12, 0.20), (0.30, 0.20), (0.50, 0.52), (0.70, 0.20),
    (0.88, 0.20), (0.88, 0.80), (0.72, 0.80), (0.72, 0.46), (0.54, 0.76),
    (0.46, 0.76), (0.28, 0.46), (0.28, 0.80),
]

SS = 4  # supersampling factor for smooth edges


def draw_m(size, fill=(255, 255, 255, 255), scale=1.0):
    """White (or custom) M on a transparent square canvas; `scale` shrinks it toward the centre."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (255, 255, 255, 0))  # white-transparent avoids dark fringes when resizing
    d = ImageDraw.Draw(img)
    pts = [((0.5 + (x - 0.5) * scale) * big, (0.5 + (y - 0.5) * scale) * big) for x, y in M_POINTS]
    d.polygon(pts, fill=fill)
    return img.resize((size, size), Image.LANCZOS)


def brand_logo(size):
    """Red rounded square with a white M."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=BRAND_RED)
    img = img.resize((size, size), Image.LANCZOS)
    img.alpha_composite(draw_m(size, scale=0.9))
    return img


def fit_logo(logo, size):
    return logo.resize((size, size), Image.LANCZOS)


def main(proj):
    proj = Path(proj)
    res = proj / "android" / "app" / "src" / "main" / "res"
    assets = proj / "assets"
    assets.mkdir(exist_ok=True)

    logo_path = assets / "logo.png"
    provided = logo_path.exists()
    if provided:
        logo = Image.open(logo_path).convert("RGBA")
        w, h = logo.size
        side = min(w, h)  # centre-crop to square
        logo = logo.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
        logo.save(logo_path)
        print(f"Using provided logo ({side}px)")
    else:
        logo = brand_logo(512)
        logo.save(logo_path)
        print("No assets/logo.png found, generated M monogram placeholder")

    # Legacy launcher icons (used below Android 8) + adaptive foreground/monochrome layers
    legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for dens, px in legacy.items():
        d = res / f"mipmap-{dens}"
        d.mkdir(parents=True, exist_ok=True)
        fit_logo(logo, px).save(d / "ic_launcher.png")

        fg_px = round(px * 108 / 48)
        layer = Image.new("RGBA", (fg_px, fg_px), (0, 0, 0, 0))
        if provided:
            inner = round(fg_px * 0.66)
            layer.alpha_composite(fit_logo(logo, inner), ((fg_px - inner) // 2, (fg_px - inner) // 2))
        else:
            layer = draw_m(fg_px, scale=0.62)
        layer.save(d / "ic_launcher_foreground.png")
        draw_m(fg_px, scale=0.62).save(d / "ic_launcher_monochrome.png")

    any_dir = res / "mipmap-anydpi-v26"
    any_dir.mkdir(parents=True, exist_ok=True)
    (any_dir / "ic_launcher.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
        '    <monochrome android:drawable="@mipmap/ic_launcher_monochrome"/>\n'
        "</adaptive-icon>\n"
    )

    # Status-bar notification icon: white M silhouette on transparent
    for dens, px in {"mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96}.items():
        d = res / f"drawable-{dens}"
        d.mkdir(parents=True, exist_ok=True)
        draw_m(px, scale=1.0).save(d / "ic_notification.png")

    values = res / "values"
    values.mkdir(parents=True, exist_ok=True)
    bg = DARK_BG if provided else RED_HEX
    (values / "mpm_colors.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        f'    <color name="ic_launcher_background">{bg}</color>\n'
        f'    <color name="mpm_notification">{RED_HEX}</color>\n'
        "</resources>\n"
    )

    # Manifest: default notification icon + accent colour for Firebase push
    manifest = proj / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    text = manifest.read_text("utf-8")
    if "default_notification_icon" not in text:
        meta = (
            '    <meta-data android:name="com.google.firebase.messaging.default_notification_icon"\n'
            '        android:resource="@drawable/ic_notification"/>\n'
            '    <meta-data android:name="com.google.firebase.messaging.default_notification_color"\n'
            '        android:resource="@color/mpm_notification"/>\n'
        )
        if "</application>" not in text:
            sys.exit("AndroidManifest.xml has no </application>")
        manifest.write_text(text.replace("</application>", meta + "    </application>", 1), "utf-8")
        print("Manifest patched")
    print("Icons written")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
