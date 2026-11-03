"""Rounded control artwork and native ttk interaction coverage."""

import struct
import unittest
import zlib

from scripts.manager import view_theme


LIGHT = {
    "background": "#f5f6f7", "surface": "#ffffff", "foreground": "#20262c",
    "muted": "#626c76", "border": "#e3e7e9", "accent": "#147d53",
    "primary": "#147d53", "on_primary": "#ffffff", "soft": "#eaf6f0",
}
DARK = {
    "background": "#17191c", "surface": "#212428", "foreground": "#edf0f2",
    "muted": "#aab2ba", "border": "#363b40", "accent": "#63d8a7",
    "primary": "#2aa675", "on_primary": "#071e14", "soft": "#1d382c",
}


def png_pixels(data):
    """Decode the generated unfiltered RGBA rows without an imaging package."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("Invalid PNG signature")
    offset, compressed, size = 8, bytearray(), None
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        checksum = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + payload) != checksum:
            raise AssertionError("Invalid PNG chunk checksum")
        if kind == b"IHDR":
            width, height, depth, mode, *_ = struct.unpack(">IIBBBBB", payload)
            if (depth, mode) != (8, 6):
                raise AssertionError("Expected RGBA PNG")
            size = width, height
        elif kind == b"IDAT":
            compressed.extend(payload)
        offset += length + 12
    width, height = size
    raw, rows = zlib.decompress(compressed), []
    for row in range(height):
        start = row * (width * 4 + 1)
        if raw[start] != 0:
            raise AssertionError("Unexpected PNG row filter")
        pixels = raw[start + 1:start + 1 + width * 4]
        rows.append([tuple(pixels[index:index + 4]) for index in range(0, len(pixels), 4)])
    return rows


class RoundedArtworkTests(unittest.TestCase):
    def test_button_skin_has_transparent_corners_opaque_fill_and_antialiased_edges(self):
        pixels = png_pixels(view_theme._rounded_png("#ffffff", "#20262c", radius=7))
        middle = len(pixels) // 2
        self.assertEqual(pixels[0][0][3], 0)
        self.assertEqual(pixels[middle][middle], (255, 255, 255, 255))
        self.assertEqual(pixels[0][middle], (32, 38, 44, 255))
        self.assertTrue(any(0 < pixel[3] < 255 for row in pixels for pixel in row))

    def test_focus_skin_paints_two_border_pixels_without_filling_the_corner(self):
        pixels = png_pixels(view_theme._rounded_png("#212428", "#63d8a7", radius=6, border_width=2))
        middle = len(pixels) // 2
        self.assertEqual(pixels[0][0][3], 0)
        self.assertEqual(pixels[1][middle], (99, 216, 167, 255))
        self.assertEqual(pixels[2][middle], (33, 36, 40, 255))

    def test_short_hex_colors_are_supported_and_invalid_colors_are_rejected(self):
        pixels = png_pixels(view_theme._rounded_png("#fff", "#000", radius=6))
        self.assertEqual(pixels[len(pixels) // 2][len(pixels) // 2], (255, 255, 255, 255))
        with self.assertRaises(ValueError):
            view_theme._rounded_png("not-a-color", "#000000", radius=6)


class TabIconArtworkTests(unittest.TestCase):
    def test_tab_icons_have_transparent_backgrounds_and_requested_stroke_color(self):
        shapes = []
        for name in ("play", "package", "file-text"):
            with self.subTest(icon=name):
                pixels = png_pixels(view_theme._icon_png(name, "#147d53", 16))
                self.assertEqual((len(pixels), len(pixels[0])), (16, 16))
                self.assertEqual(pixels[0][0][3], 0)
                painted = [pixel for row in pixels for pixel in row if pixel[3]]
                self.assertTrue(painted)
                self.assertTrue(all(pixel[:3] == (20, 125, 83) for pixel in painted))
                shapes.append(pixels)
        self.assertNotEqual(shapes[0], shapes[1])
        self.assertNotEqual(shapes[1], shapes[2])

    def test_icons_scale_and_keep_the_play_triangle_unfilled(self):
        pixels = png_pixels(view_theme._icon_png("play", "#63d8a7", 32))
        self.assertEqual(len(pixels), 32)
        self.assertEqual(pixels[16][16][3], 0)
        self.assertGreater(pixels[16][10][3], 0)
        with self.assertRaises(ValueError):
            view_theme._icon_png("unknown", "#fff", 16)
        with self.assertRaises(ValueError):
            view_theme._icon_png("play", "#fff", 0)


class NativeControlThemeTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import font, ttk
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self.body = font.nametofont("TkDefaultFont", root=self.root).copy()
        self.body.configure(size=-13)
        self.medium = self.body.copy()
        self.medium.configure(weight="bold")

    def apply(self, palette):
        self.images = view_theme.apply_control_styles(
            self.root, self.style, palette, body_font=self.body, medium_font=self.medium)

    def test_both_palettes_keep_control_states_and_focus_distinct(self):
        for palette in (LIGHT, DARK):
            with self.subTest(palette=palette["background"]):
                self.apply(palette)
                self.assertTrue(self.images)
                self.assertTrue(all(self.root.tk.call("image", "type", str(image)) == "photo"
                                    for image in self.images))
                for name in ("TButton", "Manager.Primary.TButton", "TEntry", "Manager.TRadiobutton"):
                    self.assertNotEqual(self.style.lookup(name, "bordercolor"),
                                        self.style.lookup(name, "bordercolor", ("focus",)), name)
                self.assertEqual(self.style.lookup("Manager.Primary.TButton", "background"), palette["primary"])
                self.assertNotEqual(self.style.lookup("Manager.Primary.TButton", "background", ("active",)), palette["primary"])
                self.assertNotEqual(self.style.lookup("Manager.Primary.TButton", "background", ("pressed",)),
                                    self.style.lookup("Manager.Primary.TButton", "background", ("active",)))
                self.assertEqual(self.style.lookup("TEntry", "foreground", ("readonly",)), palette["foreground"])
                self.assertEqual(self.style.lookup("TEntry", "foreground", ("disabled",)), palette["muted"])
                self.assertEqual(self.style.lookup("Manager.TRadiobutton", "background", ("selected",)), palette["surface"])
                self.assertEqual(self.style.lookup("Manager.TRadiobutton", "bordercolor", ("selected",)), palette["border"])

    def test_native_controls_retain_editing_radio_selection_and_disabled_invocation(self):
        import tkinter as tk
        from tkinter import ttk
        self.apply(LIGHT)
        entry = ttk.Entry(self.root)
        entry.insert(0, "C:/AWCenter/source")
        entry.state(["readonly"])
        entry.insert("end", "ignored")
        self.assertEqual(entry.get(), "C:/AWCenter/source")
        profile = tk.StringVar(self.root, value="dev")
        radio = ttk.Radiobutton(self.root, text="Üretim", variable=profile, value="prod",
                                style="Manager.TRadiobutton", takefocus=True)
        radio.invoke()
        self.assertEqual(profile.get(), "prod")
        self.assertIn("selected", radio.state())
        radio.state(["disabled"])
        profile.set("dev")
        radio.invoke()
        self.assertEqual(profile.get(), "dev")
        self.assertNotIn("Radiobutton.indicator", str(self.style.layout("Manager.TRadiobutton")))
        self.assertIn("Entry.textarea", str(self.style.layout("TEntry")))

    def test_reference_controls_have_a_36_pixel_minimum_at_normal_text_size(self):
        from tkinter import ttk
        self.apply(LIGHT)
        controls = [ttk.Entry(self.root), ttk.Button(self.root, text="Seç"),
                    ttk.Button(self.root, text="Tarayıcıda aç", style="Manager.Primary.TButton")]
        for control in controls:
            control.pack()
        self.root.update_idletasks()
        for control in controls:
            with self.subTest(widget=control.winfo_class()):
                self.assertGreaterEqual(control.winfo_reqheight(), 36)
                self.assertLessEqual(control.winfo_reqheight(), 38)

    def test_reapplying_theme_keeps_previous_windows_image_elements_valid(self):
        from tkinter import ttk
        self.apply(LIGHT)
        first_images = self.images
        first = ttk.Button(self.root, text="Başlat", style="Manager.Primary.TButton")
        first.pack()
        self.apply(DARK)
        second = ttk.Button(self.root, text="Durdur", style="Manager.Primary.TButton")
        second.pack()
        self.root.update_idletasks()
        self.assertTrue(all(self.root.tk.call("image", "type", str(image)) == "photo"
                            for image in first_images + self.images))
        self.assertGreater(first.winfo_reqheight(), 0)
        self.assertGreater(second.winfo_reqheight(), 0)

    def test_entry_uses_supplied_body_font_and_grows_for_larger_text(self):
        from tkinter import font, ttk
        self.body.configure(size=-25)
        self.medium.configure(size=-25)
        self.apply(DARK)
        entry = ttk.Entry(self.root)
        button = ttk.Button(self.root, text="Başlat")
        entry.pack()
        button.pack()
        self.root.update_idletasks()
        rendered = font.Font(root=self.root, font=entry.cget("font"))
        self.assertEqual(rendered.metrics("linespace"), self.body.metrics("linespace"))
        self.assertGreaterEqual(entry.winfo_reqheight(), self.body.metrics("linespace") + 14)
        self.assertGreaterEqual(button.winfo_reqheight(), self.body.metrics("linespace") + 14)

    def test_tab_icon_api_returns_native_transparent_photos(self):
        self.icons = [view_theme.icon_image(self.root, name, DARK["accent"], size=16)
                      for name in ("play", "package", "file-text")]
        for image in self.icons:
            self.assertEqual((image.width(), image.height()), (16, 16))
            self.assertTrue(image.transparency_get(0, 0))


if __name__ == "__main__":
    unittest.main()
