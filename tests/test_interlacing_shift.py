import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

import analysis_core as core


def _smooth_test_image(height=32, width=48, seed=7):
    rng = np.random.default_rng(seed)
    image = gaussian_filter(rng.normal(size=(height, width)).astype(np.float32), sigma=(2.0, 2.0))
    image -= float(image.min())
    image /= float(image.max() - image.min())
    return (image * 1000.0).astype(np.float32)


def _tdms_string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def _tdms_property(name: str, type_id: int, value) -> bytes:
    out = bytearray()
    out += _tdms_string(name)
    out += struct.pack("<I", type_id)
    if type_id == 0x20:
        out += _tdms_string(str(value))
    elif type_id == 3:
        out += struct.pack("<i", int(value))
    else:
        raise ValueError(type_id)
    return bytes(out)


def _write_test_tdms(path: Path, frames: list[np.ndarray]) -> None:
    height, width = frames[0].shape
    metadata = bytearray()
    metadata += struct.pack("<I", width + 2)
    metadata += _tdms_string("/")
    metadata += struct.pack("<I", 0xFFFFFFFF)
    metadata += struct.pack("<I", 1)
    metadata += _tdms_property("name", 0x20, "data_real-time imaging")
    metadata += _tdms_string("/'Untitled'")
    metadata += struct.pack("<I", 0xFFFFFFFF)
    metadata += struct.pack("<I", 0)
    for col in range(width):
        channel = "Untitled" if col == 0 else f"Untitled {col}"
        metadata += _tdms_string(f"/'Untitled'/'{channel}'")
        metadata += struct.pack("<I", 20)
        metadata += struct.pack("<IIQ", 2, 1, height)
        metadata += struct.pack("<I", 1)
        metadata += _tdms_property("NI_ArrayColumn", 3, col)
    raw = b"".join(np.asarray(frame, dtype="<i2").tobytes(order="C") for frame in frames)
    leadin = b"TDSm" + struct.pack("<IIQQ", 0x0E, 4713, len(metadata) + len(raw), len(metadata))
    path.write_bytes(leadin + metadata + raw)


class InterlacingShiftTests(unittest.TestCase):
    def test_estimates_correction_shift_for_odd_line_offset(self):
        base = _smooth_test_image()
        artifact = core.apply_interlacing_shift_image(base, 3, row_parity="odd")

        estimated = core.estimate_interlacing_shift(artifact, search_range=6, row_parity="odd")
        corrected = core.apply_interlacing_shift_image(artifact, estimated, row_parity="odd")

        self.assertEqual(estimated, -3)
        np.testing.assert_allclose(corrected[:, 8:-8], base[:, 8:-8], atol=1e-4)

    def test_applies_interlacing_shift_to_movie_without_changing_shape(self):
        base = _smooth_test_image()
        artifact = core.apply_interlacing_shift_image(base, 4, row_parity="odd")
        movie = np.stack([artifact, artifact + 5.0], axis=0)

        corrected = core.apply_interlacing_shift_movie(movie, -4, row_parity="odd")

        self.assertEqual(corrected.shape, movie.shape)
        np.testing.assert_allclose(corrected[0, :, 8:-8], base[:, 8:-8], atol=1e-4)
        np.testing.assert_allclose(corrected[1, :, 8:-8], base[:, 8:-8] + 5.0, atol=1e-4)

    def test_two_photon_conversion_auto_corrects_interlacing_shift_from_ch1(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "two_photon"
            folder.mkdir()
            (folder / "protocol_real-time imaging.txt").write_text(
                "\n".join(
                    [
                        "Recording time:        \t1.00",
                        "Recorded channels:   \tCh1, Ch2",
                        "Image frame rate:    \t2",
                        "Image frame size (x):\t48",
                        "Image frame size (y):\t32",
                    ]
                ),
                encoding="gbk",
            )
            ch1_base = _smooth_test_image(seed=10)
            ch2_base = _smooth_test_image(seed=11) * 0.6 + 100.0
            ch1_artifact = core.apply_interlacing_shift_image(ch1_base, 2, row_parity="odd")
            ch2_artifact = core.apply_interlacing_shift_image(ch2_base, 2, row_parity="odd")
            _write_test_tdms(
                folder / "data_real-time imaging.tdms",
                [
                    ch1_artifact.astype(np.int16),
                    ch2_artifact.astype(np.int16),
                    (ch1_artifact + 3).astype(np.int16),
                    (ch2_artifact + 3).astype(np.int16),
                ],
            )

            out_dir = Path(tmp) / "converted"
            result = core.convert_two_photon_folder_to_movie(folder, out_dir, interlacing_search_range=5)

            self.assertEqual(result.interlacing_shift_px, -2)
            np.testing.assert_allclose(result.channel_movies[0][0, :, 8:-8], ch1_base[:, 8:-8] + 32768.0, atol=1.0)
            np.testing.assert_allclose(result.channel_movies[1][0, :, 8:-8], ch2_base[:, 8:-8] + 32768.0, atol=1.0)
            result.movie._mmap.close()
            for channel_movie in result.channel_movies:
                channel_movie._mmap.close()


if __name__ == "__main__":
    unittest.main()
