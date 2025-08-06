# autospectate/utils.py

import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import logging

def setup_logging(log_file):
    """
    Sets up logging to a file and the console.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def log_info(message):
    logging.info(message)

def log_error(message):
    logging.error(message)

def capture_screen(bbox):
    """
    Captures a portion of the screen defined by bbox.
    """
    screenshot = None
    try:
        screenshot = ImageGrab.grab(bbox=bbox)
        # Convert to numpy array while we have the screenshot
        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        return frame
    except Exception as e:
        log_error(f"Error capturing screen: {e}")
        return None
    finally:
        # CRITICAL: Always close the PIL image to prevent memory leak
        if screenshot:
            screenshot.close()
            del screenshot

def calculate_distance(pos1, pos2):
    """
    Calculates Euclidean distance between two positions.
    """
    return np.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

def click_position(x, y):
    """
    Clicks at the specified (x, y) screen coordinates.
    """
    try:
        pyautogui.click(x, y)
        log_info(f"Clicked at ({x}, {y})")
    except pyautogui.FailSafeException:
        log_error("Fail-safe triggered during click.")
    except Exception as e:
        log_error(f"Error during click: {e}")

def drag_and_follow(start_x, start_y, end_x, end_y, duration=1.5):
    """
    Performs a drag action from (start_x, start_y) to (end_x, end_y) and presses 'F'.
    """
    try:
        pyautogui.moveTo(start_x, start_y, duration=0.2)
        pyautogui.dragTo(end_x, end_y, duration=duration, button='left')
        pyautogui.press('f')
        log_info("Performed drag and pressed 'F'")
    except pyautogui.FailSafeException:
        log_error("Fail-safe triggered during drag.")
    except Exception as e:
        log_error(f"Error during drag and follow: {e}")
