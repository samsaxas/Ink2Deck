import io
import os
import sys

import pytest
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))
from evaluate import cer, wer
from ocr_utils import (
    GeminiExtractionError,
    create_pdf,
    create_ppt_with_text_and_image,
    extract_text,
    to_rgb,
)


def make_image(mode="RGB"):
    return Image.new("RGB", (320, 160), "white").convert(mode)


def test_extract_text_raises_when_gemini_fails(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(
        "ocr_utils.extract_text_with_gemini",
        lambda *a, **k: (_ for _ in ()).throw(GeminiExtractionError("quota exhausted")),
    )
    with pytest.raises(GeminiExtractionError):
        extract_text(make_image())


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P"])
def test_image_modes_convert_to_rgb(mode):
    assert to_rgb(make_image(mode)).mode == "RGB"


def test_pdf_handles_unicode_and_returns_bytes():
    data = create_pdf("Equation: x² ≥ 5 → done\nλ = 2")
    assert isinstance(data, bytes) and data.startswith(b"%PDF")


def test_pptx_has_title_image_and_text_slides():
    from pptx import Presentation
    stream = create_ppt_with_text_and_image("First point\n\nSecond point", make_image("RGBA"))
    assert len(Presentation(io.BytesIO(stream.read())).slides) == 4


def test_error_rate_metrics():
    assert cer("hello world", "hello world") == 0
    assert wer("a b c d", "a b x d") == 0.25
