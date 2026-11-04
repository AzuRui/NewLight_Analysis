r"""Guard the "导出 ROI 统计" feature end to end.

The release that shipped without `openpyxl` in its bundle failed here with
`No module named 'openpyxl'` only when a user chose `.xlsx`, so the round trip through
`pandas.ExcelWriter` is the thing that has to stay executable rather than merely importable.
"""

import numpy as np
import pandas as pd

import analysis_core as core


def _stats() -> tuple[pd.DataFrame, np.ndarray]:
    traces = np.zeros((12, 2), dtype=np.float32)
    traces[3, 0] = 1.0
    traces[8, 1] = 2.0
    stats = core.roi_statistics(traces, ["roi_a", "roi_b"], 10.0, [], min_peak_percentile=90.0)
    movie = np.zeros((12, 4, 4), dtype=np.uint16)
    return stats, movie


def test_roi_statistics_excel_export_round_trips(tmp_path):
    path = tmp_path / "ROI_statistics.xlsx"
    stats, movie = _stats()

    core.save_roi_statistics_table(
        str(path), stats, movie=movie, fs=10.0, roi_count=2, trigger_count=0,
    )

    sheets = pd.read_excel(path, sheet_name=None)
    assert sorted(sheets) == ["Experiment Info", "ROI Statistics"]
    assert list(sheets["ROI Statistics"]["ROI"]) == ["roi_a", "roi_b"]
    assert sheets["ROI Statistics"]["Peak_Count"].tolist() == [1, 1]
    assert sheets["Experiment Info"]["Value"].tolist()[0] == 12


def test_roi_statistics_csv_export_needs_no_excel_engine(tmp_path):
    path = tmp_path / "ROI_statistics.csv"
    stats, _movie = _stats()

    core.save_roi_statistics_table(str(path), stats)

    assert list(pd.read_csv(path)["ROI"]) == ["roi_a", "roi_b"]
