import asyncio
import io
import unittest

from PIL import Image

from thumbor.config import Config
from thumbor.context import Context
from thumbor.engines.pil import Engine
from thumbor.filters.round_corner import Filter

SOURCE = "course/images/example.jpg"
CORNER = 60
MIN_RATIO = 0.6
MAX_CHANNEL_DIFF = 40
SEARCH_STEPS = 3


def render_round_corner_png():
    Filter.pre_compile()
    context = Context(config=Config())
    engine = Engine(context)
    with open(SOURCE, "rb") as handle:
        engine.load(handle.read(), ".jpg")
    engine.resize(300, 200)
    filter_instance = Filter("round_corner(60,255,255,255,1)", context)
    filter_instance.engine = engine
    asyncio.run(filter_instance.round_corner(*filter_instance.params))
    return engine.read(".png")


def neighbours(image, x, y):
    width, height = image.size
    found = []
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            found.append(image.getpixel((nx, ny)))
    return found


def nearest_opaque(image, x, y):
    width, height = image.size
    for step in range(1, SEARCH_STEPS + 1):
        for dx, dy in ((step, 0), (0, step), (-step, 0), (0, -step)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                pixel = image.getpixel((nx, ny))
                if pixel[3] == 255:
                    return pixel
    return None


class RoundCornerFringeTestCase(unittest.TestCase):
    def test_arc_edge_fades_without_dark_ring_or_whitening(self):
        image = Image.open(io.BytesIO(render_round_corner_png())).convert(
            "RGBA"
        )
        self.assertLess(
            image.getpixel((0, 0))[3], 255, "corner should be transparent"
        )

        edge_count = 0
        dark_edges = []
        colour_edges = []
        for y in range(CORNER):
            for x in range(CORNER):
                pixel = image.getpixel((x, y))
                if pixel[3] != 255:
                    continue
                around = neighbours(image, x, y)
                if not any(p[3] < 255 for p in around):
                    continue
                opaque = [p for p in around if p[3] == 255]
                if not opaque:
                    continue
                edge_count += 1
                edge_sum = sum(pixel[:3])
                best = max(sum(p[:3]) for p in opaque)
                if edge_sum < MIN_RATIO * best:
                    dark_edges.append((x, y, pixel[:3], best))

        for y in range(CORNER):
            for x in range(CORNER):
                pixel = image.getpixel((x, y))
                if not 0 < pixel[3] < 255:
                    continue
                source = nearest_opaque(image, x, y)
                if source is None:
                    continue
                diff = max(abs(a - b) for a, b in zip(pixel[:3], source[:3]))
                if diff > MAX_CHANNEL_DIFF:
                    colour_edges.append((x, y, pixel, source))

        self.assertGreater(edge_count, 0, "expected arc edge pixels")
        self.assertFalse(
            dark_edges,
            f"{len(dark_edges)} of {edge_count} arc edge pixels are much "
            f"darker than their neighbours (dark ring), first: "
            f"{dark_edges[:3]}",
        )
        self.assertFalse(
            colour_edges,
            f"{len(colour_edges)} partly transparent arc pixels differ from "
            f"the nearest opaque pixel by more than {MAX_CHANNEL_DIFF} per "
            f"channel (edge not keeping source colour), first: "
            f"{colour_edges[:3]}",
        )
