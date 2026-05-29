import struct
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

import analysis_core as core


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


class TwoPhotonConverterTests(unittest.TestCase):
    def test_protocol_parser_reads_frame_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "protocol_real-time imaging.txt").write_text(
                "\n".join(
                    [
                        "Recording time:        \t1.00",
                        "Recorded channels:   \tCh1, Ch2",
                        "Image frame rate:    \t2",
                        "Image frame size (x):\t3",
                        "Image frame size (y):\t2",
                    ]
                ),
                encoding="gbk",
            )

            protocol = core.read_two_photon_protocol(folder)

            self.assertEqual(protocol.width, 3)
            self.assertEqual(protocol.height, 2)
            self.assertEqual(protocol.frame_rate, 2)
            self.assertEqual(protocol.expected_frames, 2)
            self.assertEqual(protocol.channels, ("Ch1", "Ch2"))

    def test_pseudocolor_maps_ch1_green_and_ch2_red(self):
        ch1 = np.array([[0, 10], [20, 30]], dtype=np.float32)
        ch2 = np.array([[30, 20], [10, 0]], dtype=np.float32)

        rgb = core.pseudocolor_rgb(ch1, ch2, (0, 30), (0, 30))
        bgr = core.pseudocolor_bgr(ch1, ch2, (0, 30), (0, 30))

        self.assertEqual(rgb.shape, (2, 2, 3))
        self.assertEqual(int(rgb[0, 1, 0]), 170)
        self.assertEqual(int(rgb[0, 1, 1]), 85)
        self.assertTrue(np.all(rgb[:, :, 2] == 0))
        self.assertEqual(bgr.shape, (2, 2, 3))
        self.assertEqual(int(bgr[0, 1, 1]), 85)
        self.assertEqual(int(bgr[0, 1, 2]), 170)
        self.assertTrue(np.all(bgr[:, :, 0] == 0))

    def test_convert_folder_restores_tdms_frames_and_writes_avi(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "20260424_A04"
            folder.mkdir()
            (folder / "protocol_real-time imaging.txt").write_text(
                "\n".join(
                    [
                        "Recording time:        \t1.00",
                        "Recorded channels:   \tCh1, Ch2",
                        "Image frame rate:    \t2",
                        "Image frame size (x):\t3",
                        "Image frame size (y):\t2",
                    ]
                ),
                encoding="gbk",
            )
            ch1_0 = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int16)
            ch2_0 = np.array([[10, 20, 30], [40, 50, 60]], dtype=np.int16)
            ch1_1 = ch1_0 + 10
            ch2_1 = ch2_0 + 10
            _write_test_tdms(folder / "data_real-time imaging.tdms", [ch1_0, ch2_0, ch1_1, ch2_1])

            out_dir = Path(tmp) / "converted"
            result = core.convert_two_photon_folder_to_movie(folder, out_dir)

            self.assertEqual(result.movie.shape, (2, 2, 3))
            self.assertEqual(len(result.channel_movies), 2)
            self.assertEqual(len(result.channel_avi_paths), 2)
            np.testing.assert_allclose(result.movie[0], ch2_0.astype(np.float32) + 32768.0)
            np.testing.assert_allclose(result.channel_movies[0][0], ch1_0.astype(np.float32) + 32768.0)
            np.testing.assert_allclose(result.channel_movies[1][0], ch2_0.astype(np.float32) + 32768.0)
            self.assertTrue(result.color_avi_path.exists())
            for channel_path in result.channel_avi_paths:
                self.assertTrue(channel_path.exists())
            cap = cv2.VideoCapture(str(result.color_avi_path))
            ok, frame = cap.read()
            cap.release()
            self.assertTrue(ok)
            self.assertGreater(float(frame[:, :, 1].mean()), 0.0)
            self.assertGreater(float(frame[:, :, 2].mean()), 0.0)
            result.movie._mmap.close()
            for channel_movie in result.channel_movies:
                channel_movie._mmap.close()


if __name__ == "__main__":
    unittest.main()
