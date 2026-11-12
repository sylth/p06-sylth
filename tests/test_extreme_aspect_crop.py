# -*- coding: utf-8 -*-

"""Regression test for extreme aspect ratio resizing (issue #4).

Three symptoms, all from the same root cause: ``Transformer`` can compute a
zero-length crop or resize dimension when the target aspect ratio is far from
the source's, producing an empty image (every pixel fully transparent) or,
once that empty image reaches ``has_transparency()``, a hard failure.

The source pictures are built in memory so the test does not depend on any
fixture file.
"""

from io import BytesIO

from PIL import Image
from tornado.testing import gen_test

from tests.base import TestCase
from thumbor.config import Config
from thumbor.context import Context, RequestParameters
from thumbor.engines.pil import Engine as PilEngine
from thumbor.importer import Importer
from thumbor.transformer import Transformer

# The source picture is a transparent canvas with opaque vertical bars, so
# a result that lost its content is distinguishable from a real render.
BAR_COLORS = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]


def make_source(width, height):
    """Build a transparent source image with opaque vertical bars."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    bar_width = max(width // len(BAR_COLORS), 1)

    for x in range(width):
        color = BAR_COLORS[min(x // bar_width, len(BAR_COLORS) - 1)]
        for y in range(height):
            pixels[x, y] = color

    return image


def to_png_bytes(image):
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def has_content(image):
    """True when at least one pixel is not fully transparent."""
    return any(pixel[3] > 0 for pixel in image.convert("RGBA").getdata())


class ExtremeAspectCropTestCase(TestCase):
    def get_context(self):
        config = Config(
            SECURITY_KEY="ACME-SEC",
            LOADER="thumbor.loaders.file_loader",
            STORAGE="thumbor.storages.no_storage",
            ENGINE="thumbor.engines.pil",
        )
        importer = Importer(config)
        importer.import_modules()

        context = Context(config=config, importer=importer)
        context.modules.engine = PilEngine(context)
        context.request = RequestParameters()

        return context

    async def transform(self, source, width, height, fit_in=False):
        """Load ``source`` and run the pipeline for the requested size."""
        context = self.get_context()
        engine = context.modules.engine
        engine.load(to_png_bytes(source), ".png")

        context.request.engine = engine
        context.request.engine.extension = ".png"
        context.request.width = width
        context.request.height = height
        context.request.fit_in = fit_in
        context.request.adaptive = False
        context.request.full = False
        context.request.stretch = False
        context.request.smart = False
        context.request.filters = []
        context.request.focal_points = []

        transformer = Transformer(context)
        await transformer.transform()

        return engine.image

    @gen_test
    async def test_wide_and_short_resize_returns_real_image(self):
        # A 16x16 source asked for 800x20 must keep visible content.
        result = await self.transform(make_source(16, 16), 800, 20)

        assert result.size == (800, 20)
        assert has_content(result), (
            "800x20 result from a 16x16 source is fully transparent"
        )

    @gen_test
    async def test_fit_in_1x1_returns_image_instead_of_raising(self):
        # A very wide source fitted into a 1x1 box must not raise.
        result = await self.transform(make_source(940, 2), 1, 1, fit_in=True)

        assert result.size == (1, 1)
        assert has_content(result), (
            "fit-in/1x1 result from a 940x2 source is fully transparent"
        )

    @gen_test
    async def test_fit_in_width_only_returns_image_instead_of_raising(self):
        # A width-only fit-in request must not raise.
        result = await self.transform(make_source(940, 2), 100, 0, fit_in=True)

        assert result.size == (100, 1)
        assert has_content(result), (
            "fit-in/100x0 result from a 940x2 source is fully transparent"
        )