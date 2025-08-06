# autospectate/main_flow.py

import time
import logging
import pyautogui
import cv2
import requests
import numpy as np
from PIL import ImageGrab
from pathlib import Path
from playwright.sync_api import sync_playwright
from typing import Optional, Dict, Tuple

from state_management import StateManager, GameState
from health_check import HealthCheck
from recovery import RecoveryManager
from spectator_core import SpectatorCore
from web_automation import find_and_spectate_game
from utils import setup_logging, capture_screen
from obs_control import create_obs_manager
from betting_bridge import BettingBridge
from windows_management import * 
from windows_management import switch_to_captureage
from simple_memory_monitor import SimpleMemoryMonitor
from simple_restart_helper import SimpleRestartHelper


class MainFlow:
    def __init__(self, config):
        """Initialize the main flow controller."""
        self.config = config
        self.setup_logging()

        # Initiliaze Betting System 
        self.betting_bridge = BettingBridge(channel='saltyempires')
        self.betting_bridge.start()

        # Initialize management systems
        self.state_manager = StateManager()
        self.health_checker = HealthCheck()
        self.recovery_manager = RecoveryManager(self)
        self.restart_helper = SimpleRestartHelper()
        self.restart_helper.capture_age_path = r"C:\Users\Alex Hogancamp\AppData\Local\Programs\CaptureAge\CaptureAge.exe"
        self.restart_manager = RestartManager(self.restart_helper)

        self.memory_monitor = SimpleMemoryMonitor()

        # Core configuration
        self.game_window_title = "CaptureAge"
        self.companion_url = getattr(config, 'AOE2_COMPANION_URL', 'https://www.aoe2companion.com/ongoing')
        
        # Initialize OBS Manager
        self.obs_manager = create_obs_manager()
        if not self.obs_manager.connect():
            logging.error("Failed to connect to OBS")
            raise Exception("OBS connection failed")
        
        logging.info("Initializing with FindingGame scene...")    
        if not self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME']):
            logging.error("Failed to set initial scene")
            raise Exception("Failed to set initial scene")
                
        # Screen regions for color detection
        self.color_regions = {
            'player1': {'x': 210, 'y': 1, 'width': 355, 'height': 41},
            'player2': {'x': 565, 'y': 1, 'width': 355, 'height': 41}
        }
        
        # Timeouts and delays
        self.game_load_timeout = 130  # 120 seconds + 10 seconds
        self.color_check_interval = 3  # 3 seconds between checks
        self.force_color_max_attempts = 10
        self.between_games_delay = 10  # 1 minute
        
        # Initialize state
        self.spectator_core = SpectatorCore(config, betting_bridge=self.betting_bridge)
        self.current_game_start = None
        self.capture_age_title = "CaptureAge"
        self.initial_game_wait = 180  # 3 minutes wait before switching to CaptureAge

    def setup_logging(self):
        """Set up logging configuration."""
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        setup_logging(Path('logs/main_flow.log'))
        logging.info("MainFlow initialized")

    def manual_restart(self):
        """Call this if you want to manually restart"""
        logging.info("🔧 Manual restart requested")
        if self.restart_manager.perform_restart("manual"):
            return True
        return False


    def ensure_scene_transition(self, target_scene):
        """Ensure proper scene transition with validation and retry logic."""
        if not hasattr(self, 'obs_manager') or self.obs_manager is None:
            logging.error("OBS manager not properly initialized")
            return False

        max_attempts = 3
        retry_delay = 1.0

        for attempt in range(max_attempts):
            try:
                if not self.obs_manager.ws or not self.obs_manager.ws.ws:
                    logging.info(f"Attempt {attempt + 1}: OBS not connected, attempting reconnection...")
                    if not self.obs_manager.connect():
                        logging.error("Failed to connect to OBS")
                        time.sleep(retry_delay)
                        continue

                if target_scene not in self.obs_manager.scenes.values():
                    logging.error(f"Invalid target scene: {target_scene}")
                    return False

                if self.obs_manager.switch_scene(target_scene):
                    logging.info(f"Successfully transitioned to {target_scene}")
                    return True

                logging.warning(f"Scene switch attempt {attempt + 1} failed, retrying...")
                time.sleep(retry_delay)

            except Exception as e:
                logging.error(f"Error during scene transition (attempt {attempt + 1}): {str(e)}")
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)

        logging.error(f"Failed to transition to {target_scene} after {max_attempts} attempts")
        return False

    def ensure_obs_connected(self):
        """Ensure OBS connection is active, reconnect if needed."""
        try:
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

    def wait_for_game_load(self) -> bool:
            """Wait for the game to load (2 minute timer)."""
            try:
                logging.info("Waiting 2 minutes for game load...")
                time.sleep(self.game_load_timeout)
                return True
            except Exception as e:
                logging.error(f"Error during game load wait: {e}")
                return False

    def cleanup_game_window(self) -> bool:
        """Clean up the Age of Empires II window after a game ends."""
        try:
            logging.info("Cleaning up game window...")
            
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
            logging.info("Final menu sequence (ESC -> ESC)")
            pyautogui.press('esc')
            time.sleep(0.5)
            pyautogui.press('esc')

            time.sleep(2)
            return True
            
        except Exception as e:
            logging.error(f"Error cleaning up game window: {e}")
            return False

    def setup_game_view(self) -> bool:
        """Setup the game view with correct camera settings using mouse wheel zoom."""
        try:
            logging.info("Setting up game view...")
            
            # Set default orientation
            logging.info("Setting default orientation (Alt+D)")
            pyautogui.hotkey('alt', 'd')
            time.sleep(0.8)  # Longer delay to ensure it processes
            
            # Set fixed camera
            logging.info("Setting fixed camera (Alt+F)")
            pyautogui.hotkey('alt', 'f')
            time.sleep(0.8)
            
            # Use mouse wheel to zoom out instead of broken number keys
            logging.info("Zooming out with mouse wheel...")
            
            # Get screen center for mouse position (using config values)
            screen_center_x = self.config.GAME_AREA_WIDTH // 2
            screen_center_y = self.config.GAME_AREA_HEIGHT // 2
            
            # Move mouse to center of game area
            pyautogui.moveTo(screen_center_x, screen_center_y, duration=0.2)
            time.sleep(0.3)
            
            # Scroll out several times to get a good zoom level
            for i in range(20):
                pyautogui.scroll(-12)  # -12 = -3 × 4 for quadruple zoom
                time.sleep(0.2)
                logging.info(f"Zoom scroll {i+1}/6")
            
            logging.info("Game view setup completed with mouse wheel zoom")
            return True
            
        except Exception as e:
            logging.error(f"Error setting up game view: {e}")
            return False


    def verify_player_colors(self) -> Tuple[bool, bool]:
        """Verify if players are set to correct colors."""
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
        screenshot = None
        try:
            bbox = (x - 5, y - 5, x + 5, y + 5)
            screenshot = ImageGrab.grab(bbox=bbox)
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)

            if target_color == 'blue':
                lower = np.array([100, 120, 180])
                upper = np.array([140, 255, 255])
            else:  # red
                lower1 = np.array([0, 150, 120])
                upper1 = np.array([10, 255, 255])
                lower2 = np.array([170, 150, 120])
                upper2 = np.array([180, 255, 255])

                mask1 = cv2.inRange(img, lower1, upper1)
                mask2 = cv2.inRange(img, lower2, upper2)
                mask = cv2.bitwise_or(mask1, mask2)
                return np.any(mask)

            mask = cv2.inRange(img, lower, upper)
            result = np.any(mask)
            logging.info(f"Color check for {target_color}: {'Found' if result else 'Not found'}")
            return result
            
        except Exception as e:
            logging.error(f"Error checking color: {e}")
            return False
        finally:
            # CRITICAL: Always close the PIL image
            if screenshot:
                screenshot.close()
                del screenshot

    def force_player_colors(self) -> bool:
        """Force players to Red and Blue colors in the bottom right UI."""
        logging.info("Forcing player colors...")
        
        ui_region = {
            'x': 1180,
            'y': 980,
            'width': 320,
            'height': 250
        }
        
        name_positions = {
            'top': {'x': 66, 'y': 22},
            'bottom': {'x': 66, 'y': 64}
        }
        
        try:
            # First make top name blue
            attempts = 0
            while attempts < self.force_color_max_attempts:
                logging.info(f"Setting top name to blue (attempt {attempts + 1})")
                
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

    def handle_game_end(self) -> bool:
        """Enhanced game end handling with restart management"""
        try:
            logging.info("Starting game end cleanup sequence")
            
            # Record successful game completion
            self.restart_manager.record_game_completion()
            
            # Get memory status
            memory_status = self.memory_monitor.check_and_log()
            
            # Check if we should restart
            restart_reason = self.restart_manager.should_restart(memory_status)
            if restart_reason:
                logging.info(f" Restart needed due to: {restart_reason}")
                
                # Perform OBS cleanup first
                self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME'])
                try:
                    self.obs_manager.clear_match_text()
                except Exception as e:
                    logging.warning(f"Non-critical error clearing match text: {e}")
                
                # Perform restart
                if self.restart_manager.perform_restart(restart_reason):
                    return True
                else:
                    # Restart failed, check if we need nuclear option
                    if self.restart_manager.should_nuclear_restart():
                        logging.critical("🚨 Performing nuclear restart...")
                        self.restart_helper.restart_python_script()
                        return False  # Won't reach here
            
            # Normal game end cleanup (existing code)
            self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME'])
            time.sleep(1)

            try:
                self.obs_manager.clear_match_text()
            except Exception as e:
                logging.warning(f"Non-critical error clearing match text: {e}")

            # AoE2 window cleanup
            aoe2_window = "Age of Empires II: Definitive Edition"
            if not ensure_window_focus(aoe2_window):
                logging.error("Failed to focus AoE2 window")
                self.restart_manager.record_failure()
                return False
                
            # Send menu navigation commands
            time.sleep(1)
            logging.info("Sending menu navigation commands")
            
            pyautogui.press('tab')
            time.sleep(1.0)
            pyautogui.press('enter')
            time.sleep(1.5)
            
            pyautogui.press('esc')
            time.sleep(1.0)
            pyautogui.press('enter')
            time.sleep(1.5)
            
            pyautogui.press('esc')
            time.sleep(1.0)
            pyautogui.press('esc')
            time.sleep(2.0)
            
            logging.info("Game end cleanup completed successfully")
            return True
                    
        except Exception as e:
            logging.error(f"Error during game end cleanup: {e}")
            self.restart_manager.record_failure()
            return False

    def run_spectator(self) -> bool:
        """Initialize and run the spectator core."""
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
                'PLAYER_HSV_RANGES': self.config.PLAYER_HSV_RANGES,
                'GAME_AGES': self.config.GAME_AGES,
                'BUILDING_ICON_MIN_AREA': self.config.BUILDING_ICON_MIN_AREA,
                'BUILDING_ICON_MAX_AREA': self.config.BUILDING_ICON_MAX_AREA,
                'BUILDING_ICON_MIN_CIRCULARITY': self.config.BUILDING_ICON_MIN_CIRCULARITY,
                'MAX_PLAYERS': self.config.MAX_PLAYERS,
                'EXPECTED_PLAYERS_1V1': self.config.EXPECTED_PLAYERS_1V1,
                'STARTING_TC_COUNT': self.config.STARTING_TC_COUNT
            })()

            self.spectator_core = SpectatorCore(config_obj, betting_bridge=self.betting_bridge)
            self.current_game_start = time.time()
            
            logging.info("Starting spectator core...")
            spectator_result = self.spectator_core.run_spectator()
            self.spectator_core.cleanup_between_games()

            if spectator_result:
                logging.info("Game ended normally")
            else:
                logging.warning("Game ended unexpectedly")
                
            return spectator_result
            
        except Exception as e:
            logging.error(f"Error in spectator core: {e}")
            # Clean up even if there was an error
            if hasattr(self, 'spectator_core'):
                self.spectator_core.cleanup_between_games()
            return False


    def main_loop(self):
        """Enhanced main loop with restart management and recovery."""
        try:
            self.state_manager.transition_to(GameState.FINDING_GAME)
            
            while True:
                try:
                    # Check for nuclear restart condition first
                    if self.restart_manager.should_nuclear_restart():
                        logging.critical("🚨 Nuclear restart condition met")
                        self.restart_helper.restart_python_script()
                        return  # Won't reach here
                    
                    # Regular health check
                    if not self.health_checker.perform_full_health_check(self.obs_manager):
                        logging.error("Health check failed")
                        self.restart_manager.record_failure()
                        # Don't immediately fail, try to continue

                    # Memory monitoring with nuclear option
                    memory_status = self.memory_monitor.check_and_log()
                    if memory_status == "NUCLEAR":
                        logging.critical("🚨 NUCLEAR MEMORY LEVEL - RESTARTING SCRIPT!")
                        self.restart_helper.restart_python_script()
                    elif memory_status == "CRITICAL":
                        logging.error("Consider restarting soon!")
                        # The restart manager will catch this in should_restart()

                    # State timeout check with recovery
                    if recovery_state := self.state_manager.handle_timeout():
                        if recovery_state == GameState.ERROR:
                            if not self.recovery_manager.attempt_recovery(self.state_manager.current_state):
                                self.restart_manager.record_failure()
                                time.sleep(5)
                                continue
                        else:
                            self.state_manager.transition_to(recovery_state)
                            continue

                    current_state = self.state_manager.current_state

                    # State-specific handling
                    if current_state == GameState.FINDING_GAME:
                        logging.info("Finding new game...")
                        if not self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME']):
                            self.restart_manager.record_failure()
                            time.sleep(5)
                            continue

                        with sync_playwright() as playwright:
                            spectated, match_info = find_and_spectate_game(
                                playwright, 
                                {'AOE2_COMPANION_URL': self.companion_url}
                            )
                            
                            if not spectated:
                                logging.warning("No game found to spectate. Waiting before retry...")
                                time.sleep(20)
                                continue
                            
                            if not self.obs_manager.update_match_text(match_info):
                                logging.error("Failed to update match text")
                                # Non-critical, continue

                            self.state_manager.transition_to(GameState.GAME_FOUND)

                    elif current_state == GameState.GAME_FOUND:
                        if self.wait_for_game_load():
                            self.state_manager.transition_to(GameState.LOADING_GAME)

                    elif current_state == GameState.LOADING_GAME:
                        capture_age_attempts = 0
                        while capture_age_attempts < 5:
                            if switch_to_window(self.game_window_title):
                                logging.info("Successfully switched to CaptureAge window")
                                self.state_manager.transition_to(GameState.SETTING_UP_VIEW)
                                break
                            capture_age_attempts += 1
                            logging.warning(f"Failed to switch to CaptureAge window, attempt {capture_age_attempts}/5")
                            time.sleep(5)
                        
                        if capture_age_attempts >= 5:
                            logging.error("Failed to switch to CaptureAge after 5 attempts")
                            self.restart_manager.record_failure()
                            self.state_manager.transition_to(GameState.ERROR)

                    elif current_state == GameState.SETTING_UP_VIEW:
                        if self.force_player_colors() and self.setup_game_view():
                            if self.safe_scene_switch(self.obs_manager.scenes['GAME']):
                                if hasattr(self, 'betting_bridge') and self.betting_bridge:
                                    self.betting_bridge.on_game_start()
                                self.state_manager.transition_to(GameState.SPECTATING)
                        else:
                            logging.error("Failed to setup game view")
                            self.restart_manager.record_failure()
                            self.state_manager.transition_to(GameState.ERROR)

                    elif current_state == GameState.SPECTATING:
                        spectator_result = self.run_spectator()
                        if spectator_result:
                            self.state_manager.transition_to(GameState.GAME_ENDED)
                        else:
                            logging.warning("Spectator ended unexpectedly")
                            self.restart_manager.record_failure()
                            self.state_manager.transition_to(GameState.GAME_ENDED)

                    elif current_state == GameState.GAME_ENDED:
                        if self.handle_game_end():
                            logging.info(f"Waiting {self.between_games_delay}s before next game...")
                            time.sleep(self.between_games_delay)
                            self.state_manager.transition_to(GameState.FINDING_GAME)
                        else:
                            logging.error("Failed to handle game end properly")
                            self.restart_manager.record_failure()
                            # Try to continue anyway
                            time.sleep(self.between_games_delay)
                            self.state_manager.transition_to(GameState.FINDING_GAME)

                    elif current_state == GameState.ERROR:
                        logging.info("In error state, attempting recovery...")
                        if self.recovery_manager.attempt_recovery(current_state):
                            self.state_manager.transition_to(GameState.FINDING_GAME)
                            logging.info("Recovery successful, resuming operation")
                        else:
                            logging.error("Recovery failed, will retry")
                            self.restart_manager.record_failure()
                            time.sleep(10)  # Longer wait in error state

                    time.sleep(0.1)  # Prevent CPU thrashing
                    
                except Exception as e:
                    logging.error(f"Error in main loop iteration: {e}")
                    import traceback
                    logging.error(traceback.format_exc())
                    
                    self.restart_manager.record_failure()
                    
                    # If we have too many failures, transition to error state
                    if self.restart_manager.consecutive_failures >= 2:
                        logging.warning("Too many consecutive failures, entering error state")
                        self.state_manager.transition_to(GameState.ERROR)
                    else:
                        time.sleep(5)  # Brief pause before retry
                        
        except KeyboardInterrupt:
            logging.info("Main loop stopped by user")
            self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME'])
            try:
                self.obs_manager.clear_match_text()
            except:
                pass
        except Exception as e:
            logging.error(f"Critical error in main loop: {e}")
            import traceback
            logging.error(traceback.format_exc())
            
            # Attempt cleanup
            try:
                self.safe_scene_switch(self.obs_manager.scenes['FINDING_GAME'])
                self.obs_manager.clear_match_text()
            except:
                pass
            
            # This is a critical failure
            self.restart_manager.record_failure()
            
            # If we're in a really bad state, try nuclear restart
            if self.restart_manager.should_nuclear_restart():
                logging.critical("Critical error triggering nuclear restart")
                self.restart_helper.restart_python_script()



