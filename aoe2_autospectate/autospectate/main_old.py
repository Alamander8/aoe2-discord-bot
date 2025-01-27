import time
import logging
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab
from pathlib import Path
from playwright.sync_api import sync_playwright
from typing import Optional, Dict, Tuple

from spectator_core import SpectatorCore
from web_automation import find_and_spectate_game
from windows_management import switch_to_window
from utils import setup_logging, capture_screen
from obs_control import create_obs_manager

class MainFlow:
    def __init__(self, config):
            """Initialize the main flow controller."""
            self.config = config
            self.setup_logging()
            
            # Core configuration
            self.game_window_title = "CaptureAge"
            self.companion_url = getattr(config, 'AOE2_COMPANION_URL', 'https://www.aoe2companion.com/ongoing')
            
            # Initialize OBS Manager (only once!)
            self.obs_manager = create_obs_manager()
            if not self.obs_manager.connect():
                logging.error("Failed to connect to OBS")
                raise Exception("OBS connection failed")
            
            logging.info("Initializing with FindingGame scene...")    
            # Set initial scene to FindingGame
            if not self.obs_manager.switch_scene(self.obs_manager.scenes['FINDING_GAME']):
                logging.error("Failed to set initial scene")
                raise Exception("Failed to set initial scene")
                
            # Screen regions for color detection
            self.color_regions = {
                'player1': {'x': 210, 'y': 1, 'width': 355, 'height': 41},
                'player2': {'x': 565, 'y': 1, 'width': 355, 'height': 41}
            }
            
            # Timeouts and delays
            self.game_load_timeout = 130  # 2 minutes + 10 seconds
            self.color_check_interval = 2  # 2 seconds between checks
            self.force_color_max_attempts = 10
            self.between_games_delay = 60  # 1 minute
            
            # Initialize state
            self.spectator_core = None
            self.current_game_start = None
            self.capture_age_title = "CaptureAge"
            self.initial_game_wait = 180  # 3 minutes wait before switching to CaptureAge
        

    def ensure_scene_transition(self, target_scene):
        """Ensure proper scene transition with validation and retry logic."""
        if not hasattr(self, 'obs_manager') or self.obs_manager is None:
            print("OBS manager not properly initialized")
            return False

        max_attempts = 3
        retry_delay = 1.0  # seconds between retries

        for attempt in range(max_attempts):
            try:
                # First verify OBS connection
                if not self.obs_manager.ws or not self.obs_manager.ws.ws:
                    print(f"Attempt {attempt + 1}: OBS not connected, attempting reconnection...")
                    if not self.obs_manager.connect():
                        print("Failed to connect to OBS")
                        time.sleep(retry_delay)
                        continue

                # Verify the target scene exists
                if target_scene not in self.obs_manager.scenes.values():
                    print(f"Invalid target scene: {target_scene}")
                    return False

                # Attempt the scene switch
                if self.obs_manager.switch_scene(target_scene):
                    print(f"Successfully transitioned to {target_scene}")
                    return True

                print(f"Scene switch attempt {attempt + 1} failed, retrying...")
                time.sleep(retry_delay)

            except Exception as e:
                print(f"Error during scene transition (attempt {attempt + 1}): {str(e)}")
                if attempt < max_attempts - 1:  # Only sleep if we're going to retry
                    time.sleep(retry_delay)

        print(f"Failed to transition to {target_scene} after {max_attempts} attempts")
        return False
    
    def ensure_obs_connected(self):
            """Ensure OBS connection is active, reconnect if needed."""
            try:
                # Try to get current scene as a connection test
                if not self.obs_manager.ws or not self.obs_manager.ws.ws:
                    logging.info("OBS connection lost, attempting to reconnect...")
                    if not self.obs_manager.connect():
                        logging.error("Failed to reconnect to OBS")
                        return False
                return True
            except Exception as e:
                logging.error(f"Error checking OBS connection: {e}")
                return False

    def safe_scene_switch(self, scene_name):
        """Safely switch OBS scene with connection check."""
        if self.ensure_obs_connected():
            logging.info(f"Attempting to switch to scene: {scene_name}")
            if self.obs_manager.switch_scene(scene_name):
                logging.info(f"Successfully switched to scene: {scene_name}")
                return True
            else:
                logging.error(f"Failed to switch to scene: {scene_name}")
        return False


    def handle_game_end(self):
        """Handle game end cleanup sequence"""
        logging.info("Game ended, starting cleanup")
        
        # Single scene switch attempt at the start
        scene_switched = self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME'])
        
        if not scene_switched:
            logging.error("Failed to switch scene to FindingGame")
        
        # Clear text regardless of scene switch
        try:
            self.obs_manager.clear_match_text()
        except Exception as e:
            logging.warning(f"Non-critical error clearing match text: {e}")

        # Only proceed with game cleanup
        attempts = 0
        max_attempts = 5
        while attempts < max_attempts:
            if switch_to_window("Age of Empires II: Definitive Edition"):
                logging.info("Successfully switched to Age of Empires II: DE window")
                if self.cleanup_game_window():
                    return True
            attempts += 1
            time.sleep(2)
        
        logging.error("Failed to complete game end cleanup")
        return False


    def setup_logging(self):
        """Set up logging configuration."""
        # Create logs directory if it doesn't exist
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        # Now setup logging
        setup_logging(Path('logs/main_flow.log'))
        logging.info("MainFlow initialized")

    def wait_for_game_load(self) -> bool:
        """
        Wait for the game to load (2 minute timer).
        Returns True when complete.
        """
        logging.info("Waiting 2 minutes for game load...")
        time.sleep(self.game_load_timeout)
        return True


    def cleanup_game_window(self) -> bool:
        """
        Clean up the Age of Empires II window after a game ends.
        Returns True if successful, False otherwise.
        """
        try:
            logging.info("Cleaning up game window...")
            
            # Switch to Age of Empires II window
            if not switch_to_window('Age of Empires II: Definitive Edition'):
                logging.error("Failed to switch to Age of Empires II window")
                return False
                
            time.sleep(1)  # Wait for window focus
            
            # First sequence: TAB -> Enter
            logging.info("First menu sequence (TAB -> Enter)")
            pyautogui.press('tab')
            time.sleep(0.5)
            pyautogui.press('enter')
            time.sleep(1)
            
            # Second sequence: ESC -> Enter
            logging.info("Second menu sequence (ESC -> Enter)")
            pyautogui.press('esc')
            time.sleep(0.5)
            pyautogui.press('enter')
            time.sleep(1)
            
            # Final sequence: ESC --> ESC 
            logging.info("Final menu sequence (TAB x3 -> Enter)")
            pyautogui.press('esc')
            time.sleep(0.5)
            pyautogui.press('esc')

            time.sleep(2)  # Final wait to ensure everything is cleared
            return True
            
        except Exception as e:
            logging.error(f"Error cleaning up game window: {e}")
            return False

    def setup_game_view(self) -> bool:
        """
        Setup the game view with correct camera settings.
        Returns True if successful, False otherwise.
        """
        try:
            logging.info("Setting up game view...")
            
            # Set default orientation
            logging.info("Setting default orientation (Alt+D)")
            pyautogui.hotkey('alt', 'd')
            time.sleep(0.5)  # Short delay between commands
            
            # Set fixed camera
            logging.info("Setting fixed camera (Alt+F)")
            pyautogui.hotkey('alt', 'f')
            time.sleep(0.5)
            
            # Set zoom level
            logging.info("Setting zoom level (3)")
            pyautogui.press('3')
            time.sleep(0.5)
            
            return True
            
        except Exception as e:
            logging.error(f"Error setting up game view: {e}")
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
        
        try:
            # First make top name blue
            attempts = 0
            while attempts < self.force_color_max_attempts:
                logging.info(f"Setting top name to blue (attempt {attempts + 1})")
                
                # Click position for top name
                click_x = ui_region['x'] + name_positions['top']['x']
                click_y = ui_region['y'] + name_positions['top']['y']
                
                if self.check_color(click_x, click_y, 'blue'):
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
                
                if self.check_color(click_x, click_y, 'red'):
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
            
            success = (self.check_color(top_x, top_y, 'blue') and 
                    self.check_color(bottom_x, bottom_y, 'red'))
            
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
        Returns True if game ended normally, False on error.
        """
        try:
            # Create complete config object for SpectatorCore
            config_obj = type('Config', (), {
                'MINIMAP_X': self.config.MINIMAP_X,
                'MINIMAP_Y': self.config.MINIMAP_Y,
                'MINIMAP_WIDTH': self.config.MINIMAP_WIDTH,
                'MINIMAP_HEIGHT': self.config.MINIMAP_HEIGHT,
                'MINIMAP_PADDING': self.config.MINIMAP_PADDING,
                'GAME_AREA_X': self.config.GAME_AREA_X,
                'GAME_AREA_Y': self.config.GAME_AREA_Y,
                'GAME_AREA_WIDTH': self.config.GAME_AREA_WIDTH,
                'GAME_AREA_HEIGHT': self.config.GAME_AREA_HEIGHT,
                'PLAYER_HSV_RANGES': self.config.PLAYER_HSV_RANGES,  # Changed to use self.config
                'GAME_AGES': self.config.GAME_AGES,  # Changed to use self.config
                'BUILDING_ICON_MIN_AREA': self.config.BUILDING_ICON_MIN_AREA,  # Changed to use self.config
                'BUILDING_ICON_MAX_AREA': self.config.BUILDING_ICON_MAX_AREA,  # Changed to use self.config
                'BUILDING_ICON_MIN_CIRCULARITY': self.config.BUILDING_ICON_MIN_CIRCULARITY,  # Changed to use self.config
                'MAX_PLAYERS': self.config.MAX_PLAYERS,  # Changed to use self.config
                'EXPECTED_PLAYERS_1V1': self.config.EXPECTED_PLAYERS_1V1,  # Changed to use self.config
                'STARTING_TC_COUNT': self.config.STARTING_TC_COUNT  # Changed to use self.config
            })()

            self.spectator_core = SpectatorCore(config_obj)
            self.current_game_start = time.time()
            
            logging.info("Starting spectator core...")
            spectator_result = self.spectator_core.run_spectator()
            
            if spectator_result:
                logging.info("Game ended normally")
            else:
                logging.warning("Game ended unexpectedly")
                
            return spectator_result
            
        except Exception as e:
            logging.error(f"Error in spectator core: {e}")
            return False

    def main_loop(self):
        try:
            if not self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME']):
                raise Exception("Failed to set initial scene")
            
            while True:
                try:
                    logging.info("Starting new game cycle")
                    
                    # Single scene switch here
                    if not self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME']):
                        time.sleep(5)
                        continue

                    # Find and spectate game
                    with sync_playwright() as playwright:
                        spectated, match_info = find_and_spectate_game(
                            playwright, 
                            {'AOE2_COMPANION_URL': self.companion_url}
                        )
                        
                        if not spectated:
                            logging.warning("No game found to spectate. Waiting before retry...")
                            time.sleep(60)
                            continue
                        
                        logging.info(f"Match found: {match_info}")
                        if not self.obs_manager.update_match_text(match_info):
                            logging.error("Failed to update match text")

                    # Wait for game load first
                    if not self.wait_for_game_load():
                        continue

                    # Keep trying to switch to CaptureAge until successful
                    capture_age_attempts = 0
                    while capture_age_attempts < 5:
                        if switch_to_window(self.game_window_title):
                            logging.info("Successfully switched to CaptureAge window")
                            break
                        capture_age_attempts += 1
                        logging.warning(f"Failed to switch to CaptureAge window, attempt {capture_age_attempts}/5")
                        time.sleep(5)

                    if capture_age_attempts >= 5:
                        logging.error("Could not switch to CaptureAge window after multiple attempts")
                        continue

                    # Only proceed with color forcing if window switch was successful
                    if not self.force_player_colors():
                        continue
                    
                    if not self.setup_game_view():
                        logging.error("Failed to setup game view")
                        continue
                    
                    if not self.safe_scene_switch(self.obs_manager.scenes['GAME']):
                        logging.error("Failed to switch to Game scene")
                        continue

                    # Run spectator
                    spectator_result = self.run_spectator()
                    
                    # Single handler for game end
                    self.handle_game_end()
                    
                    logging.info("Waiting before next game...")
                    time.sleep(self.between_games_delay)
                    
                except Exception as e:
                    logging.error(f"Error in main loop: {e}")
                    self.handle_game_end()
                    time.sleep(10)
                    
        except Exception as e:
            logging.error(f"Critical error in main loop: {e}")
            self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME'])
            self.obs_manager.clear_match_text()



def main():
    """Entry point."""
    # Import config at the start of main to ensure it's accessible
    import config

    # Create complete config object with all necessary parameters
    spec_config = type('Config', (), {})()  # Create empty config object first
    
    # Copy all attributes from config module to our config object
    for attr in dir(config):
        # Skip internal attributes (those starting with '_')
        if not attr.startswith('_'):
            setattr(spec_config, attr, getattr(config, attr))
    
    # Initialize and run
    flow = MainFlow(spec_config)
    flow.main_loop()

if __name__ == "__main__":
    main()
