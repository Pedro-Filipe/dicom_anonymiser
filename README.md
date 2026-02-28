# DICOM Anonymiser

A desktop application for browsing, inspecting, and anonymising DICOM medical imaging files.

## Features

- Browse a folder recursively to discover all DICOM files
- View DICOM images with automatic windowing and modality LUT applied
- Inspect full DICOM headers, including nested sequences (SQ)
- Search/filter tags by keyword, tag address, or value
- Select individual tags and configure per-tag anonymisation rules (blank, placeholder, or delete)
- Apply rules to the current file or batch-process all files in the folder
- Save and load anonymisation profiles as human-readable YAML files

## Requirements

- Python 3.10+
- tkinter (included with standard Python on Windows and macOS; on Linux install `python3-tk`)

## Installation

```bash
pip install pydicom Pillow numpy PyYAML
```

For JPEG / JPEG2000 / JPEG-LS compressed DICOM support, also install:

```bash
pip install "pylibjpeg[all]"
```

## Running

```bash
python main.py
```

## Usage

### Opening files

1. Click **Open Folder** (or `File → Open Folder…`, `Ctrl+O`).
2. Select a directory. The app will recursively discover all valid DICOM files and list them in the left panel.
3. Click any file in the list to load it. The image appears in the centre panel and the DICOM header tree populates on the right.

### Browsing the header tree

- Tags are shown as `(gggg,eeee) Keyword` with their VR and value.
- Sequence tags (SQ) are expandable and show each item's sub-tags nested underneath.
- Use the **Search** bar at the top of the tag panel to filter by keyword, tag address, or value. Press `Esc` or click `✕` to clear.

### Selecting tags for anonymisation

- Click the checkbox glyph (☐/☑) to the left of any tag to select or deselect it.
- Use **Anonymise → Select All Tags** to check everything, or **Clear Selection** to uncheck all.

### Configuring anonymisation rules

1. Select one or more tags.
2. Click **Anonymise Selected** (or `Anonymise → Configure Rules…`).
3. For each selected tag, choose an action:
   - **blank** — replace the value with an empty/zero value appropriate for the VR
   - **placeholder** — replace the value with a custom string you provide
   - **delete** — remove the tag entirely from the dataset
4. Click **Apply to Current File** to modify only the file currently displayed, or **Apply to All Files** to queue the rules for batch processing.

### Saving anonymised files

- **Save Current** (`Ctrl+S`) — saves the currently displayed (and already modified) file to a location you choose.
- **Save All** (`Ctrl+Shift+S`) — applies the active rules to every file in the folder and saves them all to an output folder you choose. A progress bar is shown during the operation. Original files are never overwritten.

### Saving and loading profiles

A profile stores your anonymisation rules so you can reuse them across sessions.

- **Profile → Save Profile…** (`Ctrl+Shift+P`) — saves the current rules to a `.yaml` file.
- **Profile → Load Profile…** (`Ctrl+Shift+L`) — loads rules from a previously saved `.yaml` file and marks any matching tags as checked.

#### Profile file format

```yaml
rules:
  - tag: 0010,0010
    keyword: PatientName
    action: blank
  - tag: 0010,0020
    keyword: PatientID
    action: placeholder
    placeholder: ANON_001
  - tag: 0010,0030
    keyword: PatientBirthDate
    action: delete
```

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open folder |
| `Ctrl+S` | Save current file |
| `Ctrl+Shift+S` | Save all files |
| `Ctrl+Shift+L` | Load profile |
| `Ctrl+Shift+P` | Save profile |
| `Ctrl+Q` | Quit |
