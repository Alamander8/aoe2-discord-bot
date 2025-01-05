import time
import logging
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab
from pathlib import Path
from playwright.sync_api import sync_playwright
from typing import Optional, Dict, Tuple
from obs_control import create_obs_manager

from autospectate.spectator_core import SpectatorCore
from autospectate.web_automation import find_and_spectate_game
from autospectate.windows_management import switch_to_window
from autospectate.utils import setup_logging, capture_screen

class MainFlow:
    def __init__(self, config: Dict):
        """Initialize the main flow controller."""
        self.config = config
        self.setup_logging()
        
        # Core configuration
        self.game_window_title = "Age of Empires II: Definitive Edition"
        self.companion_url = config.get('AOE2_COMPANION_URL', 'https://www.aoe2companion.com/ongoing')
        
        # Screen regions for color detection
        self.color_regions = {
            'player1': {'x': 210, 'y': 1, 'width': 355, 'height': 41},
            'player2': {'x': 565, 'y': 1, 'width': 355, 'height': 41}
        }
        
        # Timeouts and delays
        self.game_load_timeout = 120
        self.color_check_interval = 0.5
        self.force_color_max_attempts = 10
        self.between_games_delay = 120
        
        # Initialize state
        self.spectator_core = None
        self.current_game_start = None
        self.capture_age_title = "CaptureAge"
        self.initial_game_wait = 180  # 3 minutes wait before switching to CaptureAge
        self.obs_manager = create_obs_manager()

    def setup_logging(self):
        """Set up logging configuration."""
        setup_logging(Path('logs/main_flow.log'))
        logging.info("MainFlow initialized")

    def wait_for_game_load(self) -> bool:
        """
        Wait for the game to load by monitoring specific UI elements.
        Returns True if game loaded successfully, False on timeout.
        """
        logging.info("Waiting for game to load...")
        start_time = time.time()
        
        while time.time() - start_time < self.game_load_timeout:
            try:
                # Capture the resource UI area where numbers appear
                resource_area = capture_screen((
                    self.config.GAME_AREA_X + 210,
                    self.config.GAME_AREA_Y + 1,
                    self.config.GAME_AREA_X + 565,
                    self.config.GAME_AREA_Y + 42
                ))
                
                if resource_area is not None:
                    # Convert to grayscale and check if numbers are visible
                    gray = cv2.cvtColor(resource_area, cv2.COLOR_BGR2GRAY)
                    if np.mean(gray) > 20:  # Check if there's visible content
                        logging.info("Game UI detected - load complete")
                        return True
                
                time.sleep(1)
                
            except Exception as e:
                logging.error(f"Error checking game load: {e}")
                time.sleep(1)
        
        logging.error("Game load timeout exceeded")
        return False



    def start_continuous_stream(self):
        """Start the continuous streaming process."""
        try:
            if not self.obs_manager.connect():
                logging.error("Failed to connect to OBS")
                return False

            self.obs_manager.switch_scene(self.obs_manager.scenes['GOING_LIVE'])
            if not self.obs_manager.is_streaming():
                self.obs_manager.start_stream()

            return True
        except Exception as e:
            logging.error(f"Error starting continuous stream: {e}")
            return False

    def handle_game_cycle(self, match_info):
        """Handle a single game cycle."""
        try:
            if not switch_to_window(self.game_window_title):
                return False

            if not self.wait_for_game_load():
                return False

            logging.info("Waiting 3 minutes before switching to CaptureAge...")
            time.sleep(self.initial_game_wait)

            if not switch_to_window(self.capture_age_title):
                return False

            if not self.force_player_colors():
                return False

            self.obs_manager.switch_scene(self.obs_manager.scenes['GAME'])
            self.obs_manager.update_game_source(f"{self.capture_age_title}:Chrome_WidgetWin_1:CaptureAge.exe")

            self.spectator_core = SpectatorCore(self.config)
            self.current_game_start = time.time()
            
            while not self.spectator_core.detect_game_over():
                self.spectator_core.run_spectator_iteration()
                time.sleep(0.5)

            return True
        except Exception as e:
            logging.error(f"Error in game cycle: {e}")
            return False

    def adjust_game_view(self):
        """Adjust game view settings (ALT+D, ALT+F)."""
        try:
            logging.info("Adjusting game view settings...")
            
            # Press ALT+D for first view adjustment
            pyautogui.hotkey('alt', 'd')
            time.sleep(0.5)
            
            # Press ALT+F for second view adjustment
            pyautogui.hotkey('alt', 'f')
            time.sleep(0.5)
            
            logging.info("View settings adjusted successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error adjusting game view: {e}")
            return False

    def verify_player_colors(self) -> Tuple[bool, bool]:
        """
        Verify if players are set to correct colors.
        Returns tuple of (is_player1_red, is_player2_blue).
        """
        try:
            # Capture player UI regions
            p1_region = capture_screen((
                self.config.GAME_AREA_X + self.color_regions['player1']['x'],
                self.config.GAME_AREA_Y + self.color_regions['player1']['y'],
                self.config.GAME_AREA_X + self.color_regions['player1']['x'] + self.color_regions['player1']['width'],
                self.config.GAME_AREA_Y + self.color_regions['player1']['y'] + self.color_regions['player1']['height']
            ))
            
            p2_region = capture_screen((
                self.config.GAME_AREA_X + self.color_regions['player2']['x'],
                self.config.GAME_AREA_Y + self.color_regions['player2']['y'],
                self.config.GAME_AREA_X + self.color_regions['player2']['x'] + self.color_regions['player2']['width'],
                self.config.GAME_AREA_Y + self.color_regions['player2']['y'] + self.color_regions['player2']['height']
            ))
            
            if p1_region is None or p2_region is None:
                return False, False
            
            # Convert to HSV for better color detection
            p1_hsv = cv2.cvtColor(p1_region, cv2.COLOR_BGR2HSV)
            p2_hsv = cv2.cvtColor(p2_region, cv2.COLOR_BGR2HSV)
            
            # Define color ranges for red and blue
            red_lower = np.array([0, 150, 70])
            red_upper = np.array([10, 255, 255])
            blue_lower = np.array([100, 150, 0])
            blue_upper = np.array([140, 255, 255])
            
            # Check for red and blue in respective regions
            is_p1_red = np.any(cv2.inRange(p1_hsv, red_lower, red_upper))
            is_p2_blue = np.any(cv2.inRange(p2_hsv, blue_lower, blue_upper))
            
            return is_p1_red, is_p2_blue
            
        except Exception as e:
            logging.error(f"Error verifying player colors: {e}")
            return False, False

    def force_player_colors(self) -> bool:
        """
        Force players to Red and Blue colors in the bottom right UI.
        Returns True if successful, False otherwise.
        """
        logging.info("Forcing player colors...")
        
        # UI region for player names (bottom right, above minimap)
        ui_region = {
            'x': 1180,
            'y': 980,
            'width': 320,
            'height': 250
        }
        
        # Click positions relative to UI region
        name_positions = {
            'top': {
                'x': 66,
                'y': 22
            },
            'bottom': {
                'x': 66,
                'y': 64
            }
        }
        
        def check_color(x, y, target_color):
            try:
                bbox = (x - 5, y - 5, x + 5, y + 5)
                screenshot = ImageGrab.grab(bbox=bbox)
                img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)
                
                if target_color == 'blue':
                    lower = np.array([85, 200, 200])  # UI bright blue
                    upper = np.array([95, 255, 255])
                else:  # red
                    lower = np.array([0, 150, 150])
                    upper = np.array([10, 255, 255])
                    
                mask = cv2.inRange(img, lower, upper)
                result = np.any(mask)
                logging.info(f"Color check for {target_color}: {'Found' if result else 'Not found'}")
                return result
            except Exception as e:
                logging.error(f"Error checking color: {e}")
                return False
        
        try:
            # First make top name blue
            attempts = 0
            while attempts < self.force_color_max_attempts:
                logging.info(f"Setting top name to blue (attempt {attempts + 1})")
                
                # Click position for top name
                click_x = ui_region['x'] + name_positions['top']['x']
                click_y = ui_region['y'] + name_positions['top']['y']
                
                if check_color(click_x, click_y, 'blue'):
                    logging.info("Top name is blue")
                    break
                    
                pyautogui.click(click_x, click_y)
                time.sleep(self.color_check_interval)
                attempts += 1
            
            # Then make bottom name red
            attempts = 0
            while attempts < self.force_color_max_attempts:
                logging.info(f"Setting bottom name to red (attempt {attempts + 1})")
                
                # Click position for bottom name
                click_x = ui_region['x'] + name_positions['bottom']['x']
                click_y = ui_region['y'] + name_positions['bottom']['y']
                
                if check_color(click_x, click_y, 'red'):
                    logging.info("Bottom name is red")
                    break
                    
                pyautogui.click(click_x, click_y)
                time.sleep(self.color_check_interval)
                attempts += 1
                
            # Check final state
            top_x = ui_region['x'] + name_positions['top']['x']
            top_y = ui_region['y'] + name_positions['top']['y']
            bottom_x = ui_region['x'] + name_positions['bottom']['x']
            bottom_y = ui_region['y'] + name_positions['bottom']['y']
            
            success = (check_color(top_x, top_y, 'blue') and 
                    check_color(bottom_x, bottom_y, 'red'))
            
            if success:
                logging.info("Successfully set player colors")
            else:
                logging.warning("Failed to set correct player colors")
                
            return success
            
        except Exception as e:
            logging.error(f"Error during color forcing: {e}")
            return False

    def run_spectator(self) -> bool:
        """
        Initialize and run the spectator core.
        Returns True if completed normally, False on error.
        """
        try:
            self.spectator_core = SpectatorCore(self.config)
            self.current_game_start = time.time()
            
            logging.info("Starting spectator core...")
            self.spectator_core.run_spectator()
            
            return True
            
        except Exception as e:
            logging.error(f"Error in spectator core: {e}")
            return False

    def main_loop(self):
        """Main continuous streaming loop."""
        if not self.start_continuous_stream():
            return

        while True:
            try:
                self.obs_manager.switch_scene(self.obs_manager.scenes['GOING_LIVE'])
                logging.info("Looking for new game...")

                with sync_playwright() as playwright:
                    spectated, match_info = find_and_spectate_game(
                        playwright, 
                        {'AOE2_COMPANION_URL': self.companion_url}
                    )
                    
                    if not spectated:
                        logging.warning("No game found to spectate. Waiting before retry...")
                        time.sleep(60)
                        continue

                self.handle_game_cycle(match_info)

                self.obs_manager.switch_scene(self.obs_manager.scenes['GOING_LIVE'])
                logging.info(f"Waiting {self.between_games_delay} seconds before next game...")
                time.sleep(self.between_games_delay)

            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(10)
            finally:
                try:
                    self.obs_manager.switch_scene(self.obs_manager.scenes['GOING_LIVE'])
                except:
                    pass

def main():
    """Entry point."""
    # Create config object
    config = {
        'MINIMAP_X': 760,
        'MINIMAP_Y': 840,
        'MINIMAP_WIDTH': 350,
        'MINIMAP_HEIGHT': 300,
        'GAME_AREA_X': 0,
        'GAME_AREA_Y': 0,
        'GAME_AREA_WIDTH': 1920,
        'GAME_AREA_HEIGHT': 1080,
        'AOE2_COMPANION_URL': 'https://www.aoe2companion.com/ongoing'
    }
    
    # Initialize and run
    flow = MainFlow(config)
    flow.main_loop()

if __name__ == "__main__":
    main()