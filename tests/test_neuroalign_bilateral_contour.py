import numpy as np

from neuroalign_step_worker import bilateral_outer_contour


def test_bilateral_outer_contour_keeps_both_hemispheres_and_fissure():
    mask = np.zeros((120, 140), dtype=np.uint8)
    mask[12:108, 8:64] = 1
    mask[16:104, 76:132] = 1
    contour = bilateral_outer_contour(mask)
    x0, y0 = np.min(contour, axis=0)
    x1, y1 = np.max(contour, axis=0)

    assert x0 <= 8
    assert x1 >= 131
    assert y0 <= 12
    assert y1 >= 103
    assert x1 - x0 > 110


def test_bilateral_outer_contour_does_not_modify_saved_subject_mask(tmp_path):
    mask = np.zeros((80, 100), dtype=np.uint8)
    mask[8:72, 6:43] = 1
    mask[10:70, 57:94] = 1
    original = mask.copy()

    _ = bilateral_outer_contour(mask)

    assert np.array_equal(mask, original)
