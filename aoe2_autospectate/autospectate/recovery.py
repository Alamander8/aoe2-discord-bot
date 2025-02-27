import time
import logging
from state_management import GameState
from game_manager import AoE2Manager

class RecoveryManager:
    def __init__(self, main_flow):
        self.main_flow = main_flow
        self.max_recovery_attempts = 3
        self.recovery_cooldown = 60  # seconds
        self.last_recovery_attempt = 0
        self.recovery_counts = {}
        self.game_manager = AoE2Manager()
        
    def attempt_recovery(self, error_state: GameState) -> bool:
        """Enhanced recovery with AoE2:DE process management"""
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
            # Reset OBS scene first
            if not self.main_flow.safe_scene_switch(self.main_flow.obs_manager.scenes['FINDING_GAME']):
                logging.error("Failed to reset OBS scene during recovery")
                
            # Restart AoE2:DE
            if not self.game_manager.restart_game():
                logging.error("Failed to restart AoE2:DE")
                return False
                
            # Wait for game to be ready
            if not self.game_manager.wait_for_game_ready():
                logging.error("Game failed to reach ready state")
                return False
                
            # Reset state
            self.main_flow.state_manager.transition_to(GameState.FINDING_GAME)
            
            logging.info(f"Successfully recovered from {error_state}")
            return True
            
        except Exception as e:
            logging.error(f"Error during recovery attempt: {e}")
            return False
            
    def reset_recovery_count(self, state: GameState):
        """Reset recovery count for a specific state"""
        self.recovery_counts[state] = 0