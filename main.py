"""
main.py — Entry point for the DICOM Anonymiser.

Usage:
    pip install pydicom Pillow numpy PyYAML
    python main.py
"""

from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk

from app import MainApp


def main() -> None:
    root = tk.Tk()
    root.title("DICOM Anonymiser")
    root.geometry("1400x800")
    root.minsize(900, 600)
    try:
        icon_path = Path(__file__).parent / "assets" / "icon.png"
        icon = ImageTk.PhotoImage(Image.open(icon_path))
        root.iconphoto(True, icon)
    except Exception:
        pass
    MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
