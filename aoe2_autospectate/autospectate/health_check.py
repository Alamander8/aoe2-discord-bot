# autospectate/health_check.py

import time
import logging
from windows_management import switch_to_window

class HealthCheck:
    def __init__(self):
        self.last_health_check = time.time()
        self.health_check_interval = 30  # seconds
        self.window_check_attempts = 3
        self.process_check_attempts = 2

    def check_game_windows(self) -> bool:
        """Verify required game windows are present and accessible."""
        windows_to_check = ["CaptureAge", "Age of Empires II: Definitive Edition"]
        
        for window in windows_to_check:
            attempts = 0
            while attempts < self.window_check_attempts:
                if switch_to_window(window):
                    break
                attempts += 1
                time.sleep(1)
            
            if attempts >= self.window_check_attempts:
                logging.error(f"Failed to find/access window: {window}")
                return False
        
        return True

    def verify_obs_connection(self, obs_manager) -> bool:
        """Verify OBS connection is active and working."""
        max_retries = 2
        retry_delay = 1.0  # seconds
        
        for attempt in range(max_retries):
            try:
                if not obs_manager.ws or not obs_manager.ws.ws:
                    if attempt == 0:  # Only log on first attempt
                        logging.error("OBS connection lost")
                    if not obs_manager.connect():
                        time.sleep(retry_delay)
                        continue
                return True  # If we have a connection, that's good enough
                    
            except Exception as e:
                logging.error(f"OBS connection check failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    
        return False

    def perform_full_health_check(self, obs_manager) -> bool:
        """Perform comprehensive system health check."""
        current_time = time.time()
        if current_time - self.last_health_check < self.health_check_interval:
            return True

        self.last_health_check = current_time
        
        # Check windows
        if not self.check_game_windows():
            return False
            
        # Check OBS
        if not self.verify_obs_connection(obs_manager):
            return False
            
        return True