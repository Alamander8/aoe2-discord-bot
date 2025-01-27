import cv2
import numpy as np
from PIL import ImageGrab, Image
import pyautogui
import time
import logging
from pathlib import Path

class UIPositionDebugger:
    def __init__(self):
        self.setup_logging()
        # Game area dimensions
        self.game_area = {
            'x': 0,
            'y': 0,
            'width': 1920,
            'height': 1080
        }
        
        # Region of interest for player UI (next to minimap)
        # Adjust the UI region height
        self.ui_roi = {
            'x': 1180,
            'y': 980,          # Move up another 30px (from 990 to 960) to catch GEOLOGIC
            'width': 320,
            'height': 250,     # Keep the taller height to ensure we get everything
        }

        self.name_regions = {
            'bottom': {
                'x': 4,
                'y': 10,       # Adjust to catch ALAMANDER8
                'width': 125,
                'height': 25
            },
            'top': {
                'x': 4,
                'y': 52,      # Move up significantly to catch GEOLOGIC
                'width': 125,
                'height': 25
            }
        }

    def setup_logging(self):
        """Set up logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('ui_debug.log'),
                logging.StreamHandler()
            ]
        )

    def capture_ui_area(self):
        """Capture the bottom-right UI area with player scores."""
        try:
            # Capture the score area next to minimap
            bbox = (
                self.ui_roi['x'],
                self.ui_roi['y'],
                self.ui_roi['x'] + self.ui_roi['width'],
                self.ui_roi['y'] + self.ui_roi['height']
            )
            screenshot = ImageGrab.grab(bbox=bbox)
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception as e:
            logging.error(f"Error capturing UI area: {e}")
            return None

    def detect_player_name_regions(self, ui_image):
        """Just use fixed coordinates to define name regions."""
        try:
            debug_image = ui_image.copy()
            
            top_region = self.name_regions['top'].copy()
            bottom_region = self.name_regions['bottom'].copy()
            
            # Add click positions at center of each box
            top_region['click_x'] = top_region['x'] + (top_region['width'] // 2)
            top_region['click_y'] = top_region['y'] + (top_region['height'] // 2)
            
            bottom_region['click_x'] = bottom_region['x'] + (bottom_region['width'] // 2)
            bottom_region['click_y'] = bottom_region['y'] + (bottom_region['height'] // 2)
            
            # Draw debug boxes and click points
            cv2.rectangle(debug_image,
                (top_region['x'], top_region['y']),
                (top_region['x'] + top_region['width'], top_region['y'] + top_region['height']),
                (0, 255, 0), 2)
            cv2.circle(debug_image, 
                (top_region['click_x'], top_region['click_y']), 
                3, (0, 0, 255), -1)
                
            cv2.rectangle(debug_image,
                (bottom_region['x'], bottom_region['y']),
                (bottom_region['x'] + bottom_region['width'], bottom_region['y'] + bottom_region['height']),
                (0, 255, 0), 2)
            cv2.circle(debug_image, 
                (bottom_region['click_x'], bottom_region['click_y']), 
                3, (0, 0, 255), -1)
            
            cv2.imwrite('debug_ui_detection.png', debug_image)
            return top_region, bottom_region
            
        except Exception as e:
            logging.error(f"Error detecting player name regions: {e}")
            return None, None


    def click_test_visualization(self, top_region, bottom_region):
        """Create a visualization of where clicks would occur."""
        try:
            # Create visualization with light gray background
            vis_image = np.ones((
                self.ui_roi['height'],
                self.ui_roi['width'],
                3
            ), dtype=np.uint8) * 40
            
            # Draw grid for reference
            for i in range(0, self.ui_roi['width'], 20):
                cv2.line(vis_image, (i, 0), (i, self.ui_roi['height']), (60, 60, 60), 1)
            for i in range(0, self.ui_roi['height'], 20):
                cv2.line(vis_image, (0, i), (self.ui_roi['width'], i), (60, 60, 60), 1)
            
            # Draw regions and click points
            if top_region:
                cv2.rectangle(vis_image,
                    (top_region['x'], top_region['y']),
                    (top_region['x'] + top_region['width'], top_region['y'] + top_region['height']),
                    (0, 255, 0), 2)
                cv2.circle(vis_image,
                    (top_region['click_x'], top_region['click_y']),
                    5, (0, 0, 255), -1)
                cv2.putText(vis_image,
                    f"({top_region['click_x']}, {top_region['click_y']})",
                    (top_region['click_x'] + 10, top_region['click_y']),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                    
            if bottom_region:
                cv2.rectangle(vis_image,
                    (bottom_region['x'], bottom_region['y']),
                    (bottom_region['x'] + bottom_region['width'], bottom_region['y'] + bottom_region['height']),
                    (0, 255, 0), 2)
                cv2.circle(vis_image,
                    (bottom_region['click_x'], bottom_region['click_y']),
                    5, (0, 0, 255), -1)
                cv2.putText(vis_image,
                    f"({bottom_region['click_x']}, {bottom_region['click_y']})",
                    (bottom_region['click_x'] + 10, bottom_region['click_y']),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                    
            cv2.imwrite('click_positions.png', vis_image)
            return vis_image
            
        except Exception as e:
            logging.error(f"Error creating click visualization: {e}")
            return None
 

    def check_name_color(self, region_info, target_color):
        """
        Check if a name region is the target color.
        target_color should be 'red' or 'blue'
        """
        try:
            # Get region coordinates from region_info
            bbox = (
                self.ui_roi['x'] + region_info['x'],
                self.ui_roi['y'] + region_info['y'],
                self.ui_roi['x'] + region_info['x'] + region_info['width'],
                self.ui_roi['y'] + region_info['y'] + region_info['height']
            )
            
            screenshot = ImageGrab.grab(bbox=bbox)
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)
            
            # Define color ranges
            if target_color == 'blue':
                lower = np.array([100, 150, 150])
                upper = np.array([140, 255, 255])
            else:  # red
                lower = np.array([0, 150, 150])
                upper = np.array([10, 255, 255])
                
            # Check if color is present
            mask = cv2.inRange(img, lower, upper)
            
            # Save debug image
            debug_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            cv2.imwrite(f'color_check_{target_color}.png', debug_img)
            cv2.imwrite(f'color_mask_{target_color}.png', mask)
            
            has_color = np.any(mask)
            logging.info(f"Color check for {target_color}: {'Found' if has_color else 'Not found'}")
            return has_color
            
        except Exception as e:
            logging.error(f"Error checking name color: {e}")
            return False


    def check_color(self, x, y, target_color):
        """Check if pixel at (x,y) is the target color."""
        try:
            # Capture small region around point
            bbox = (x - 5, y - 5, x + 5, y + 5)
            screenshot = ImageGrab.grab(bbox=bbox)
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)
            
            # Define color ranges - adjusted for UI colors
            if target_color == 'blue':
                # Bright UI blue (like LMOFFEREINS)
                lower = np.array([105, 50, 50])  # More saturated/brighter blue
                upper = np.array([125, 255, 255])  # Closer to cyan range
            else:  # red
                lower = np.array([0, 150, 150])
                upper = np.array([10, 255, 255])
                
            mask = cv2.inRange(img, lower, upper)
            result = np.any(mask)
            
            # Save debug images
            cv2.imwrite(f'debug_{target_color}_check.png', cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR))
            cv2.imwrite(f'debug_{target_color}_mask.png', mask)
            
            logging.info(f"Color check for {target_color}: {'Found' if result else 'Not found'}")
            return result
            
        except Exception as e:
            logging.error(f"Error checking color: {e}")
            return False
    

    def cycle_colors_until_match(self):
        """Cycle colors until top is blue and bottom is red."""
        logging.info("Starting color cycling...")
        max_attempts = 10

        # First handle top name (make it blue)
        attempts = 0
        while attempts < max_attempts:
            logging.info(f"Clicking top name for blue ({attempts + 1}/{max_attempts})")
            pyautogui.click(self.ui_roi['x'] + 66, self.ui_roi['y'] + 22)  # Top name coordinates
            time.sleep(0.5)
            
            # Save debug image for color checking
            bbox = (self.ui_roi['x'] + 61, self.ui_roi['y'] + 17, self.ui_roi['x'] + 71, self.ui_roi['y'] + 27)
            screenshot = ImageGrab.grab(bbox=bbox)
            img = np.array(screenshot)
            cv2.imwrite(f'color_check_blue_{attempts}.png', cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            
            if self.check_color(self.ui_roi['x'] + 66, self.ui_roi['y'] + 22, 'blue'):
                logging.info("Top name is now blue!")
                break
            attempts += 1

        # Then handle bottom name (make it red)
        attempts = 0
        while attempts < max_attempts:
            logging.info(f"Clicking bottom name for red ({attempts + 1}/{max_attempts})")
            pyautogui.click(self.ui_roi['x'] + 66, self.ui_roi['y'] + 64)  # Bottom name coordinates
            time.sleep(0.5)
            
            if self.check_color(self.ui_roi['x'] + 66, self.ui_roi['y'] + 64, 'red'):
                logging.info("Bottom name is now red!")
                break
            attempts += 1




    def test_click_positions(self, top_region, bottom_region):
        """Simulate clicks with visual feedback."""
        try:
            if top_region:
                click_x = self.ui_roi['x'] + top_region['click_x']
                click_y = self.ui_roi['y'] + top_region['click_y']
                logging.info(f"Top click position: ({click_x}, {click_y})")
                # Uncomment to actually test clicks:
                # pyautogui.click(click_x, click_y)
                # time.sleep(0.5)

            if bottom_region:
                click_x = self.ui_roi['x'] + bottom_region['click_x']
                click_y = self.ui_roi['y'] + bottom_region['click_y']
                logging.info(f"Bottom click position: ({click_x}, {click_y})")
                # Uncomment to actually test clicks:
                # pyautogui.click(click_x, click_y)
                # time.sleep(0.5)
                
        except Exception as e:
            logging.error(f"Error testing click positions: {e}")

    def run_debug_session(self):
        """Run a complete debug session."""
        logging.info("Starting UI position debug session")
        
        # Capture UI area
        ui_image = self.capture_ui_area()
        if ui_image is None:
            logging.error("Failed to capture UI area")
            return
        
        # Save raw capture
        cv2.imwrite('ui_capture_raw.png', ui_image)
        
        # Detect regions
        top_region, bottom_region = self.detect_player_name_regions(ui_image)
        
        # Create visualization
        self.click_test_visualization(top_region, bottom_region)
        
        # Log detected positions
        if top_region:
            logging.info(f"Top player region detected: {top_region}")
        if bottom_region:
            logging.info(f"Bottom player region detected: {bottom_region}")
        
        # Offer to test clicks
        self.test_click_positions(top_region, bottom_region)

def main():
    debugger = UIPositionDebugger()
    
    # First run the debug session to make sure our regions are correct
    debugger.run_debug_session()
    
    # Add a small delay
    time.sleep(1)
    
    print("Starting color cycling test...")
    print("Press Ctrl+C to stop")
    
    try:
        debugger.cycle_colors_until_match()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error during color cycling: {e}")

if __name__ == "__main__":
    main()




    def check_color(self, x, y, target_color):
        """Check if pixel at (x,y) is the target color."""
        try:
            bbox = (x - 5, y - 5, x + 5, y + 5)
            screenshot = ImageGrab.grab(bbox=bbox)
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)

            if target_color == 'blue':
                # Further refined blue color range
                lower = np.array([100, 120, 180])  # Adjusted for brighter, saturated blue
                upper = np.array([140, 255, 255])
            else:  # red
                # Further refined and expanded red color range
                lower1 = np.array([0, 150, 120])    # Lower end of red hue
                upper1 = np.array([10, 255, 255])
                lower2 = np.array([170, 150, 120])  # Upper end of red hue
                upper2 = np.array([180, 255, 255])

                # Create masks for both hue ranges
                mask1 = cv2.inRange(img, lower1, upper1)
                mask2 = cv2.inRange(img, lower2, upper2)

                # Combine masks
                mask = cv2.bitwise_or(mask1, mask2)

            mask = cv2.inRange(img, lower, upper) if target_color == 'blue' else mask
            result = np.any(mask)
            logging.info(f"Color check for {target_color}: {'Found' if result else 'Not found'}")
            return result
        except Exception as e:
            logging.error(f"Error checking color: {e}")
            return False