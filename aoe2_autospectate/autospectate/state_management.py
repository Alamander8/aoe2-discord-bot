# autospectate/state_management.py

from enum import Enum, auto
from typing import Optional, Dict
import time
import logging

class GameState(Enum):
    INITIALIZING = auto()
    FINDING_GAME = auto()
    GAME_FOUND = auto()
    LOADING_GAME = auto()
    SETTING_UP_VIEW = auto()
    SPECTATING = auto()
    GAME_ENDED = auto()
    ERROR = auto()

class StateManager:
    def __init__(self):
        self.current_state: GameState = GameState.INITIALIZING
        self.last_state_change: float = time.time()
        self.state_timeouts: Dict[GameState, float] = {
            GameState.FINDING_GAME: 300,    # 5 minutes
            GameState.LOADING_GAME: 120,    # 2 minutes
            GameState.SETTING_UP_VIEW: 60,  # 1 minute
            GameState.SPECTATING: 14400,    # 4 hours (max game length)
            GameState.GAME_ENDED: 120       # 2 minutes
        }
        self.retry_counts: Dict[GameState, int] = {}
        self.max_retries: Dict[GameState, int] = {
            GameState.FINDING_GAME: 3,
            GameState.LOADING_GAME: 2,
            GameState.SETTING_UP_VIEW: 3,
            GameState.SPECTATING: 1
        }

    def transition_to(self, new_state: GameState) -> bool:
        """
        Attempt to transition to a new state with validation.
        Returns True if transition was successful.
        """
        if not self._is_valid_transition(new_state):
            logging.error(f"Invalid state transition: {self.current_state} -> {new_state}")
            return False

        # Reset retry count for new state
        self.retry_counts[new_state] = 0
        
        # Update state
        logging.info(f"State transition: {self.current_state} -> {new_state}")
        self.current_state = new_state
        self.last_state_change = time.time()
        return True

    def _is_valid_transition(self, new_state: GameState) -> bool:
        """Define valid state transitions."""
        if new_state == self.current_state:
            return True

        valid_transitions = {
            GameState.INITIALIZING: [GameState.FINDING_GAME, GameState.ERROR],
            GameState.FINDING_GAME: [GameState.GAME_FOUND, GameState.ERROR],
            GameState.GAME_FOUND: [GameState.LOADING_GAME, GameState.ERROR],
            GameState.LOADING_GAME: [GameState.SETTING_UP_VIEW, GameState.ERROR],
            GameState.SETTING_UP_VIEW: [GameState.SPECTATING, GameState.ERROR],
            GameState.SPECTATING: [GameState.GAME_ENDED, GameState.ERROR],
            GameState.GAME_ENDED: [GameState.FINDING_GAME, GameState.ERROR],
            GameState.ERROR: [GameState.FINDING_GAME]
        }
        return new_state in valid_transitions.get(self.current_state, [])

    def handle_timeout(self) -> Optional[GameState]:
        """Check for state timeout and determine recovery action."""
        current_time = time.time()
        timeout = self.state_timeouts.get(self.current_state)
        
        if timeout and (current_time - self.last_state_change) > timeout:
            logging.warning(f"Timeout in state {self.current_state}")
            
            # Increment retry count
            self.retry_counts[self.current_state] = self.retry_counts.get(self.current_state, 0) + 1
            
            # Check if we've exceeded max retries
            if self.retry_counts[self.current_state] >= self.max_retries.get(self.current_state, 0):
                logging.error(f"Max retries exceeded for {self.current_state}")
                return GameState.ERROR
            
            # Return the recovery state based on current state
            recovery_states = {
                GameState.FINDING_GAME: GameState.FINDING_GAME,
                GameState.LOADING_GAME: GameState.FINDING_GAME,
                GameState.SETTING_UP_VIEW: GameState.LOADING_GAME,
                GameState.SPECTATING: GameState.GAME_ENDED,
                GameState.GAME_ENDED: GameState.FINDING_GAME
            }
            return recovery_states.get(self.current_state)
            
        return None

    def get_state_duration(self) -> float:
        """Get how long we've been in the current state."""
        return time.time() - self.last_state_change

    def is_in_error(self) -> bool:
        """Check if we're in an error state."""
        return self.current_state == GameState.ERROR