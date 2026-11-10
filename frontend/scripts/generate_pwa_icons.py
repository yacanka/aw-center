from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "public" / "app" / "icons"
SOURCE = ROOT / "pwa-source.png"
MASKABLE_SOURCE = ROOT / "pwa-maskable-source.png"


def resized_icon(path: Path, size: int) -> Image.Image:
    with Image.open(path) as source:
        icon = source.convert("RGB")
    if icon.width != icon.height:
        raise ValueError(f"PWA kaynak ikonu kare olmalıdır: {path.name}")
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    icon_512 = resized_icon(SOURCE, 512)
    icon_512.resize((192, 192), Image.Resampling.LANCZOS).save(ROOT / "pwa-192.png")
    icon_512.save(ROOT / "pwa-512.png")
    resized_icon(MASKABLE_SOURCE, 512).save(ROOT / "pwa-maskable-512.png")


if __name__ == "__main__":
    main()
