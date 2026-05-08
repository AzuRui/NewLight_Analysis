# NewLight_Analysis Packaging

Use `build_exe.bat` to create a portable Windows folder build.

## Build

```powershell
E:\WorkSpace\NewLight_Analysis\build_exe.bat
```

Output:

```text
E:\WorkSpace\NewLight_Analysis\build_release\NewLight_Analysis\NewLight_Analysis.exe
E:\WorkSpace\NewLight_Analysis\build_release\Run_NewLight_Analysis.bat
```

## Distribution

Distribute the whole `build_release` folder, or zip it.

The executable contains the main GUI and Python dependencies from the build environment. The optional algorithm backends remain external:

- `neuroseg3` conda environment for NeuroSeg3 ROI segmentation.
- `caiman_latest` conda environment for CaImAn motion correction.

On target machines, run:

```powershell
build_release\NewLight_Analysis\check_backends.bat
```

If CaImAn is missing, run:

```powershell
build_release\NewLight_Analysis\setup_caiman_latest.bat
```

## Notes

- The app icon is `xhr.ico`.
- The build mode is PyInstaller `onedir`, which creates a folder plus `NewLight_Analysis.exe`.
- This is preferred over single-file mode because scientific Python libraries start faster and are easier to debug in folder mode.

