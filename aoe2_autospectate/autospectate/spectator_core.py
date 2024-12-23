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
        
        Args:
            config: Configuration object containing necessary settings
        """
        # Screen dimensions and coordinates
        self.minimap_x = config.MINIMAP_X
        self.minimap_y = config.MINIMAP_Y
        self.minimap_width = config.MINIMAP_WIDTH
        self.minimap_height = config.MINIMAP_HEIGHT
        
        self.game_area_x = config.GAME_AREA_X
        self.game_area_y = config.GAME_AREA_Y
        self.game_area_width = config.GAME_AREA_WIDTH
        self.game_area_height = config.GAME_AREA_HEIGHT
        
        # Game state
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
        self.player_colors = {}
        
        # Load settings from config
        self.player_colors_config = config.PLAYER_HSV_RANGES
        self.game_ages = config.GAME_AGES
        
        # Load building templates
        self.building_templates = {}
        if hasattr(config, 'BUILDING_TEMPLATES'):
            for building, path in config.BUILDING_TEMPLATES.items():
                template = cv2.imread(path, cv2.IMREAD_COLOR)
                if template is not None:
                    self.building_templates[building] = template
                else:
                    logging.error(f"Failed to load template for {building}")

    def capture_minimap(self):
        """Capture the minimap area of the screen."""
        try:
            screenshot = ImageGrab.grab(bbox=(
                self.minimap_x,
                self.minimap_y,
                self.minimap_x + self.minimap_width,
                self.minimap_y + self.minimap_height
            ))
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
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

    def set_permanent_vision(self):
        """Set permanent vision using hotkeys."""
        pyautogui.hotkey('alt', 'f')
        time.sleep(0.5)
        pyautogui.hotkey('alt', 'f')
        self.vision_set = True
        logging.info("Set permanent vision")

    def toggle_stats(self):
        """Toggle game statistics display."""
        pyautogui.hotkey('alt', 'c')
        logging.info("Toggled stats")

    def detect_player_colors(self, image, debug=False):
        """
        Detect player colors in the given image with improved accuracy.
        Returns dict of detected colors with their positions and confidence.
        """
        detected_colors = {}
        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        debug_image = image.copy() if debug else None
        
        for color_name, hsv_range in self.player_colors_config.items():
            lower = np.array(hsv_range['lower'], dtype=np.uint8)
            upper = np.array(hsv_range['upper'], dtype=np.uint8)
            mask = cv2.inRange(hsv_image, lower, upper)
            
            # Find contours in the mask
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 25 and area < 500:  # Player dots should be within this size range
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        
                        # Calculate roundness to detect player dots
                        perimeter = cv2.arcLength(contour, True)
                        roundness = 4 * np.pi * area / (perimeter * perimeter)
                        
                        if roundness > 0.7:  # Player dots are usually round
                            confidence = (area / 500) * roundness * 100  # Confidence score
                            detected_colors[color_name] = {
                                'position': (cx, cy),
                                'confidence': confidence,
                                'area': area
                            }
                            
                            if debug:
                                cv2.drawContours(debug_image, [contour], -1, (0, 255, 0), 2)
                                cv2.circle(debug_image, (cx, cy), 3, (0, 0, 255), -1)
                                cv2.putText(debug_image, f"{color_name}", (cx-20, cy-10),
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return detected_colors

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

    def is_big_fight(self, curr_image, contours):
        """
        Determine if detected activity represents a significant fight.
        Returns bool indicating fight status and set of involved players.
        """
        # Define area thresholds based on current age
        age_thresholds = {
            'Dark Age': 50,
            'Feudal Age': 100,
            'Castle Age': 200,
            'Imperial Age': 300
        }
        area_threshold = age_thresholds.get(self.current_age, 100)

        if len(contours) < 2:
            return False, set()

        large_contours = [c for c in contours if cv2.contourArea(c) > area_threshold]
        if len(large_contours) < 2:
            return False, set()

        colors_present = set()
        for contour in large_contours:
            mask = np.zeros(curr_image.shape[:2], np.uint8)
            cv2.drawContours(mask, [contour], 0, 255, -1)
            hsv_image = cv2.cvtColor(curr_image, cv2.COLOR_BGR2HSV)
            
            for color_name, hsv_range in self.player_colors_config.items():
                lower = np.array(hsv_range['lower'], dtype=np.uint8)
                upper = np.array(hsv_range['upper'], dtype=np.uint8)
                color_mask = cv2.inRange(hsv_image, lower, upper)
                color_mask = cv2.bitwise_and(color_mask, mask)
                if cv2.countNonZero(color_mask) >= 5:
                    colors_present.add(color_name)
                    if len(colors_present) >= 2:
                        return True, colors_present
                        
        return False, set()

    def find_most_active_area(self, contours):
        """Find the center of the largest activity area."""
        if not contours:
            return None
            
        largest_contour = max(contours, key=cv2.contourArea)
        M = cv2.moments(largest_contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            return (cx, cy)
        return None

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
            pyautogui.click(self.minimap_x + x, self.minimap_y + y)
            logging.info(f"Clicked minimap at ({x}, {y})")
        except pyautogui.FailSafeException:
            logging.error("Fail-safe triggered during minimap click")

    def update_game_age(self):
        """Update the current game age based on game time."""
        for age, threshold in reversed(self.game_ages):
            if self.game_time >= threshold:
                if self.current_age != age:
                    self.current_age = age
                    logging.info(f"Game Age: {age}")
                break

    def find_player_position(self, minimap_image, player_name):
        """Find a player's position on the minimap."""
        hsv_range = self.player_colors_config.get(player_name)
        if not hsv_range:
            logging.error(f"No color defined for player: {player_name}")
            return None

        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)
        lower = np.array(hsv_range['lower'], dtype=np.uint8)
        upper = np.array(hsv_range['upper'], dtype=np.uint8)
        mask = cv2.inRange(hsv_image, lower, upper)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            M = cv2.moments(largest_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                return (cx, cy)
        return None

    def run_spectator(self):
        """Main spectator loop."""
        prev_minimap = self.capture_minimap()
        prev_game_area = self.capture_game_area()

        while True:
            try:
                current_time = time.time()
                self.game_time = int(current_time - self.start_time)

                # Update game age
                self.update_game_age()

                # Set permanent vision at 10 minutes
                if self.game_time >= 600 and not self.vision_set:
                    self.set_permanent_vision()

                # Toggle stats every 10 seconds
                if current_time - self.last_stats_toggle_time >= 10:
                    self.toggle_stats()
                    self.last_stats_toggle_time = current_time

                # Capture current frames
                curr_minimap = self.capture_minimap()
                curr_game_area = self.capture_game_area()

                # Detect activity
                activity_contours_minimap, change_magnitude_minimap = self.detect_activity(
                    prev_minimap, curr_minimap)
                activity_contours_game_area, change_magnitude_game_area = self.detect_activity(
                    prev_game_area, curr_game_area)

                # Track changes for detection
                self.change_history.append(change_magnitude_game_area)
                if len(self.change_history) > 10:
                    self.change_history.pop(0)
                average_change = sum(self.change_history) / len(self.change_history)
                big_change_threshold = 1.5 * average_change if average_change > 0 else 1000

                # Handle fights and significant changes
                is_fight, players_involved = self.is_big_fight(curr_game_area, activity_contours_game_area)
                is_big_change = change_magnitude_game_area > big_change_threshold

                if (is_fight or is_big_change) and players_involved:
                    self.conflict_players.update(players_involved)

                    if current_time - self.last_fight_time >= 15 and self.conflict_players:
                        if not self.spectate_queue:
                            self.spectate_queue = list(self.conflict_players)
                            random.shuffle(self.spectate_queue)

                        player_to_follow = self.spectate_queue.pop(0)
                        self.conflict_players.discard(player_to_follow)

                        player_position = self.find_player_position(curr_minimap, player_to_follow)
                        if player_position:
                            time.sleep(1)
                            self.click_minimap(*player_position)

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

                            self.last_fight_time = current_time
                            time.sleep(10)

                elif current_time - self.last_action_time >= 2:
                    active_point = self.find_most_active_area(activity_contours_minimap)
                    if active_point:
                        time.sleep(1)
                        self.click_minimap(*active_point)
                    self.last_action_time = current_time

                prev_minimap = curr_minimap
                prev_game_area = curr_game_area
                time.sleep(0.5)

            except Exception as e:
                logging.error(f"Error in spectator loop: {e}")
                time.sleep(1)