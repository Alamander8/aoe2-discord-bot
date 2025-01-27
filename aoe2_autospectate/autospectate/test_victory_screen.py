import cv2
import numpy as np
from PIL import ImageGrab
import time

def test_victory_detection():
    victory_box = (
        800,   # X start
        120,   # Y start - moved up to catch victory text
        1120,  # X end
        300    # Y end - adjusted for victory message height
    )
    
    while True:
        try:
            screenshot = ImageGrab.grab(bbox=victory_box)
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            cv2.imwrite('debug_victory_capture.png', frame)
            
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            blue_text = cv2.inRange(hsv, 
                np.array([100, 150, 200]), 
                np.array([140, 255, 255])
            )
            red_text = cv2.inRange(hsv, 
                np.array([0, 150, 200]), 
                np.array([10, 255, 255])
            )
            
            cv2.imwrite('debug_blue_mask.png', blue_text)
            cv2.imwrite('debug_red_mask.png', red_text)
            
            blue_pixels = np.sum(blue_text > 0)
            red_pixels = np.sum(red_text > 0)
            
            print(f"Blue pixels: {blue_pixels}")
            print(f"Red pixels: {red_pixels}")
            print("-" * 50)  # Separator for readability
            time.sleep(1)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    test_victory_detection()