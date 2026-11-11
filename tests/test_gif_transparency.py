import io
import unittest

from PIL import Image

from thumbor.config import Config
from thumbor.context import Context
from thumbor.engines.pil import Engine


def make_palette_gif():
    # Index 0 is the transparent entry, index 1 is blue.
    img = Image.new("P", (40, 40), 1)
    img.putpalette([0, 0, 0, 0, 0, 255] + [0, 0, 0] * 254)
    for x in range(20):
        for y in range(40):
            img.putpixel((x, y), 0)
    buf = io.BytesIO()
    img.save(buf, "GIF", transparency=0)
    return buf.getvalue()


class GifTransparencyTestCase(unittest.TestCase):
    def test_resized_gif_keeps_transparent_index(self):
        context = Context(config=Config())
        engine = Engine(context)
        engine.load(make_palette_gif(), ".gif")
        engine.resize(20, 20)
        out = Image.open(io.BytesIO(engine.read(".gif")))

        self.assertIsNotNone(
            out.info.get("transparency"),
            "resized GIF lost its transparency index",
        )
        transparent_index = out.info["transparency"]
        indexes = list(out.convert("P").getdata())
        self.assertGreater(
            indexes.count(transparent_index),
            0,
            "no pixels use the transparent index",
        )
