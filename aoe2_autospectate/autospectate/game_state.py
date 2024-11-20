# autospectate/game_state.py

import time
from autospectate.config import PLAYER_HSV_RANGES, MINIMAP_X, MINIMAP_Y, MINIMAP_WIDTH, MINIMAP_HEIGHT, GAME_AREA_WIDTH, GAME_AREA_HEIGHT

class GameState:
    def __init__(self):
        self.vision_set = False
        self.last_action_time = 0
        self.player_colors = {}
        self.current_focus = None
        self.focus_start_time = time.time()
        self.last_stats_toggle_time = 0
        self.current_age = 'Dark Age'
        self.last_followed_player = None
        self.last_fight_time = 0  # To manage cooldown for fight actions
        self.change_history = []  # To track changes for big change detection
        self.conflict_players = set()  # Players currently in conflict
        self.spectate_queue = []  # Queue to manage spectating order
        self.permanent_structures = {}  # Tracks permanent structures
        self.exploration_queue = []  # Queue for exploration actions
        self.explored_players = set()  # Players whose structures have been explored
        self.camera_decision_interval = 1  # Initial interval for camera decisions in seconds
        self.next_camera_decision_time = time.time() + self.camera_decision_interval
        self.GAME_TIME = 0  # Initialize GAME_TIME
        self.config = {
            'PLAYER_HSV_RANGES': PLAYER_HSV_RANGES,
            'MINIMAP_X': MINIMAP_X,
            'MINIMAP_Y': MINIMAP_Y,
            'MINIMAP_WIDTH': MINIMAP_WIDTH,
            'MINIMAP_HEIGHT': MINIMAP_HEIGHT,
            'GAME_AREA_WIDTH': GAME_AREA_WIDTH,
            'GAME_AREA_HEIGHT': GAME_AREA_HEIGHT
        }
        self.player_positions = {}  # To store player minimap positions

# Initialize the singleton instance
game_state = GameState()
