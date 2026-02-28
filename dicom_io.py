"""
dicom_io.py — Pure DICOM logic, no tkinter dependency.

Handles: file discovery, pixel pipeline, tag tree building,
anonymisation, and saving.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pydicom
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Anonymisation types
# ---------------------------------------------------------------------------


class AnonAction(Enum):
    BLANK = "blank"
    PLACEHOLDER = "placeholder"
    DELETE = "delete"


@dataclass
class AnonRule:
    action: AnonAction
    placeholder: str = ""


# ---------------------------------------------------------------------------
# Tag node (for tree rendering)
# ---------------------------------------------------------------------------


@dataclass
class TagNode:
    tag: pydicom.tag.BaseTag
    keyword: str
    vr: str
    value_repr: str
    is_sequence: bool
    children: list["TagNode"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

_NON_DICOM_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".json",
    ".xml",
    ".csv",
    ".txt",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
}


def discover_dicom_files(folder: str) -> list[Path]:
    """
    Recursively find DICOM files under *folder*.

    Strategy:
    1. Collect *.dcm / *.DCM files.
    2. Collect files with no recognised suffix (or no suffix at all).
    3. Validate each candidate with a cheap header-only dcmread.
    4. Return sorted list of confirmed paths.
    """
    root = Path(folder)
    candidates: set[Path] = set()

    # Fast path: explicit .dcm extension
    _IGNORED_NAMES = {".DS_Store"}

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name in _IGNORED_NAMES:
            continue
        suffix = p.suffix.lower()
        if suffix == ".dcm":
            candidates.add(p)
        elif suffix not in _NON_DICOM_SUFFIXES:
            # Could be a DICOM file without extension
            candidates.add(p)

    confirmed: list[Path] = []
    for path in sorted(candidates):
        if _is_dicom(path):
            confirmed.append(path)

    return confirmed


def _is_dicom(path: Path) -> bool:
    """Confirm the file is a valid DICOM by checking the magic bytes and header.

    Requires the standard Part-10 preamble (b'DICM' at offset 128) so that
    arbitrary non-DICOM files are not mistaken for DICOM.
    """
    try:
        with open(path, "rb") as fh:
            fh.seek(128)
            if fh.read(4) != b"DICM":
                return False
        pydicom.dcmread(str(path), stop_before_pixels=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# DICOM loading
# ---------------------------------------------------------------------------


def load_dicom(path: Path) -> pydicom.dataset.FileDataset:
    """Full load (with pixels). Raises on failure — callers must handle."""
    return pydicom.dcmread(str(path), force=True)


# ---------------------------------------------------------------------------
# Pixel pipeline
# ---------------------------------------------------------------------------


def get_pil_image(
    ds: pydicom.dataset.FileDataset,
) -> Optional[Image.Image]:
    """
    Convert DICOM pixel data to an unscaled PIL RGB Image.

    Pipeline:
      pixel_array → multi-frame → modality LUT → windowing → uint8 → PIL RGB

    Returns None if the file has no pixel data (SR, KO, PR, etc.).
    """
    try:
        arr = ds.pixel_array
    except AttributeError:
        return None  # No PixelData element
    except Exception:
        return None  # Compressed / unsupported transfer syntax

    # Handle multi-frame: take first frame only
    if arr.ndim == 4:
        arr = arr[0]  # (frames, rows, cols, channels)
    elif (
        arr.ndim == 3
        and hasattr(ds, "NumberOfFrames")
        and int(getattr(ds, "NumberOfFrames", 1)) > 1
    ):
        arr = arr[0]  # (frames, rows, cols)

    # Convert to float for LUT operations
    arr = arr.astype(np.float64)

    # Apply modality LUT (rescale slope/intercept)
    try:
        from pydicom.pixels import apply_modality_lut

        arr = apply_modality_lut(arr, ds)
    except Exception:
        pass

    # Apply windowing
    try:
        from pydicom.pixels import apply_windowing

        arr = apply_windowing(arr, ds)
    except Exception:
        pass

    arr = _normalise_to_uint8(arr)

    # Build PIL Image
    photometric = getattr(ds, "PhotometricInterpretation", "MONOCHROME2")
    if arr.ndim == 3 and arr.shape[2] == 3:
        # RGB / YBR data
        return Image.fromarray(arr, mode="RGB")
    elif arr.ndim == 3 and arr.shape[2] == 4:
        return Image.fromarray(arr, mode="RGBA").convert("RGB")
    else:
        # Grayscale
        if photometric == "MONOCHROME1":
            arr = 255 - arr  # invert
        return Image.fromarray(arr, mode="L").convert("RGB")


def get_display_image(
    ds: pydicom.dataset.FileDataset,
    max_size: tuple[int, int] = (512, 512),
) -> Optional[ImageTk.PhotoImage]:
    """
    Convert DICOM pixel data to a tkinter-compatible PhotoImage (resized to max_size).

    Returns None if the file has no pixel data (SR, KO, PR, etc.).
    """
    img = get_pil_image(ds)
    if img is None:
        return None
    img = _resize_to_fit(img, max_size)
    return ImageTk.PhotoImage(img)


def _normalise_to_uint8(arr: np.ndarray) -> np.ndarray:
    """Scale any dtype to uint8 [0, 255]."""
    if arr.dtype == np.uint8:
        return arr
    mn, mx = arr.min(), arr.max()
    if mx == mn:
        return np.zeros_like(arr, dtype=np.uint8)
    return ((arr - mn) / (mx - mn) * 255).astype(np.uint8)


def _resize_to_fit(img: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    """Resize PIL image to fit within max_size, preserving aspect ratio."""
    img.thumbnail(max_size, Image.LANCZOS)
    return img


# ---------------------------------------------------------------------------
# Tag tree building
# ---------------------------------------------------------------------------


def build_tag_nodes(ds: pydicom.Dataset) -> list[TagNode]:
    """
    Recursively convert a pydicom Dataset into TagNode objects.

    SQ elements produce a TagNode with .children = list of "Item N" TagNodes,
    each of which has .children = build_tag_nodes(item_dataset).
    """
    nodes: list[TagNode] = []
    for elem in ds:
        keyword = elem.keyword if elem.keyword else "(Private)"
        repr_val = _elem_value_repr(elem)

        if elem.VR == "SQ":
            item_nodes: list[TagNode] = []
            for i, item_ds in enumerate(elem.value):
                sub_nodes = build_tag_nodes(item_ds)
                item_node = TagNode(
                    tag=elem.tag,
                    keyword=f"Item {i + 1}",
                    vr="",
                    value_repr="",
                    is_sequence=True,
                    children=sub_nodes,
                )
                item_nodes.append(item_node)

            nodes.append(
                TagNode(
                    tag=elem.tag,
                    keyword=keyword,
                    vr="SQ",
                    value_repr=f"{len(elem.value)} item(s)",
                    is_sequence=True,
                    children=item_nodes,
                )
            )
        else:
            nodes.append(
                TagNode(
                    tag=elem.tag,
                    keyword=keyword,
                    vr=elem.VR,
                    value_repr=repr_val,
                    is_sequence=False,
                )
            )
    return nodes


def _elem_value_repr(elem: pydicom.DataElement) -> str:
    """Truncated, safe string representation of a DataElement value."""
    try:
        val = elem.value
        if isinstance(val, bytes):
            return f"<binary {len(val)} bytes>"
        if isinstance(val, pydicom.sequence.Sequence):
            return f"{len(val)} item(s)"
        s = str(val)
        if len(s) > 80:
            s = s[:77] + "..."
        return s
    except Exception:
        return "<error>"


# ---------------------------------------------------------------------------
# Anonymisation
# ---------------------------------------------------------------------------


def anonymise_dataset(
    ds: pydicom.dataset.FileDataset,
    rules: dict[int, AnonRule],
) -> pydicom.dataset.FileDataset:
    """
    Return a deep copy of *ds* with anonymisation rules applied.

    Keys in *rules* are int(tag).  Tags not present in the dataset are silently skipped.
    """
    anon_ds = copy.deepcopy(ds)

    for tag_int, rule in rules.items():
        tag = pydicom.tag.Tag(tag_int)
        if tag not in anon_ds:
            continue

        if rule.action == AnonAction.DELETE:
            del anon_ds[tag]

        elif rule.action == AnonAction.BLANK:
            vr = anon_ds[tag].VR
            anon_ds[tag].value = _blank_value(vr)

        elif rule.action == AnonAction.PLACEHOLDER:
            vr = anon_ds[tag].VR
            if vr in _STRING_VRS:
                anon_ds[tag].value = rule.placeholder
            else:
                # Numeric / binary VRs can't hold a string — blank instead
                anon_ds[tag].value = _blank_value(vr)

    return anon_ds


_STRING_VRS = {
    "AE",
    "AS",
    "CS",
    "DA",
    "DS",
    "DT",
    "IS",
    "LO",
    "LT",
    "PN",
    "SH",
    "ST",
    "TM",
    "UC",
    "UI",
    "UR",
    "UT",
}

_NUMERIC_VRS = {"SS", "US", "SL", "UL", "FL", "FD", "SV", "UV", "OL", "OV"}
_BINARY_VRS = {"OB", "OW", "OD", "OF", "UN"}


def _blank_value(vr: str) -> object:
    """Return a type-appropriate blank value for *vr*."""
    if vr in _STRING_VRS:
        return ""
    if vr in _BINARY_VRS:
        return b""
    if vr in _NUMERIC_VRS:
        return 0
    if vr == "AT":
        return pydicom.tag.Tag(0, 0)
    if vr == "SQ":
        return pydicom.Sequence([])
    return ""


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def save_dicom(ds: pydicom.dataset.FileDataset, output_path: Path) -> None:
    """Save *ds* to *output_path*, creating parent directories as needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(str(output_path), enforce_file_format=True)


