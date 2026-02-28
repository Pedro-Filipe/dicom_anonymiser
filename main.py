"""
main.py — Entry point for the DICOM Anonymiser.

Usage:
    pip install pydicom Pillow numpy PyYAML
    python main.py
"""

import tkinter as tk

from app import MainApp


def main() -> None:
    root = tk.Tk()
    root.title("DICOM Anonymiser")
    root.geometry("1400x800")
    root.minsize(900, 600)
    MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
