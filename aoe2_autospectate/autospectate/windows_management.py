# autospectate/windows_management.py

import pygetwindow as gw
import logging

def switch_to_window(window_title):
    """
    Switches focus to the window with the specified title.
    """
    try:
        window = gw.getWindowsWithTitle(window_title)[0]
        if window:
            window.activate()
            logging.info(f"Switched to window: {window_title}")
    except IndexError:
        logging.error(f"Window with title '{window_title}' not found.")
    except Exception as e:
        logging.error(f"Error switching to window '{window_title}': {e}")