# ---------------------------------------------------------------------------
# Anonymisation profile (YAML)
# ---------------------------------------------------------------------------


def save_profile(rules: dict[int, AnonRule], path: Path) -> None:
    """
    Serialise *rules* to a human-readable YAML file at *path*.

    Format:
      rules:
        - tag: "0010,0010"
          keyword: PatientName
          action: blank
        - tag: "0010,0020"
          keyword: PatientID
          action: placeholder
          placeholder: "ANON_001"
    """
    import yaml  # deferred so the rest of the module works without PyYAML

    entries = []
    for tag_int, rule in sorted(rules.items()):
        tag = pydicom.tag.Tag(tag_int)
        tag_str = f"{tag.group:04X},{tag.element:04X}"
        keyword = pydicom.datadict.keyword_for_tag(tag) or "(Private)"
        entry: dict = {
            "tag": tag_str,
            "keyword": keyword,
            "action": rule.action.value,
        }
        if rule.action == AnonAction.PLACEHOLDER:
            entry["placeholder"] = rule.placeholder
        entries.append(entry)

    doc = {"rules": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(
            doc, fh, default_flow_style=False, allow_unicode=True, sort_keys=False
        )


def load_profile(path: Path) -> dict[int, AnonRule]:
    """
    Load an anonymisation profile from a YAML file produced by *save_profile*.

    Each entry must have at minimum: ``tag`` (e.g. ``"0010,0010"``) and ``action``
    (``blank`` | ``placeholder`` | ``delete``).  ``keyword`` is informational only
    and is ignored during loading.

    Returns {int(tag): AnonRule}.
    Raises ValueError with a descriptive message on malformed input.
    """
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    if not isinstance(doc, dict) or "rules" not in doc:
        raise ValueError("YAML file must contain a top-level 'rules' key.")

    rules: dict[int, AnonRule] = {}
    for i, entry in enumerate(doc["rules"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Rule #{i + 1} is not a mapping.")
        if "tag" not in entry:
            raise ValueError(f"Rule #{i + 1} is missing the 'tag' field.")
        if "action" not in entry:
            raise ValueError(f"Rule #{i + 1} is missing the 'action' field.")

        # Parse "GGGG,EEEE" tag string
        raw_tag = str(entry["tag"]).replace(" ", "")
        if "," not in raw_tag or len(raw_tag) != 9:
            raise ValueError(
                f"Rule #{i + 1}: invalid tag format '{entry['tag']}'. Expected 'GGGG,EEEE'."
            )
        try:
            group = int(raw_tag[:4], 16)
            elem = int(raw_tag[5:], 16)
        except ValueError:
            raise ValueError(
                f"Rule #{i + 1}: tag '{entry['tag']}' contains non-hex characters."
            )

        tag_int = int(pydicom.tag.Tag(group, elem))

        action_str = str(entry["action"]).lower()
        try:
            action = AnonAction(action_str)
        except ValueError:
            raise ValueError(
                f"Rule #{i + 1}: unknown action '{action_str}'. "
                "Must be 'blank', 'placeholder', or 'delete'."
            )

        placeholder = (
            str(entry.get("placeholder", ""))
            if action == AnonAction.PLACEHOLDER
            else ""
        )
        rules[tag_int] = AnonRule(action=action, placeholder=placeholder)

    return rules
