import time
import random
import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import logging

class SpectatorCore:
    def __init__(self, config):
        """
        Initialize the spectator core with configuration.
        """
        # Store the config object and initialize all needed attributes
        self.config = config
        
        # Screen dimensions and coordinates
        self.minimap_x = config.MINIMAP_X
        self.minimap_y = config.MINIMAP_Y
        self.minimap_width = config.MINIMAP_WIDTH
        self.minimap_height = config.MINIMAP_HEIGHT
        
        self.game_area_x = config.GAME_AREA_X
        self.game_area_y = config.GAME_AREA_Y
        self.game_area_width = config.GAME_AREA_WIDTH
        self.game_area_height = config.GAME_AREA_HEIGHT
        
        # Color configuration
        self.player_colors_config = config.PLAYER_HSV_RANGES
        
        # Game state tracking
        self.game_time = 0
        self.start_time = time.time()
        self.vision_set = False
        self.last_action_time = 0
        self.last_stats_toggle_time = 0
        self.current_age = 'Dark Age'
        self.last_fight_time = 0
        self.change_history = []
        self.conflict_players = set()
        self.spectate_queue = []
        
        # Player tracking
        self.player_focus_time = {}  # Track time spent on each player
        self.last_player_switch = time.time()
        self.current_player = None
        self.min_focus_time = 10  # Minimum seconds to stay on a player
        self.max_focus_time = 30  # Maximum seconds to stay on a player
        
        # Metrics
        self.player_switches = 0
        self.fights_detected = 0
        self.total_activity = 0

        # Building tracking
        self.player_buildings = {}  # Track building locations by player

    def capture_minimap(self, debug=False):
        """
        Capture the minimap area of the screen with optional debug visualization.
        """
        try:
            # Calculate coordinates with padding
            x1 = self.minimap_x - self.config.MINIMAP_PADDING
            y1 = self.minimap_y - self.config.MINIMAP_PADDING
            x2 = self.minimap_x + self.minimap_width + self.config.MINIMAP_PADDING
            y2 = self.minimap_y + self.minimap_height + self.config.MINIMAP_PADDING
            
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            if debug:
                # Draw a rectangle showing the capture area
                debug_frame = frame.copy()
                cv2.rectangle(debug_frame, 
                            (self.config.MINIMAP_PADDING, self.config.MINIMAP_PADDING),
                            (self.minimap_width + self.config.MINIMAP_PADDING, 
                             self.minimap_height + self.config.MINIMAP_PADDING),
                            (0, 255, 0), 2)
                cv2.imwrite('debug_minimap_area.png', debug_frame)
                
            return frame
            
        except Exception as e:
            logging.error(f"Error capturing minimap: {e}")
            return None

    def capture_game_area(self):
        """Capture the main game area of the screen."""
        try:
            screenshot = ImageGrab.grab(bbox=(
                self.game_area_x,
                self.game_area_y,
                self.game_area_x + self.game_area_width,
                self.game_area_y + self.game_area_height
            ))
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception as e:
            logging.error(f"Error capturing game area: {e}")
            return None

    def detect_building_icons(self, minimap_image, debug=False):
        """
        Detect TC and Castle icons on the minimap.
        Returns dict of players with their building positions and types.
        """
        active_players = {}
        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)
        debug_image = minimap_image.copy() if debug else None
        
        for player, ranges in self.player_colors_config.items():
            lower = np.array(ranges['icon']['lower'], dtype=np.uint8)
            upper = np.array(ranges['icon']['upper'], dtype=np.uint8)
            mask = cv2.inRange(hsv_image, lower, upper)
            
            # Find contours of potential building icons
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            buildings = []
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if self.config.BUILDING_ICON_MIN_AREA <= area <= self.config.BUILDING_ICON_MAX_AREA:
                    # Calculate circularity
                    perimeter = cv2.arcLength(contour, True)
                    circularity = 4 * np.pi * area / (perimeter * perimeter)
                    
                    if circularity >= self.config.BUILDING_ICON_MIN_CIRCULARITY:
                        M = cv2.moments(contour)
                        if M["m00"] != 0:
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"])
                            buildings.append({
                                'position': (cx, cy),
                                'area': area,
                                'type': 'building'
                            })
                            
                            if debug:
                                cv2.circle(debug_image, (cx, cy), 3, (0, 255, 0), -1)
                                cv2.putText(debug_image, f"{player}", (cx-10, cy-10),
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)
            
            if buildings:
                active_players[player] = buildings
                self.player_buildings[player] = buildings  # Update tracked buildings
        
        if debug and debug_image is not None:
            cv2.imwrite('debug_building_icons.png', debug_image)
            
        return active_players
    def detect_activity(self, prev_image, curr_image):
        """
        Detect activity between two consecutive frames.
        Returns contours and change magnitude.
        """
        if prev_image is None or curr_image is None:
            return [], 0
            
        diff = cv2.absdiff(prev_image, curr_image)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        change_magnitude = np.sum(thresh)
        return contours, change_magnitude

    def detect_conflict_near_tc(self, minimap_image, active_players, debug=False):
        """
        Detect conflicts near TC locations, prioritizing enemy units near opponent's TCs.
        Returns list of conflicts with their positions and priorities.
        """
        conflicts = []
        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)
        debug_image = minimap_image.copy() if debug else None
        
        # First, get each player's unit positions
        player_units = {}
        for player, ranges in self.player_colors_config.items():
            if player in active_players:
                lower = np.array(ranges['normal']['lower'], dtype=np.uint8)
                upper = np.array(ranges['normal']['upper'], dtype=np.uint8)
                mask = cv2.inRange(hsv_image, lower, upper)
                player_units[player] = mask

        # Check for units near opponent TCs
        players = list(active_players.keys())
        for i in range(len(players)):
            for j in range(i+1, len(players)):
                player1, player2 = players[i], players[j]
                
                # Check player1's units near player2's TCs
                for tc in active_players[player2]:
                    tc_pos = tc['position']
                    # Create a circular mask around TC
                    tc_area_mask = np.zeros(hsv_image.shape[:2], dtype=np.uint8)
                    cv2.circle(tc_area_mask, tc_pos, 30, 255, -1)  # 30 pixel radius around TC
                    
                    # Check for player1's units in this area
                    units_near_tc = cv2.bitwise_and(player_units[player1], tc_area_mask)
                    if cv2.countNonZero(units_near_tc) > 50:  # Threshold for significant unit presence
                        conflicts.append({
                            'position': tc_pos,
                            'players': (player1, player2),
                            'priority': 'high',  # High priority for TC conflicts
                            'type': 'tc_conflict'
                        })
                        if debug:
                            cv2.circle(debug_image, tc_pos, 30, (0, 0, 255), 2)
                
                # Do the same for player2's units near player1's TCs
                for tc in active_players[player1]:
                    tc_pos = tc['position']
                    tc_area_mask = np.zeros(hsv_image.shape[:2], dtype=np.uint8)
                    cv2.circle(tc_area_mask, tc_pos, 30, 255, -1)
                    
                    units_near_tc = cv2.bitwise_and(player_units[player2], tc_area_mask)
                    if cv2.countNonZero(units_near_tc) > 50:
                        conflicts.append({
                            'position': tc_pos,
                            'players': (player2, player1),
                            'priority': 'high',
                            'type': 'tc_conflict'
                        })
                        if debug:
                            cv2.circle(debug_image, tc_pos, 30, (0, 0, 255), 2)

        if debug and len(conflicts) > 0:
            cv2.imwrite('debug_conflicts.png', debug_image)
        
        return conflicts

    def validate_game_players(self, active_players):
        """
        Validate detected players for a 1v1 game.
        """
        if len(active_players) != self.config.EXPECTED_PLAYERS_1V1:
            logging.warning(f"Unexpected player count: {len(active_players)}. Expected {self.config.EXPECTED_PLAYERS_1V1}")
            return {}

        validated_players = {}
        for player, buildings in active_players.items():
            if len(buildings) >= self.config.STARTING_TC_COUNT:
                validated_players[player] = buildings
            else:
                logging.debug(f"Player {player} has no detected buildings")

        return validated_players

    def click_and_drag_follow(self, start_x, start_y, end_x, end_y, duration=0.5):
        """Perform click, drag, and follow action."""
        try:
            pyautogui.moveTo(start_x, start_y, duration=0.2)
            pyautogui.dragTo(end_x, end_y, duration=duration, button='left')
            pyautogui.press('f')
            logging.info("Following with click-and-drag")
        except pyautogui.FailSafeException:
            logging.error("Fail-safe triggered during click and drag")

    def click_minimap(self, x, y):
        """Click a position on the minimap."""
        try:
            click_x = self.minimap_x + x
            click_y = self.minimap_y + y
            logging.info(f"Clicking minimap at ({click_x}, {click_y})")
            pyautogui.click(click_x, click_y)
        except pyautogui.FailSafeException:
            logging.error("Fail-safe triggered during minimap click")

    def run_spectator_iteration(self):
        """Run a single iteration of the spectator logic."""
        try:
            curr_minimap = self.capture_minimap()
            if curr_minimap is None:
                return

            # Detect active players and their buildings
            active_players = self.detect_building_icons(curr_minimap)
            validated_players = self.validate_game_players(active_players)
            
            if validated_players:
                logging.info(f"Active players: {list(validated_players.keys())}")
                
                # Detect conflicts near TCs
                conflicts = self.detect_conflict_near_tc(curr_minimap, validated_players)
                
                if conflicts:
                    # Sort by priority (TC conflicts first)
                    conflicts.sort(key=lambda x: 0 if x['priority'] == 'high' else 1)
                    target_conflict = conflicts[0]
                    
                    # Focus camera on conflict
                    self.click_minimap(*target_conflict['position'])
                    
                    # Center screen drag
                    center_x = self.game_area_width // 2
                    center_y = self.game_area_height // 2
                    drag_distance = 100

                    self.click_and_drag_follow(
                        center_x - drag_distance,
                        center_y - drag_distance,
                        center_x + drag_distance,
                        center_y + drag_distance,
                        duration=1.5
                    )
                    
                    logging.info(f"Focusing on {target_conflict['type']} between {target_conflict['players']}")
                else:
                    logging.info("No significant conflicts detected")
            
        except Exception as e:
            logging.error(f"Error in spectator iteration: {e}")

    def run_spectator(self):
        """Main spectator loop."""
        logging.info("Starting spectator")
        while True:
            try:
                current_time = time.time()
                self.game_time = int(current_time - self.start_time)
                
                # Run a single iteration
                self.run_spectator_iteration()
                
                time.sleep(0.5)  # Short sleep to prevent excessive CPU usage

            except Exception as e:
                logging.error(f"Error in spectator loop: {e}")
                time.sleep(1)  # Wait before retrying