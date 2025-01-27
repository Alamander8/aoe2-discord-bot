# autospectate/recovery.py

import time
import logging
from state_management import GameState

class RecoveryManager:
    def __init__(self, main_flow):
        self.main_flow = main_flow
        self.max_recovery_attempts = 3
        self.recovery_cooldown = 60  # seconds
        self.last_recovery_attempt = 0
        self.recovery_counts = {}

    def attempt_recovery(self, error_state: GameState) -> bool:
        """Attempt to recover from an error state."""
        current_time = time.time()
        
        # Check cooldown
        if current_time - self.last_recovery_attempt < self.recovery_cooldown:
            logging.info("Recovery attempt too soon, waiting for cooldown")
            return False
            
        # Check max attempts
        if self.recovery_counts.get(error_state, 0) >= self.max_recovery_attempts:
            logging.error(f"Max recovery attempts exceeded for {error_state}")
            return False
            
        self.last_recovery_attempt = current_time
        self.recovery_counts[error_state] = self.recovery_counts.get(error_state, 0) + 1
        
        try:
            # Reset OBS scene
            if not self.main_flow.safe_scene_switch(self.main_flow.obs_manager.scenes['FINDING_GAME']):
                logging.error("Failed to reset OBS scene during recovery")
                return False
                
            # Clean up game windows
            if not self.main_flow.cleanup_game_window():
                logging.error("Failed to clean up game windows during recovery")
                return False
                
            # Reset state
            self.main_flow.state_manager.transition_to(GameState.FINDING_GAME)
            
            logging.info(f"Successfully recovered from {error_state}")
            return True
            
        except Exception as e:
            logging.error(f"Error during recovery attempt: {e}")
            return False

    def reset_recovery_count(self, state: GameState):
        """Reset recovery count for a specific state."""
        self.recovery_counts[state] = 0