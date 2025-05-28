# ConvertLeica-Docker

ConvertLeica-Docker is a toolset and web interface for converting Leica LIF, LOF, and XLEF microscopy image files to the OME-TIFF format, with special handling for certain file types and image configurations. It is designed for both command-line and web-based workflows, supporting batch conversion and interactive browsing/conversion of large microscopy datasets.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage (Command Line)](#usage-command-line)
  - [Inputs](#inputs)
  - [Outputs](#outputs)
  - [Conversion Scenarios](#conversion-scenarios)
  - [WSL/Windows Example Usage](#wslwindows-example-usage)
- [Web Server & Local Website](#web-server--local-website)
  - [How it Works](#how-it-works)
  - [Browsing and Conversion](#browsing-and-conversion)
- [Special Cases](#special-cases)
- [Troubleshooting](#troubleshooting)
- [License](#license)

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

- Python 3.8+
- [pip](https://pip.pypa.io/en/stable/)
- (Optional) Docker for containerized usage

### Install Python dependencies

```sh
pip install -r requirements.txt
```

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

### Inputs

- **LIF**: Leica Image File (may contain multiple images, folders, tilescans, etc.)
- **LOF**: Leica Object File (single image, often exported from LIF)
- **XLEF**: Leica Experiment File (may reference multiple images, often RGB)

### Outputs

- **OME-TIFF**: Standard output for most images (multi-channel, multi-Z, tiled, etc.)
- **.LOF**: Returned for certain LOF files or when conversion to OME-TIFF is not needed
- **Single-image .LIF**: Returned for special cases (e.g., negative overlap tilescans)

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

## Web Server & Local Website

### How it Works

- `server.py` starts a local HTTP server and API for browsing and converting Leica files.
- `index.html` provides a modern web interface for:
  - Browsing the directory tree (set by `ROOT_DIR` in `server.py`)
  - Previewing images and metadata
  - Converting images to OME-TIFF (or returning .LOF/.LIF in special cases)

### Running the Server

```sh
python server.py
```

- The server will open a browser window to the local site (by default at http://localhost:8000/)
- You can browse, preview, and convert files interactively.

### Browsing and Conversion

- Navigate folders and select LIF, LOF, or XLEF files
- Preview images and inspect metadata
- Click "Convert Image" to trigger conversion
- The output will be OME-TIFF, .LOF, or single-image .LIF depending on the scenario (see below)

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

---

## License

MIT License
