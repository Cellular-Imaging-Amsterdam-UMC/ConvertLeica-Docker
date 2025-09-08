# ConvertLeica-Docker

ConvertLeica-Docker is a toolset and web interface for converting Leica LIF, LOF, and XLEF microscopy image files to the OME-TIFF format, with special handling for certain file types and image configurations. It is designed for both command-line and web-based workflows, supporting batch conversion and interactive browsing/conversion of large microscopy datasets.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage (Command Line)](#usage-command-line)
  - [Inputs](#inputs)
  - [Outputs](#outputs)
  - [Function Output](#function-output-format)
  - [Conversion Scenarios](#conversion-scenarios)
  - [WSL/Windows Example Usage](#wslwindows-example-usage)
- [Special Cases](#special-cases)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [References](#references)
- [More documentation](#more-documentation)
- [LeicaViewerQT (basic)](#leicaviewerqt-basic)

---

## Features

- **Convert Leica LIF, LOF, and XLEF files to OME-TIFF** (multi-channel, multi-Z, RGB, tilescans, etc.)
- **Automatic handling of special cases**: returns .LOF or single-image .LIF files when OME-TIFF is not appropriate
- **Batch and single-image conversion**
- **Web interface for browsing, previewing, and converting files**
- **Progress reporting and metadata inspection**

---

## Installation

### Requirements

- Python 3.12
- [pip](https://pip.pypa.io/en/stable/)
- (Optional) Docker for containerized usage

#### Python packages (see `requirements.txt`)

- numpy==1.26.4
- pyvips[binary]==2.2.2
- opencv-python==4.9.0.80

Install with:

```sh
pip install -r requirements.txt
```

#### libvips binaries (required for all platforms)

- **libvips** is required for pyvips to work. You must install the native libvips binaries on your system.

##### Linux

- Install libvips using your package manager. For example, on Ubuntu/Debian:

  ```sh
  sudo apt-get update && sudo apt-get install -y libvips-dev && sudo rm -rf /var/lib/apt/lists/*
  ```

##### macOS (not tested)

- Install libvips using [Homebrew](https://brew.sh/):

  ```sh
  brew install vips
  ```

##### Windows

- Download the latest Windows libvips binary from [libvips releases](https://github.com/libvips/libvips/releases) (choose the latest `vips-dev-w64-all` zip file).
- Extract to a folder, e.g., `C:\bin\vips`.
- Add the `bin` subfolder (e.g., `C:\bin\vips\bin`) to your Windows PATH environment variable.
- This project attempts to set the PATH for libvips automatically in `ci_leica_converters_ometiff.py` and `ci_leica_converters_ometiff_rgb.py`, defaulting to `C:\bin\vips\bin`. If you extract libvips elsewhere, update the PATH in those files or your system PATH accordingly.

### (Optional) Build and run with Docker

```sh
# Build the Docker image
# (from the root of this repository)
docker build -t convertleica-docker .

# Run the container, mounting your data directory
# (replace L:/data with your data path)
docker run --rm -v "L:/data:/data" convertleica-docker --inputfile /data/myfile.lif --outputfolder /data/.processed
```

---

## Usage (Command Line)

### Basic Command

```sh
python main.py --inputfile <path-to-LIF/LOF/XLEF> --outputfolder <output-folder> [--image_uuid <uuid>] [--show_progress] [--altoutputfolder <alt-folder>] [--xy_check_value <int>]
```

#### Arguments

- `--inputfile` (required): Path to the input Leica file (.lif, .lof, .xlef)
- `--outputfolder` (required): Output directory for converted files
- `--image_uuid`: UUID of the image to extract (for multi-image files)
- `--show_progress`: Show progress bar during conversion
- `--altoutputfolder`: Optional second output directory
- `--xy_check_value`: XY size threshold for special handling (default: 3192)
- `--get_image_metadata`: Also include full image metadata JSON in the result under `keyvalues.image_metadata_json`
- `--get_image_xml`: Also include the raw image XML (when available) under `keyvalues.image_xml`

### Inputs

- **LIF**: Leica Image File (may contain multiple images, folders, tilescans, etc.)
- **LOF**: Leica Object File (single image, often exported from LIF)
- **XLEF**: Leica Experiment File (may reference multiple images, often RGB)

### Outputs

- **OME-TIFF**: Standard output for most images (multi-channel, multi-Z, tiled, etc.)
- **.LOF**: Returned for certain LOF files or when conversion to OME-TIFF is not needed
- **Single-image .LIF**: Returned for special cases (e.g., negative overlap tilescans)

### Function Output Format

The function returns a JSON array string describing the conversion result(s). Each element has:

- `name`: base name of the created or relevant file (without extension)
- `full_path`: absolute path to the output file (OME-TIFF, .LOF, or .LIF)
- `alt_path`: absolute path to the file in `altoutputfolder` (if used and file exists), else `null`
- `keyvalues`: a single-item list with a dictionary containing per-channel intensity stats and optional metadata

Per-channel intensity stats (always present when readable):

- `channel_mins`: list[int] per channel, minimum pixel value observed (container units)
- `channel_maxs`: list[int] per channel, maximum pixel value observed (container units)
- `channel_display_black_values`: list[int] per channel, display black levels scaled to the container range
- `channel_display_white_values`: list[int] per channel, display white levels scaled to the container range

Optional metadata fields (included only when flags are used):

- `image_metadata_json`: full parsed image metadata JSON (when `--get_image_metadata`)
- `image_xml`: raw image XML string if available, else empty string (when `--get_image_xml`)

If no conversion is applicable or an error occurs, an empty JSON array string (`[]`) is returned.

Example result:

```json
[
  {
    "name": "Swiss Rolls GM1748 LEX277AD",
    "full_path": "L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/.processed/Swiss Rolls GM1748 LEX277AD.ome.tiff",
    "alt_path": "U:/cc/Swiss Rolls GM1748 LEX277AD.ome.tiff",
    "keyvalues": [
      {
        "channel_mins": [1097, 2257, 335, 175],
        "channel_maxs": [7423, 5907, 10261, 3716],
        "channel_display_black_values": [1179, 2357, 372, 202],
        "channel_display_white_values": [6798, 5641, 7002, 2969]
      },
      "experiment_name": "Cells in mouse brain",
      "experiment_date": "2025-05-01"
    ]
  }
]
```

You can parse this output in Python using `json.loads()` to access the result programmatically.

---

### Conversion Scenarios

- **LIF file**: RGB and multi-channel images are converted to OME-TIFF. If the image is a tilescan with negative overlap, a single-image .LIF is returned instead.
- **LOF file**: RGB and multi-channel images are converted to OME-TIFF. If not needed, the original .LOF is returned.
- **XLEF file**: RGB and multi-channel images are converted to OME-TIFF. Special cases (e.g., negative overlap or unsupported structure) may return the original LOF file.

### WSL/Windows Example Usage

See `Tests/test_convertleica.py` and `Tests/test_ometiff_RGB.py` for real-world examples:

```python
lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/Swiss Rolls GM1748 LEX277AD.lif'
image_uuid = "ad7b9384-0466-11e9-8a36-8cec4b8a9866"
outputfolder = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/.processed'
altoutputfolder = 'U:/cc'

status = convert_leica(
    inputfile=lif_file_path,
    image_uuid=image_uuid,
    show_progress=True,
    outputfolder=outputfolder,
    altoutputfolder=altoutputfolder
)
print(status)
```

---

## Special Cases

- **Tilescan with Negative Overlap (LIF)**: Instead of OME-TIFF, a single-image .LIF is returned
- **LOF/XLEF**: If conversion is not needed, the original LOF file is returned

---

## Troubleshooting

- Ensure all dependencies are installed (`pip install -r requirements.txt`)
- For Docker, ensure your data directory is mounted correctly
- For large files, ensure sufficient disk space and memory
- If you encounter errors, check the console output for details

## License

MIT License

---

### References

- [NumPy](https://numpy.org/)
- [pyvips](https://libvips.github.io/pyvips/)
- [OpenCV (opencv-python)](https://pypi.org/project/opencv-python/)

---

## More documentation

- [Server.md](Server.md) — Web server and website documentation, including progressive preview and disk cache behavior, endpoints, and client flow.
- [ConvertLeicaQT.md](ConvertLeicaQT.md) — Desktop Qt GUI documentation with browsing, progressive previews (cache parity with server), and conversion workflow.
- [LeicaViewerQT.md](LeicaViewerQT.md) — A lightweight Qt desktop image viewer focused on Leica LIF/LOF/XLEF browsing and quick previewing.

Note: Requires the same Python dependencies as the converter (see requirements) and a working libvips installation.
