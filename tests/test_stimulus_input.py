import tempfile
import unittest
from pathlib import Path

import numpy as np

import analysis_core as core


class StimulusInputTests(unittest.TestCase):
    def test_multicolumn_user_input_selects_ttl_column_and_infers_fs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "protocol_real-time imaging.txt").write_text(
                "\n".join(
                    [
                        "Recording time:        \t2.00",
                        "Recorded channels:   \tCh1",
                        "Image frame rate:    \t40",
                        "Image frame size (x):\t4",
                        "Image frame size (y):\t3",
                    ]
                ),
                encoding="gbk",
            )
            samples = 200
            ephys = np.zeros(samples, dtype=np.float32)
            ephys[[20, 90, 160]] = 5.0
            stim_marker = np.full(samples, 0.002, dtype=np.float32)
            empty = np.random.default_rng(2).normal(0, 0.001, size=samples).astype(np.float32)
            path = folder / "data_user input.txt"
            with path.open("w", encoding="utf-8") as f:
                f.write("E-phys\tStim. Marker\t(empty)\n")
                for row in zip(ephys, stim_marker, empty):
                    f.write("\t".join(f"{value:.6f}" for value in row) + "\n")

            info = core.read_stimulus_file_info(path)

            self.assertEqual(info.column_name, "E-phys")
            self.assertAlmostEqual(info.fs, 100.0)
            triggers = core.detect_stimulus_triggers(info.signal, info.fs, threshold=0)
            np.testing.assert_array_equal(triggers, np.array([20, 90, 160]))


if __name__ == "__main__":
    unittest.main()
