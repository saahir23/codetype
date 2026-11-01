"""codetype: a trainer where you type along AI-generated code
while a side panel explains each block. Run:  python main.py"""
import sys
import tkinter as tk

from ui import App


def main():
    if sys.platform == "win32":
        try:  # crisp text on high-DPI Windows screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
