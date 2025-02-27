# autospectate/windows_management.py

import pygetwindow as gw
import logging
import win32gui
import win32con
import time

def activate_window(window_title):
    """Programmatically activate and bring window to foreground."""
    try:
        # Find the window
        windows = gw.getWindowsWithTitle(window_title)
        if not windows:
            logging.error(f"Window '{window_title}' not found")
            return False
            
        window = windows[0]
        
        # Check if minimized
        if window.isMinimized:
            window.restore()
            time.sleep(0.5)
        
        # Bring to foreground
        window.activate()
        time.sleep(0.5)
        
        # Additional verification
        active_window = gw.getActiveWindow()
        is_focused = active_window and window_title in active_window.title
        
        if is_focused:
            logging.info(f"Successfully activated window: {window_title}")
            return True
        else:
            logging.warning(f"Failed to verify window activation: {window_title}")
            return False
            
    except Exception as e:
        logging.error(f"Error activating window '{window_title}': {e}")
        return False

def switch_to_window(window_title):
    """Switches focus to the window with the specified title with verification."""
    return activate_window(window_title)  # Use the more robust activate_window function

def ensure_window_focus(window_title):
    """Ensure window is focused with retries."""
    max_attempts = 3
    for attempt in range(max_attempts):
        if activate_window(window_title):
            return True
        logging.warning(f"Window activation attempt {attempt + 1}/{max_attempts} failed")
        time.sleep(1)
    return False

def minimize_window(window_title):
    """Minimize specified window."""
    try:
        windows = gw.getWindowsWithTitle(window_title)
        if windows:
            window = windows[0]
            if not window.isMinimized:
                window.minimize()
                logging.info(f"Minimized window: {window_title}")
                return True
            else:
                logging.info(f"Window '{window_title}' is already minimized")
                return True
        logging.error(f"Window '{window_title}' not found")
        return False
    except Exception as e:
        logging.error(f"Error minimizing window: {e}")
        return False

def force_minimize_window(window_title):
    """Force minimize window using Win32 API as fallback."""
    try:
        if minimize_window(window_title):
            return True
            
        def callback(hwnd, window_title):
            if win32gui.IsWindowVisible(hwnd) and window_title in win32gui.GetWindowText(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return False
            return True
        
        win32gui.EnumWindows(lambda hwnd, _: callback(hwnd, window_title), window_title)
        logging.info(f"Force minimized window: {window_title}")
        return True
    except Exception as e:
        logging.error(f"Error force minimizing window '{window_title}': {e}")
        return False

def verify_window_exists(window_title):
    """Verify if a window with the given title exists."""
    try:
        windows = gw.getWindowsWithTitle(window_title)
        return len(windows) > 0
    except Exception as e:
        logging.error(f"Error verifying window existence: {e}")
        return False
    
def verify_aoe2_window():
    """Just verify AoE2 window exists without activating it."""
    try:
        windows = gw.getWindowsWithTitle("Age of Empires II: Definitive Edition")
        return len(windows) > 0
    except Exception as e:
        logging.error(f"Error verifying AoE2 window: {e}")
        return False
    
def setup_captureage_window():
    """Initial setup of CaptureAge window position and size."""
    try:
        windows = gw.getWindowsWithTitle("CaptureAge")
        if windows:
            window = windows[0]
            # Only reposition/resize if needed
            if window.left != 0 or window.top != 0 or window.width != 1920 or window.height != 1080:
                window.moveTo(0, 0)
                window.resizeTo(1920, 1080)
                logging.info("Set up CaptureAge window position and size")
            return True
        return False
    except Exception as e:
        logging.error(f"Error setting up CaptureAge window: {e}")
        return False

def switch_to_captureage():
    """Focus CaptureAge window without repositioning."""
    try:
        windows = gw.getWindowsWithTitle("CaptureAge")
        if windows:
            windows[0].activate()
            time.sleep(0.1)  # Short delay for focus to take effect
            
            # Verify focus was obtained
            active = gw.getActiveWindow()
            if active and "CaptureAge" in active.title:
                return True
            
            logging.warning("Failed to verify CaptureAge window focus")
            return False
        return False
    except Exception as e:
        logging.error(f"Error switching to CaptureAge: {e}")
        return False