class RestartManager:
    def __init__(self, restart_helper):
        self.restart_helper = restart_helper
        self.games_since_restart = 0
        self.start_time = time.time()
        self.last_memory_check = time.time()
        
        # Restart triggers
        self.max_games = 30  # Restart every 5 games
        self.max_runtime_hours = 12  # Force restart after 8 hours
        self.memory_threshold_gb = 2.0  # Restart if memory > 3GB
        self.consecutive_failures = 0
        self.max_failures = 3  # Nuclear restart after 3 consecutive failures
        
    def should_restart(self, memory_status="OK"):
        """Check if we should restart CaptureAge/processes"""
        current_time = time.time()
        runtime_hours = (current_time - self.start_time) / 3600
        
        # Game count trigger
        if self.games_since_restart >= self.max_games:
            logging.info(f" Restart trigger: Game count ({self.games_since_restart}/{self.max_games})")
            return "games"
        
        # Runtime trigger
        if runtime_hours >= self.max_runtime_hours:
            logging.info(f" Restart trigger: Runtime ({runtime_hours:.1f}/{self.max_runtime_hours} hours)")
            return "runtime"
        
        # Memory trigger
        if memory_status == "CRITICAL":
            logging.info(" Restart trigger: Critical memory usage")
            return "memory"
        
        return None
    
    def should_nuclear_restart(self):
        """Check if we need to restart the entire Python script"""
        if self.consecutive_failures >= self.max_failures:
            logging.critical(f" Nuclear restart trigger: {self.consecutive_failures} consecutive failures")
            return True
        return False
    
    def perform_restart(self, reason="scheduled"):
        """Perform a controlled restart"""
        try:
            logging.info(f" Performing restart (reason: {reason})...")
            
            if self.restart_helper.restart_everything():
                self.games_since_restart = 0
                self.consecutive_failures = 0  # Reset failure count on successful restart
                logging.info(" Restart successful")
                time.sleep(15)  # Wait for processes to stabilize
                return True
            else:
                self.consecutive_failures += 1
                logging.error(f"Restart failed (failures: {self.consecutive_failures})")
                return False
                
        except Exception as e:
            self.consecutive_failures += 1
            logging.error(f"Restart error: {e} (failures: {self.consecutive_failures})")
            return False
    
    def record_game_completion(self):
        """Call this after each game completes successfully"""
        self.games_since_restart += 1
        self.consecutive_failures = 0  # Reset on successful game
        logging.info(f"Games since restart: {self.games_since_restart}/{self.max_games}")
    
    def record_failure(self):
        """Call this when something fails"""
        self.consecutive_failures += 1
        logging.warning(f" : {self.consecutive_failures}/{self.max_failures}")
    
    def get_status(self):
        """Get current restart manager status"""
        current_time = time.time()
        runtime_hours = (current_time - self.start_time) / 3600
        
        return {
            'games_completed': self.games_since_restart,
            'runtime_hours': runtime_hours,
            'consecutive_failures': self.consecutive_failures,
            'next_restart_games': self.max_games - self.games_since_restart,
            'next_restart_hours': self.max_runtime_hours - runtime_hours
        }




def main():
    """Entry point."""
    import config

    spec_config = type('Config', (), {})()
    
    for attr in dir(config):
        if not attr.startswith('_'):
            setattr(spec_config, attr, getattr(config, attr))
    
    flow = MainFlow(spec_config)
    flow.main_loop()

if __name__ == "__main__":
    main()