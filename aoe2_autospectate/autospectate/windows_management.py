# autospectate/windows_management.py

import pygetwindow as gw
import logging

def switch_to_window(window_title):
    """
    Switches focus to the window with the specified title.
    Returns True if successful, False otherwise.
    """
    try:
        window = gw.getWindowsWithTitle(window_title)[0]
        if window:
            window.activate()
            logging.info(f"Switched to window: {window_title}")
            return True  # Successfully switched
        return False  # Window found but couldn't activate
    except IndexError:
        logging.error(f"Window with title '{window_title}' not found.")
        return False
    except Exception as e:
        logging.error(f"Error switching to window '{window_title}': {e}")
        return False