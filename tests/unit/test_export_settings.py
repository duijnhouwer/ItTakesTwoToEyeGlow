import pytest
from eyeglow_egobody.model.export_settings import VideoSettings

@pytest.mark.parametrize('fps',[0,121,float('nan'),float('inf')])
def test_invalid_fps(fps):
    with pytest.raises(ValueError):
        VideoSettings(fps=fps)

@pytest.mark.parametrize('quality',[-1,101,1.5])
def test_invalid_quality(quality):
    with pytest.raises(ValueError):
        VideoSettings(quality=quality)


def test_quality_maps_monotonically_to_encoder_crf():
    assert VideoSettings(quality=100).crf == 0
    assert VideoSettings(quality=0).crf == 51
    assert VideoSettings(quality=90).crf < VideoSettings(quality=50).crf
