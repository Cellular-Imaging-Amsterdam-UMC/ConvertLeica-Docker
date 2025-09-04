import os
import math
import numpy as np
from typing import Dict, List, Tuple


def _as_int_list(value, length: int, default: int) -> List[int]:
    """Normalize metadata values to a per-channel integer list of a given length."""
    if isinstance(value, list):
        arr = []
        for i in range(length):
            v = value[i] if i < len(value) else None
            if v is None:
                arr.append(int(default))
            else:
                try:
                    arr.append(int(round(float(v))))
                except Exception:
                    arr.append(int(default))
        return arr
    try:
        v = int(round(float(value)))
    except Exception:
        v = int(default)
    return [v for _ in range(length)]


def _resolve_bits_per_channel(meta: dict, channels: int, isrgb: bool) -> List[int]:
    """Return bits per channel list, using channelResolution when available, else default heuristics."""
    res = meta.get("channelResolution")
    if isinstance(res, list) and res:
        bits_list = []
        fallback = 16
        for i in range(channels):
            b = res[i] if i < len(res) else None
            try:
                b = int(b) if b is not None else fallback
            except Exception:
                b = fallback
            if b not in (8, 12, 14, 15, 16, 32):
                # Container will be 8 or 16 for our raw stream; clamp to typical values
                b = 8 if b and b <= 8 else 16
            bits_list.append(b)
        return bits_list
    if isinstance(res, (int, float)):
        b = int(res)
        b = 8 if b and b <= 8 else 16
        return [b] * channels
    # Heuristic when missing
    if isrgb:
        # Most Leica RGB exports are 8-bit; fall back to 16 if metadata indicates higher container
        return [8, 8, 8]
    return [16] * channels


def _dtype_from_bits(bits: int):
    return (np.uint8, 1, 255) if bits <= 8 else (np.uint16, 2, 65535)


def compute_channel_intensity_stats(metadata: dict, sample_fraction: float = 0.1, use_memmap: bool = True) -> Dict[str, List[int]]:
    """
    Fast approximate per-channel intensity stats using subsampling and memmap.

    Strategy:
    - Choose center Z, center T, center tile (if present) to avoid reading full volumes/mosaics.
    - Subsample rows with a stride computed from sample_fraction (e.g., 0.1 -> every 10th row).
    - For RGB: read a single interleaved slice (ys, xs, 3) and compute per-channel min/max.
    - For multi-channel: read per-channel planar slices using channelbytesinc offsets.

    Returns dict with keys:
      - channel_mins: int list per channel (length 3 for RGB)
      - channel_maxs: int list per channel
      - display_black_values: scaled to container (int) per channel
      - display_white_values: scaled to container (int) per channel
    """
    # Ensure dict input
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dict (use read_image_metadata first)")

    filetype = metadata.get("filetype")
    if filetype not in (".lif", ".xlef", ".lof"):
        return {
            "channel_mins": [],
            "channel_maxs": [],
            "display_black_values": [],
            "display_white_values": [],
        }

    # Determine file name and base offset similar to CreatePreview
    if filetype == ".lif":
        file_name = metadata.get("LIFFile") or metadata.get("LOFFilePath")
        base_pos = int(metadata.get("Position", 0) or 0)
    else:  # .xlef / .lof images read from LOF
        file_name = metadata.get("LOFFilePath")
        base_pos = 62  # LOF header size used in codebase

    if not file_name or not os.path.exists(file_name):
        # Can't read pixels; just scale display min/max if available
        return _fallback_only_display(metadata)

    xs = int(metadata.get("xs", 1) or 1)
    ys = int(metadata.get("ys", 1) or 1)
    zs = int(metadata.get("zs", 1) or 1)
    ts = int(metadata.get("ts", 1) or 1)
    tiles = int(metadata.get("tiles", 1) or 1)
    isrgb = bool(metadata.get("isrgb", False))

    channels = 3 if isrgb else int(metadata.get("channels", 1) or 1)
    channelbytesinc = metadata.get("channelbytesinc") or [0] * channels
    zbytesinc = int(metadata.get("zbytesinc", 0) or 0)
    tbytesinc = int(metadata.get("tbytesinc", 0) or 0)
    tilesbytesinc = int(metadata.get("tilesbytesinc", 0) or 0)

    # Select center t, tile, and z
    t_sel = ts // 2 if ts and ts > 1 else 0
    s_sel = tiles // 2 if tiles and tiles > 1 else 0
    z_sel = zs // 2 if zs and zs > 1 else 0

    # Adjust base position
    base = base_pos + (t_sel * tbytesinc) + (s_sel * tilesbytesinc) + (z_sel * zbytesinc)

    # Resolve bits per channel and container dtype
    bits_per_ch = _resolve_bits_per_channel(metadata, channels, isrgb)
    # Use first channel bit depth to decide container dtype for reading (stream container)
    dtype, bpp, container_max_val = _dtype_from_bits(bits_per_ch[0])

    # Determine sampling stride
    if sample_fraction <= 0 or sample_fraction > 1:
        sample_fraction = 0.1
    step = max(1, int(round(1.0 / sample_fraction)))

    ch_mins: List[int] = []
    ch_maxs: List[int] = []

    try:
        if isrgb:
            # Interleaved RGB slice (ys, xs, 3)
            shape = (ys, xs, 3)
            if use_memmap:
                arr = np.memmap(file_name, dtype=dtype, mode="r", offset=base, shape=shape, order="C")
                sample = arr[::step, :, :]
            else:
                # Fallback: read in row strides
                sample = _read_rows_strided(file_name, base, ys, xs, 3, bpp, step, dtype)
            # Compute per-channel min/max
            ch_mins = sample.reshape(-1, 3).min(axis=0).astype(int).tolist()
            ch_maxs = sample.reshape(-1, 3).max(axis=0).astype(int).tolist()
        else:
            # Planar per-channel slices
            for c in range(channels):
                c_off = base + int(channelbytesinc[c] if c < len(channelbytesinc) and channelbytesinc[c] is not None else 0)
                shape = (ys, xs)
                if use_memmap:
                    arr = np.memmap(file_name, dtype=dtype, mode="r", offset=c_off, shape=shape, order="C")
                    sample = arr[::step, :]
                else:
                    sample = _read_rows_strided(file_name, c_off, ys, xs, 1, bpp, step, dtype)
                ch_mins.append(int(sample.min()))
                ch_maxs.append(int(sample.max()))
    except Exception:
        # If anything fails, fall back to display-only values
        return _fallback_only_display(metadata)

    # Display black/white values scaled to container per channel
    black_vals = _scale_display_values(metadata.get("blackvalue"), bits_per_ch, container_max_val, channels)
    white_vals = _scale_display_values(metadata.get("whitevalue"), bits_per_ch, container_max_val, channels)

    return {
        "channel_mins": ch_mins,
        "channel_maxs": ch_maxs,
        "display_black_values": black_vals,
        "display_white_values": white_vals,
    }


