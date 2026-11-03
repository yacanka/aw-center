"""Reference-shaped ttk controls, without replacing native input behavior.

The tiny RGBA skins are generated locally and stretched by ttk's image element.
Callers must retain the returned images for as long as their widgets exist.
"""

from __future__ import annotations

from itertools import count
import struct
import tkinter as tk
from tkinter import font, ttk
import zlib


_element_ids = count()


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if len(value) != 6:
        raise ValueError("Expected a hexadecimal RGB color")
    try:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        raise ValueError("Expected a hexadecimal RGB color") from None


def _shade(value: str, factor: float) -> str:
    return "#" + "".join(f"{round(component * factor):02x}" for component in _rgb(value))


def _rgba_png(size: int, rows: bytes) -> bytes:
    """Encode square RGBA scanlines with no external image dependency."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data)))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _rounded_png(fill: str, border: str, *, radius: int, border_width: int = 1) -> bytes:
    """Make a nine-slice skin with transparent, antialiased rounded corners."""
    fill_rgb, border_rgb = _rgb(fill), _rgb(border)
    size = radius * 2 + 5

    def inside(x, y, inset):
        edge_radius = max(0, radius - inset)
        if not inset <= x <= size - inset or not inset <= y <= size - inset:
            return False
        closest_x = min(max(x, inset + edge_radius), size - inset - edge_radius)
        closest_y = min(max(y, inset + edge_radius), size - inset - edge_radius)
        return (x - closest_x) ** 2 + (y - closest_y) ** 2 <= edge_radius ** 2

    samples = [((x + .5) / 4, (y + .5) / 4) for y in range(4) for x in range(4)]
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG's unfiltered scanline format.
        for x in range(size):
            outer, inner = 0, 0
            for offset_x, offset_y in samples:
                outer += inside(x + offset_x, y + offset_y, 0)
                inner += inside(x + offset_x, y + offset_y, border_width)
            if not outer:
                rows.extend((0, 0, 0, 0))
                continue
            rows.extend(round((fill_rgb[index] * inner + border_rgb[index] * (outer - inner)) / outer)
                        for index in range(3))
            rows.append(round(255 * outer / 16))

    return _rgba_png(size, rows)


def _icon_png(name: str, color: str, size: int) -> bytes:
    """Rasterize the three small tab symbols as antialiased line geometry."""
    paths = {
        "play": [((5, 3), (13, 8), (5, 13), (5, 3))],
        "package": [((8, 1.75), (13.5, 4.5), (13.5, 11.5), (8, 14.25),
                     (2.5, 11.5), (2.5, 4.5), (8, 1.75)),
                    ((2.5, 4.5), (8, 7.25), (13.5, 4.5)),
                    ((8, 7.25), (8, 14.25)), ((5.25, 3.125), (10.75, 5.875))],
        "file-text": [((3.5, 1.5), (9, 1.5), (12.5, 5), (12.5, 14.5),
                       (3.5, 14.5), (3.5, 1.5)), ((9, 1.5), (9, 5), (12.5, 5)),
                      ((5.5, 8), (10.5, 8)), ((5.5, 10.5), (10.5, 10.5))],
    }
    if name not in paths or not isinstance(size, int) or size < 1:
        raise ValueError("Expected a supported tab icon and a positive pixel size")
    rgb = _rgb(color)
    segments = [(start, end) for path in paths[name] for start, end in zip(path, path[1:])]

    def painted(x, y):
        for (start_x, start_y), (end_x, end_y) in segments:
            dx, dy = end_x - start_x, end_y - start_y
            fraction = min(1, max(0, ((x - start_x) * dx + (y - start_y) * dy) / (dx * dx + dy * dy)))
            if (x - start_x - fraction * dx) ** 2 + (y - start_y - fraction * dy) ** 2 <= .7 ** 2:
                return True
        return False

    scale = 16 / size
    samples = [((x + .5) / 4, (y + .5) / 4) for y in range(4) for x in range(4)]
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            coverage = sum(painted((x + offset_x) * scale, (y + offset_y) * scale)
                           for offset_x, offset_y in samples)
            rows.extend((*rgb, round(255 * coverage / 16)))
    return _rgba_png(size, rows)


def icon_image(root, name: str, color: str, size: int = 16) -> tk.PhotoImage:
    """Return a transparent play/package/file-text icon; the caller retains it."""
    return tk.PhotoImage(master=root, data=_icon_png(name, color, size))


def apply_control_styles(root, style: ttk.Style, palette: dict, *,
                         body_font: font.Font, medium_font: font.Font) -> list[tk.PhotoImage]:
    """Apply rounded light/dark controls while preserving ttk state semantics.

    ``Manager.Segment.TFrame`` supplies the common profile-control surround.
    Its child ``Manager.TRadiobutton`` widgets retain normal radio selection,
    keyboard navigation, and focus behavior without the circular indicator.
    """
    images, cached = [], {}
    prefix = f"Manager.skin{next(_element_ids)}"
    background, surface = palette["background"], palette["surface"]
    foreground, muted = palette["foreground"], palette["muted"]
    border, accent, soft = palette["border"], palette["accent"], palette["soft"]
    primary, on_primary = palette["primary"], palette["on_primary"]

    def image_for(fill, line, radius, width=1):
        key = fill, line, radius, width
        if key not in cached:
            image = tk.PhotoImage(master=root, data=_rounded_png(fill, line, radius=radius, border_width=width))
            cached[key] = image
            images.append(image)
        return cached[key]

    def element(name, radius, normal, variants, *, padding=1):
        name = f"{prefix}.{name}"
        states = [(*state, image_for(*colors, radius, width)) for state, colors, width in variants]
        style.element_create(name, "image", image_for(*normal, radius), *states,
                             border=radius + 1, padding=padding, sticky="nsew")
        return name

    def button_layout(element_name, label="Button"):
        return [(element_name, {"sticky": "nsew", "children": [
            (f"{label}.padding", {"sticky": "nsew", "children": [
                (f"{label}.label", {"sticky": "nsew"})]})]})]

    # The image contributes a 1px content inset. Distribute the remaining
    # padding to make normal text controls 36px high, then grow with large fonts.
    vertical_space = max(14, 34 - body_font.metrics("linespace"))
    padding = (13, vertical_space // 2, 13, vertical_space - vertical_space // 2)
    neutral = element("Button", 7, (surface, border), [
        (("disabled",), (background, border), 1),
        (("pressed", "focus"), (soft, accent), 2),
        (("active", "focus"), (background, accent), 2),
        (("focus",), (surface, accent), 2),
        (("pressed",), (soft, border), 1),
        (("active",), (background, border), 1),
    ])
    for name in ("TButton", "Manager.TButton"):
        style.layout(name, button_layout(neutral))
        style.configure(name, font=body_font, padding=padding, width=0, anchor="center",
                        relief="flat", background=surface, foreground=foreground, bordercolor=border)
        style.map(name, background=[("disabled", background), ("pressed", soft), ("active", background)],
                  foreground=[("disabled", muted)], bordercolor=[("disabled", border), ("focus", accent)])

    hover, pressed = _shade(primary, .94), _shade(primary, .87)
    primary_element = element("Primary", 7, (primary, primary), [
        (("disabled",), (background, border), 1),
        (("pressed", "focus"), (pressed, foreground), 2),
        (("active", "focus"), (hover, foreground), 2),
        (("focus",), (primary, foreground), 2),
        (("pressed",), (pressed, pressed), 1),
        (("active",), (hover, hover), 1),
    ])
    style.layout("Manager.Primary.TButton", button_layout(primary_element))
    style.configure("Manager.Primary.TButton", font=medium_font, padding=padding,
                    foreground=on_primary, background=primary, bordercolor=primary, width=0)
    style.map("Manager.Primary.TButton", foreground=[("disabled", muted)],
              background=[("disabled", background), ("pressed", pressed), ("active", hover)],
              bordercolor=[("disabled", border), ("focus", foreground), ("pressed", pressed), ("active", hover)])

    entry = element("Entry", 6, (surface, border), [
        (("disabled",), (background, border), 1),
        (("readonly", "focus"), (background, accent), 2),
        (("focus",), (surface, accent), 2),
        (("readonly",), (background, border), 1),
    ])
    style.layout("TEntry", [(entry, {"sticky": "nsew", "children": [
        ("Entry.padding", {"sticky": "nsew", "children": [
            ("Entry.textarea", {"sticky": "nsew"})]})]})])
    # Unlike ttk labels/buttons, Entry has a widget-level font default which
    # wins over the style. Set its option database default before construction.
    root.option_add("*TEntry.font", str(body_font))
    style.configure("TEntry", font=body_font, padding=(10, padding[1], 10, padding[3]),
                    fieldbackground=surface, foreground=foreground, insertcolor=foreground,
                    bordercolor=border, selectbackground=primary, selectforeground=on_primary)
    style.map("TEntry", foreground=[("disabled", muted), ("readonly", foreground)],
              fieldbackground=[("disabled", background), ("readonly", background)],
              bordercolor=[("disabled", border), ("focus", accent)])

    segment = element("Segment", 8, (background, border), [], padding=3)
    style.layout("Manager.Segment.TFrame", [(segment, {"sticky": "nsew"})])
    style.configure("Manager.Segment.TFrame", background=background, bordercolor=border)
    radio = element("Radio", 5, (background, background), [
        (("disabled", "selected"), (surface, border), 1),
        (("disabled",), (background, background), 1),
        (("pressed", "focus"), (soft, accent), 2),
        (("selected", "focus"), (surface, accent), 2),
        (("focus",), (background, accent), 2),
        (("pressed",), (soft, border), 1),
        (("selected",), (surface, border), 1),
        (("active",), (surface, surface), 1),
    ])
    style.layout("Manager.TRadiobutton", button_layout(radio, "Radiobutton"))
    style.configure("Manager.TRadiobutton", font=body_font, padding=(13, 5),
                    foreground=muted, background=background, bordercolor=background)
    style.map("Manager.TRadiobutton", foreground=[("disabled", muted), ("selected", foreground)],
              background=[("disabled", "selected", surface), ("disabled", background),
                          ("pressed", soft), ("selected", surface), ("active", surface)],
              bordercolor=[("disabled", "selected", border), ("disabled", background),
                           ("focus", accent), ("selected", border)])

    link = element("Link", 7, (surface, surface), [
        (("disabled",), (surface, surface), 1),
        (("pressed", "focus"), (soft, accent), 2),
        (("active", "focus"), (background, accent), 2),
        (("focus",), (surface, accent), 2),
        (("pressed",), (soft, soft), 1),
        (("active",), (background, background), 1),
    ])
    style.layout("Manager.Link.TButton", button_layout(link))
    style.configure("Manager.Link.TButton", font=body_font, padding=(0, 4), width=0,
                    foreground=muted, background=surface, bordercolor=surface, anchor="w")
    style.map("Manager.Link.TButton", foreground=[("disabled", muted), ("active", foreground)],
              background=[("disabled", surface), ("pressed", soft), ("active", background)],
              bordercolor=[("disabled", surface), ("focus", accent)])
    return images
