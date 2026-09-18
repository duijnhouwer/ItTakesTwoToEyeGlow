import numpy as np
from PIL import Image
import pytest
from eyeglow_egobody.export.animation import ImageWriter


def test_writer_and_overwrite_protection(tmp_path):
    writer = ImageWriter()
    path = tmp_path/'frame.png'
    try:
        writer.submit(np.full((20,30,3),127,dtype=np.uint8),path).result(timeout=5)
        with Image.open(path) as image:
            assert image.size == (30,20)
        with pytest.raises(FileExistsError):
            writer.submit(np.zeros((20,30,3),dtype=np.uint8),path).result(timeout=5)
    finally:
        writer.close()