def _read_rows_strided(file_name: str, offset: int, ys: int, xs: int, chans: int, bpp: int, step: int, dtype) -> np.ndarray:
    """Slow-path reader: read every `step`th row into an ndarray of shape (ceil(ys/step), xs[, chans])."""
    import io
    rows = int(math.ceil(ys / step))
    if chans == 3:
        out = np.empty((rows, xs, 3), dtype=dtype)
        stride_bytes = xs * bpp * 3
    else:
        out = np.empty((rows, xs), dtype=dtype)
        stride_bytes = xs * bpp
    with open(file_name, "rb", buffering=io.DEFAULT_BUFFER_SIZE) as f:
        for i in range(rows):
            r_start = i * step
            if r_start >= ys:
                out = out[:i]
                break
            f.seek(offset + r_start * stride_bytes, os.SEEK_SET)
            buf = f.read(stride_bytes)
            if len(buf) < stride_bytes:
                out = out[:i]
                break
            arr = np.frombuffer(buf, dtype=dtype)
            if chans == 3:
                out[i, :, :] = arr.reshape((xs, 3))
            else:
                out[i, :] = arr.reshape((xs,))
    return out


def _fallback_only_display(meta: dict) -> Dict[str, List[int]]:
    channels = 3 if meta.get("isrgb") else int(meta.get("channels", 1) or 1)
    bits_per_ch = _resolve_bits_per_channel(meta, channels, bool(meta.get("isrgb", False)))
    # Use container from first channel
    _, _, container_max_val = _dtype_from_bits(bits_per_ch[0])
    black_vals = _scale_display_values(meta.get("blackvalue"), bits_per_ch, container_max_val, channels)
    white_vals = _scale_display_values(meta.get("whitevalue"), bits_per_ch, container_max_val, channels)
    return {
        "channel_mins": [0] * channels,
        "channel_maxs": [container_max_val] * channels,
        "display_black_values": black_vals,
        "display_white_values": white_vals,
    }


def _scale_display_values(values, bits_per_ch: List[int], container_max_val: int, channels: int) -> List[int]:
    """Scale viewer black/white values (often 0..1 floats) to container integer range per channel.

    If `values` length mismatches `channels`, pad/repeat as needed.
    If values seem already in container range (>1), clamp and cast.
    """
    # Normalize input list length
    if isinstance(values, list) and values:
        vals = values[:]
    elif values is None:
        vals = [0.0] * channels
    else:
        # Scalar
        try:
            vals = [float(values)] * channels
        except Exception:
            vals = [0.0] * channels

    # Pad or trim
    if len(vals) < channels:
        vals = vals + [vals[-1] if vals else 0.0] * (channels - len(vals))
    else:
        vals = vals[:channels]

    out: List[int] = []
    for i in range(channels):
        v = vals[i]
        try:
            v = float(v)
        except Exception:
            v = 0.0
        # If already in integer range, clamp to container
        if v > 1.0:
            out.append(int(max(0, min(container_max_val, round(v)))))
        else:
            # Assume normalized [0,1] -> scale to container of that channel
            # Some channels might have different significant bits, but container is uniform
            out.append(int(max(0, min(container_max_val, round(v * container_max_val)))))
    return out
