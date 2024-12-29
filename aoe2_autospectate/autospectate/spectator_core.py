import time
import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import logging
import random
from collections import deque
from typing import Dict, List, Tuple, Optional

class ViewingQueue:
    def __init__(self, min_revisit_time: float = 4.0, proximity_radius: int = 50):
        self.queue = deque()
        self.viewed_positions = {}
        self.min_revisit_time = min_revisit_time
        self.proximity_radius = proximity_radius

    def add_zone(self, zone: dict) -> None:
        if self._is_new_area(zone['position']):
            self.queue.append(zone)

    def _is_new_area(self, pos: Tuple[int, int]) -> bool:
        current_time = time.time()
        for viewed_pos, timestamp in list(self.viewed_positions.items()):
            if current_time - timestamp > self.min_revisit_time:
                del self.viewed_positions[viewed_pos]
                continue
            
            dx = pos[0] - viewed_pos[0]
            dy = pos[1] - viewed_pos[1]
            if (dx*dx + dy*dy) < (self.proximity_radius * self.proximity_radius):
                return False
        return True

    def get_next_view(self) -> Optional[dict]:
        while self.queue:
            zone = self.queue.popleft()
            if self._is_new_area(zone['position']):
                self.viewed_positions[zone['position']] = time.time()
                return zone
        return None

    def clear(self) -> None:
        self.queue.clear()
        self.viewed_positions.clear()



class SpectatorCore:
    def __init__(self, config):
        # Basic configuration
        self.config = config
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
        
        # Activity thresholds
        self.min_activity_area = 30
        self.large_activity_threshold = 150
        
        # Timing settings
        self.min_view_duration = 3.0
        self.max_view_duration = 6.0
        self.last_switch_time = time.time()
        

        # Previous frame storage for movement detection
        self.prev_frame = None
        self.movement_weight = 0.4  # Moderate boost for movement
        self.static_weight = 0.6    # Still significant weight for static elements

        # Initialize territory tracker and viewing queue
        self.territory_tracker = TerritoryTracker()
        self.viewing_queue = ViewingQueue(min_revisit_time=4.0, proximity_radius=50)
        
        # Active colors for 1v1
        self.active_colors = ['Blue', 'Red']
        
        # Debug flags
        self.debug_mode = False
        self.last_minimap_mask = None

    def run_spectator(self):
        """Main spectator loop."""
        logging.info("Starting spectator")
        try:
            while True:
                self.run_spectator_iteration()
                time.sleep(0.5)  # Prevent excessive CPU usage
                
        except KeyboardInterrupt:
            logging.info("Spectator stopped by user")
        except Exception as e:
            logging.error(f"Error in spectator loop: {e}")
            time.sleep(1)

    def run_spectator_iteration(self):
        """Run a single iteration of the spectator logic."""
        try:
            # Check for game over first
            if self.detect_game_over():
                logging.info("Game has ended, stopping spectator")
                return False  # Signal to stop spectating

            curr_time = time.time()
            curr_minimap = self.capture_minimap()
            if curr_minimap is None:
                return True

            # Calculate mask once for this iteration
            mask = self.calculate_minimap_mask(curr_minimap)
            if mask is None:
                logging.error("Failed to generate minimap mask")
                return True

            # Initialize view tracking if not exists
            if not hasattr(self, 'current_view_position'):
                self.current_view_position = None
                self.time_at_position = 0
                self.max_view_time = 10.0
                self.last_positions = []
                self.forced_view_until = 0

            # Update territory tracker with mask
            self.territory_tracker.update(curr_minimap, self.player_colors_config, 
                                    self.active_colors, mask)
            
            current_view_duration = random.uniform(self.min_view_duration, self.max_view_duration)

            # Check if we're in a forced temporary view
            if curr_time < self.forced_view_until:
                return True

            # Check if we've been looking at the same area too long
            if self.current_view_position:
                time_spent = curr_time - self.time_at_position
                if time_spent > self.max_view_time:
                    # Force a temporary view change
                    temp_zones = self.detect_activity_zones(curr_minimap, mask)
                    if temp_zones:
                        # Filter out recent positions
                        new_zones = [z for z in temp_zones if all(
                            self.calculate_distance(z['position'], p) > 50 
                            for p in self.last_positions
                        )]
                        if new_zones:
                            zone = random.choice(new_zones[:3])
                            self.click_minimap(*zone['position'], mask)
                            self.last_switch_time = curr_time
                            self.forced_view_until = curr_time + 2.0
                            self._update_view_position(zone['position'], curr_time)
                            logging.info(f"Forced temporary view change (area: {zone['area']:.1f})")
                            return True

            # Normal view switching logic
            if curr_time - self.last_switch_time >= current_view_duration:
                # Priority 1: Check for high-importance raids
                raids = self.territory_tracker.detect_raids(curr_minimap, self.player_colors_config, mask)
                if raids:
                    raids.sort(key=lambda x: x['importance'], reverse=True)
                    top_raid = raids[0]
                    
                    if top_raid['importance'] > 0.8:
                        if self.handle_raid(top_raid, mask):
                            self._update_view_position(top_raid['position'], curr_time)
                            return True
                    elif top_raid['importance'] > 0.6 and random.random() > 0.3:
                        if self.handle_raid(top_raid, mask):
                            self._update_view_position(top_raid['position'], curr_time)
                            return True
                    elif random.random() > 0.7:
                        if self.handle_raid(top_raid, mask):
                            self._update_view_position(top_raid['position'], curr_time)
                            return True

                # Priority 2: Normal activity with enhanced variety
                new_zones = self.detect_activity_zones(curr_minimap, mask)
                if new_zones:
                    importance_threshold = random.uniform(0.3, 0.7)
                    valid_zones = [
                        zone for zone in new_zones 
                        if zone['importance'] > importance_threshold and
                        self.is_point_in_minimap(zone['position'][0], zone['position'][1], mask)
                    ]
                    
                    if valid_zones:
                        top_zones = valid_zones[:5]
                        selected_zone = random.choice(top_zones)
                        self.viewing_queue.add_zone(selected_zone)

                next_view = self.viewing_queue.get_next_view()
                if next_view:
                    x, y = next_view['position']
                    if self.is_point_in_minimap(x, y, mask):
                        self.click_minimap(x, y, mask)
                        self.last_switch_time = curr_time
                        self._update_view_position((x, y), curr_time)
                        logging.info(f"Switched to {next_view['color']} activity "
                                f"(area: {next_view['area']:.1f}, "
                                f"importance: {next_view.get('importance', 1.0):.1f})")

            return True  # Continue spectating

        except Exception as e:
            logging.error(f"Error in spectator iteration: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return True  # Continue despite error


    def capture_minimap(self):
        """Captures the minimap area of the screen."""
        try:
            x1 = self.minimap_x
            y1 = self.minimap_y
            x2 = self.minimap_x + self.minimap_width
            y2 = self.minimap_y + self.minimap_height
            
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            if self.debug_mode:
                cv2.imwrite('debug_raw_minimap.png', frame)
                
            return frame
        except Exception as e:
            logging.error(f"Error capturing minimap: {e}")
            return None


    def detect_game_over(self):
        """Detect game end by monitoring resource numbers for changes."""
        try:
            current_time = time.time()
            
            # Calculate resource area coordinates (same as before)
            left_bbox = (
                self.game_area_x + 210,
                self.game_area_y + 1,
                self.game_area_x + 565,
                self.game_area_y + 42
            )
            
            right_bbox = (
                self.game_area_x + self.game_area_width - 565,
                self.game_area_y + 1,
                self.game_area_x + self.game_area_width - 210,
                self.game_area_y + 42
            )
            
            # Capture the resource areas
            left_resources = ImageGrab.grab(bbox=left_bbox)
            right_resources = ImageGrab.grab(bbox=right_bbox)
            
            # Convert to grayscale numpy arrays to reduce noise
            left_array = cv2.cvtColor(np.array(left_resources), cv2.COLOR_RGB2GRAY)
            right_array = cv2.cvtColor(np.array(right_resources), cv2.COLOR_RGB2GRAY)
            
            # Save debug images if debug mode is enabled
            if self.debug_mode:
                cv2.imwrite('debug_left_gray.png', left_array)
                cv2.imwrite('debug_right_gray.png', right_array)
            
            # Initialize tracking if needed
            if not hasattr(self, 'resource_history'):
                self.resource_history = []
                self.last_resource_check = current_time
                self.resource_history.append((left_array, right_array))
                return False
            
            # Only check every 4 seconds
            if current_time - self.last_resource_check < 4.0:
                return False
            
            self.last_resource_check = current_time
            
            # Add new snapshot
            self.resource_history.append((left_array, right_array))
            
            # Keep only last 5 snapshots (20 seconds worth)
            if len(self.resource_history) > 5:
                self.resource_history.pop(0)
            
            # If we have enough history, check for changes
            if len(self.resource_history) == 5:
                all_similar = True
                max_left_diff = 0
                max_right_diff = 0
                
                # Compare each consecutive pair
                for i in range(len(self.resource_history) - 1):
                    prev_left, prev_right = self.resource_history[i]
                    curr_left, curr_right = self.resource_history[i + 1]
                    
                    # Calculate mean absolute difference
                    left_diff = np.mean(cv2.absdiff(prev_left, curr_left))
                    right_diff = np.mean(cv2.absdiff(prev_right, curr_right))
                    
                    max_left_diff = max(max_left_diff, left_diff)
                    max_right_diff = max(max_right_diff, right_diff)
                    
                    # Allow for small differences (noise threshold)
                    if left_diff > 1.0 or right_diff > 1.0:  # Adjust threshold as needed
                        all_similar = False
                        if self.debug_mode:
                            logging.info(f"Detected changes - Left diff: {left_diff:.2f}, Right diff: {right_diff:.2f}")
                        break
                
                if self.debug_mode:
                    logging.info(f"Max differences - Left: {max_left_diff:.2f}, Right: {max_right_diff:.2f}")
                    
                    if all_similar:
                        # Save comparison images
                        cv2.imwrite('debug_last_left.png', self.resource_history[-1][0])
                        cv2.imwrite('debug_last_right.png', self.resource_history[-1][1])
                        
                        # Save difference visualization
                        if len(self.resource_history) >= 2:
                            diff_left = cv2.absdiff(self.resource_history[-1][0], self.resource_history[-2][0])
                            diff_right = cv2.absdiff(self.resource_history[-1][1], self.resource_history[-2][1])
                            cv2.imwrite('debug_diff_left.png', diff_left)
                            cv2.imwrite('debug_diff_right.png', diff_right)
                
                # If no significant changes detected over 20 seconds (5 snapshots)
                if all_similar:
                    logging.info("Game over detected - Resources static for 20 seconds")
                    return True
            
            return False

        except Exception as e:
            logging.error(f"Error in game over detection: {e}")
            return False
    
    def detect_activity_zones(self, minimap_image, minimap_mask):
        """Detect activity zones with mask support."""
        activity_zones = []
        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)

        for color in self.active_colors:
            ranges = self.player_colors_config[color]
            
            normal_mask = cv2.inRange(hsv_image, 
                np.array(ranges['normal']['lower'], dtype=np.uint8),
                np.array(ranges['normal']['upper'], dtype=np.uint8))
            
            # Apply minimap mask
            normal_mask = cv2.bitwise_and(normal_mask, minimap_mask)
            
            kernel = np.ones((3,3), np.uint8)
            color_mask = cv2.morphologyEx(normal_mask, cv2.MORPH_OPEN, kernel)
            
            contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, 
                                         cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > self.min_activity_area:
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        
                        if minimap_mask[cy, cx]:
                            importance = min(area / 100, 5)
                            activity_zones.append({
                                'position': (cx, cy),
                                'area': area,
                                'color': color,
                                'importance': importance,
                                'timestamp': time.time()
                            })

            if self.debug_mode:
                debug_img = minimap_image.copy()
                debug_img[minimap_mask == 0] = [128, 128, 128]
                cv2.drawContours(debug_img, contours, -1, (0, 255, 0), 2)
                cv2.imwrite(f'debug_activity_{color}.png', debug_img)

        return sorted(activity_zones, key=lambda x: x['importance'], reverse=True)

    def handle_raid(self, raid, mask):
        """Handle raid detection and camera movement with defender-biased offset."""
        x, y = raid['position']
        if self.is_point_in_minimap(x, y, mask):
            # Get defender's base position
            defender_base = self.territory_tracker.territories[raid['defender']]['main_base']
            if defender_base:
                # Calculate vector from raid to defender base
                base_x, base_y = defender_base['position']
                dx = base_x - x
                dy = base_y - y
                
                # Normalize vector and apply small offset (4-16 pixels)
                distance = np.sqrt(dx*dx + dy*dy)
                if distance > 0:
                    offset_x = int((dx/distance) * 12)  # 12 pixel offset
                    offset_y = int((dy/distance) * 12)
                    
                    # Ensure new position is within mask
                    new_x = x + offset_x
                    new_y = y + offset_y
                    if self.is_point_in_minimap(new_x, new_y, mask):
                        x, y = new_x, new_y
            
            self.click_minimap(x, y, mask)
            self.last_switch_time = time.time()
            logging.info(f"Focusing raid: {raid['attacker']} raiding {raid['defender']} "
                        f"(importance: {raid['importance']:.2f})")
            return True
        return False

    def is_point_in_minimap(self, x, y, mask):
        """Check if a point is within the valid minimap area."""
        try:
            if 0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]:
                return bool(mask[y, x])
            return False
        except Exception as e:
            logging.error(f"Error checking point in minimap: {e}")
            return False

    def calculate_distance(self, pos1, pos2):
        """Calculate Euclidean distance between two positions."""
        return np.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

    def _update_view_position(self, position, time):
        """Helper method to update view position tracking."""
        self.current_view_position = position
        self.time_at_position = time
        self.last_positions.append(position)
        if len(self.last_positions) > 5:
            self.last_positions.pop(0)

    def click_minimap(self, x, y, mask):
        """Click a position on the minimap if it's within bounds."""
        try:
            if not self.is_point_in_minimap(x, y, mask):
                logging.warning(f"Click position ({x}, {y}) outside minimap bounds")
                return
                
            click_x = self.minimap_x + x
            click_y = self.minimap_y + y
            pyautogui.click(click_x, click_y)
            logging.info(f"Clicked minimap at ({click_x}, {click_y})")
        except Exception as e:
            logging.error(f"Error clicking minimap: {e}")

    def calculate_minimap_mask(self, minimap_image):
        """Create a mask for the minimap with the sides pushed out further for precise alignment."""
        try:
            height, width = minimap_image.shape[:2]
            mask = np.zeros((height, width), dtype=np.uint8)

            # Fine-tuning parameters
            vertical_shift = int(height * 0.03)
            top_adjustment = 8
            side_expansion = 14
            bottom_alignment = int(height * 0.88)

            diamond_points = np.array([
                [width // 2, int(height * 0.01) - vertical_shift + top_adjustment],
                [int(width * 0.99) + side_expansion, height // 2 - vertical_shift],
                [width // 2, bottom_alignment],
                [int(width * 0.01) - side_expansion, height // 2 - vertical_shift]
            ], dtype=np.int32)

            cv2.fillPoly(mask, [diamond_points], 255)

            ui_cutouts = [
                np.array([[0, 0], 
                        [width // 2, int(height * 0.01) - vertical_shift + top_adjustment],
                        [0, int(height * 0.35)]], dtype=np.int32),
                np.array([[width // 2, int(height * 0.01) - vertical_shift + top_adjustment], 
                        [width, 0], 
                        [width, int(height * 0.35)]], dtype=np.int32),
                np.array([[width, height // 2 - vertical_shift], 
                        [width, height], 
                        [width // 2, bottom_alignment]], dtype=np.int32),
                np.array([[0, height // 2 - vertical_shift], 
                        [width // 2, bottom_alignment],
                        [0, height]], dtype=np.int32)
            ]

            for ui_region in ui_cutouts:
                cv2.fillPoly(mask, [ui_region], 0)

            if self.debug_mode:
                debug_img = minimap_image.copy()
                cv2.polylines(debug_img, [diamond_points], isClosed=True, color=(0, 0, 255), thickness=2)
                for ui_region in ui_cutouts:
                    cv2.polylines(debug_img, [ui_region], isClosed=True, color=(0, 255, 0), thickness=2)
                cv2.imwrite('debug_red_boundary_final_push.png', debug_img)
                cv2.imwrite('debug_mask_final_push.png', mask)

            return mask

        except Exception as e:
            logging.error(f"Error calculating minimap mask: {e}")
            return None


class TerritoryTracker:
    def __init__(self):
        """Initialize the territory tracker with updated parameters."""
        self.territories = {}
        self.heat_map = None
        self.last_update = 0
        self.update_interval = 1.0  # Reduced for more frequent updates
        self.last_density_map = None
        self.prev_frame = None
        
        # Detection thresholds
        self.RAID_THRESHOLD = 0.4
        self.scout_detection_threshold = 0.08
        self.early_game_multiplier = 1.8
        self.base_detection_threshold = 0.25
        
        # Parameters for clustering
        self.cluster_distance = 30
        self.detection_radius = 60
        
        # Raid tracking
        self.raid_history = {}
        self.staleness_threshold = 8.0
        self.min_movement_threshold = 15
        self.movement_check_interval = 2.0

        # Movement detection weights
        self.movement_weight = 0.4
        self.static_weight = 0.6

    def initialize_player(self, color):
        """Initialize tracking for a new player color."""
        if color not in self.territories:
            self.territories[color] = {
                'main_base': None,
                'enemy_buildings': [],
                'control_zones': [],
                'last_activity': {}
            }

    def update(self, minimap_image, hsv_ranges, active_colors, minimap_mask=None):
        """Update territory understanding with mask support."""
        current_time = time.time()
        if current_time - self.last_update < self.update_interval:
            return
            
        self.last_update = current_time
        
        # Initialize heat map with mask consideration
        if minimap_mask is not None:
            self.heat_map = np.zeros_like(minimap_image[:,:,0], dtype=float)
            self.heat_map[minimap_mask == 0] = -1  # Mark non-playable areas
        else:
            self.heat_map = np.zeros_like(minimap_image[:,:,0], dtype=float)
        
        # Update each player's territory
        for color in active_colors:
            self.initialize_player(color)
            density = self.get_color_density(minimap_image, color, hsv_ranges, minimap_mask)
            
            # Update territory info
            main_base = self.identify_main_base(density)
            if main_base:
                self.territories[color]['main_base'] = main_base
                
            # Update heat map for valid areas
            if minimap_mask is not None:
                valid_area = minimap_mask > 0
                self.heat_map[valid_area] += density[valid_area]

        # Normalize heat map to range [0, 1]
        if minimap_mask is not None:
            valid_area = minimap_mask > 0
            if np.any(valid_area):
                min_val = np.min(self.heat_map[valid_area])
                max_val = np.max(self.heat_map[valid_area])
                if max_val > min_val:
                    self.heat_map[valid_area] = (self.heat_map[valid_area] - min_val) / (max_val - min_val)

    def get_color_density(self, minimap_image, color, hsv_ranges, minimap_mask=None):
        """Calculate density map with mask support and enhanced unit detection."""
        hsv = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)
        ranges = hsv_ranges[color]
        
        # Detect units with lower threshold for better scout detection
        normal_mask = cv2.inRange(hsv, 
            np.array(ranges['normal']['lower'], dtype=np.uint8),
            np.array(ranges['normal']['upper'], dtype=np.uint8))
        
        # Detect buildings
        building_mask = cv2.inRange(hsv,
            np.array(ranges['icon']['lower'], dtype=np.uint8),
            np.array(ranges['icon']['upper'], dtype=np.uint8))
        
        combined_mask = cv2.add(normal_mask, building_mask)
        
        # Apply minimap mask if provided
        if minimap_mask is not None:
            combined_mask = cv2.bitwise_and(combined_mask, minimap_mask)
        
        # Create density map with smaller kernel for better detail
        density = cv2.GaussianBlur(combined_mask, (15, 15), 0)
        density = density.astype(float) / 255.0
        
        return density


    def detect_army_engagements(self, attacker_units, defender_units, minimap_mask=None):
        """Detect significant army presence and potential field battles."""
        engagements = []
        
        # Create binary masks and convert to uint8
        attacker_mask = (attacker_units > self.scout_detection_threshold).astype(np.uint8)
        defender_mask = (defender_units > self.scout_detection_threshold).astype(np.uint8)
        
        # Use larger kernel for army detection
        kernel = np.ones((5,5), np.uint8)
        attacker_mass = cv2.dilate(attacker_mask, kernel)
        defender_mass = cv2.dilate(defender_mask, kernel)
        
        # Find areas with significant unit masses
        attacker_groups = cv2.connectedComponents(attacker_mass)[1]
        defender_groups = cv2.connectedComponents(defender_mass)[1]
        
        # For each significant attacker group
        for group_id in range(1, attacker_groups.max() + 1):
            attacker_pos = np.where(attacker_groups == group_id)
            if len(attacker_pos[0]) > 10:  # Minimum size for army
                center_y = int(np.mean(attacker_pos[0]))
                center_x = int(np.mean(attacker_pos[1]))
                
                # Look for nearby defender armies
                search_radius = 40
                y_start = max(0, center_y - search_radius)
                y_end = min(defender_units.shape[0], center_y + search_radius)
                x_start = max(0, center_x - search_radius)
                x_end = min(defender_units.shape[1], center_x + search_radius)
                
                nearby_defender = defender_groups[y_start:y_end, x_start:x_end]
                if np.any(nearby_defender > 0):
                    defender_pos = np.where(nearby_defender > 0)
                    def_center_y = int(np.mean(defender_pos[0])) + y_start
                    def_center_x = int(np.mean(defender_pos[1])) + x_start
                    
                    battle_x = (center_x + def_center_x) // 2
                    battle_y = (center_y + def_center_y) // 2
                    
                    if minimap_mask is None or minimap_mask[battle_y, battle_x]:
                        army_size = len(attacker_pos[0]) + len(np.where(nearby_defender > 0)[0])
                        engagements.append({
                            'position': (battle_x, battle_y),
                            'importance': min(1.0, army_size / 100) * 1.2,
                            'is_field_battle': True
                        })
        
        return engagements

    def identify_main_base(self, density_map):
        """Identify main base location with enhanced early game detection."""
        kernel = np.ones((21, 21), np.float32) / (21 * 21)
        sustained_density = cv2.filter2D(density_map, -1, kernel)
        
        max_val = sustained_density.max()
        if max_val > self.base_detection_threshold:
            y, x = np.unravel_index(sustained_density.argmax(), sustained_density.shape)
            return {'position': (x, y), 'density': max_val}
        return None

    def detect_raids(self, minimap_image, hsv_ranges, minimap_mask=None):
        """Detect raids with dynamic radius based on territory control and field battles."""
        raids = []
        current_time = time.time()
        
        for attacker in self.territories:
            for defender in self.territories:
                if attacker != defender:
                    # Get densities once for efficiency
                    attacker_units = self.get_color_density(minimap_image, attacker, hsv_ranges, minimap_mask)
                    defender_units = self.get_color_density(minimap_image, defender, hsv_ranges, minimap_mask)
                    
                    # First detect field battles
                    field_battles = self.detect_army_engagements(attacker_units, defender_units, minimap_mask)
                    for battle in field_battles:
                        raids.append({
                            'position': battle['position'],
                            'attacker': attacker,
                            'defender': defender,
                            'importance': battle['importance'],
                            'raid_key': f"battle-{attacker}-{defender}-{battle['position'][0]}-{battle['position'][1]}",
                            'is_field_battle': True
                        })
                    
                    # Then check for base-oriented raids
                    defender_base = self.territories[defender]['main_base']
                    if defender_base:
                        base_x, base_y = defender_base['position']
                        
                        # Calculate territory control radius
                        scan_radius = 80
                        defender_presence = defender_units[
                            max(0, base_y - scan_radius):min(defender_units.shape[0], base_y + scan_radius),
                            max(0, base_x - scan_radius):min(defender_units.shape[1], base_x + scan_radius)
                        ]
                        
                        # Find the furthest significant defender presence
                        significant_presence = defender_presence > self.scout_detection_threshold
                        if np.any(significant_presence):
                            y_indices, x_indices = np.where(significant_presence)
                            distances = np.sqrt(
                                (x_indices - scan_radius) ** 2 + 
                                (y_indices - scan_radius) ** 2
                            )
                            max_distance = np.max(distances)
                            detection_radius = max(40, int(max_distance * 1.2))
                        else:
                            detection_radius = 40
                        
                        y_start = max(0, base_y - detection_radius)
                        y_end = min(attacker_units.shape[0], base_y + detection_radius)
                        x_start = max(0, base_x - detection_radius)
                        x_end = min(attacker_units.shape[1], base_x + detection_radius)
                        
                        roi = attacker_units[y_start:y_end, x_start:x_end]
                        
                        if np.max(roi) > self.scout_detection_threshold:
                            y_coords, x_coords = np.where(roi > self.scout_detection_threshold)
                            
                            for y, x in zip(y_coords, x_coords):
                                actual_x = x + x_start
                                actual_y = y + y_start
                                
                                if minimap_mask is not None and not minimap_mask[actual_y, actual_x]:
                                    continue
                                
                                dist_to_base = np.sqrt((actual_x - base_x)**2 + (actual_y - base_y)**2)
                                
                                territory_factor = 1.0
                                if dist_to_base > detection_radius * 0.7:
                                    territory_factor = 1.2
                                
                                base_importance = self.calculate_raid_importance(
                                    (actual_x, actual_y),
                                    attacker_units,
                                    defender_units,
                                    radius=30
                                ) * territory_factor
                                
                                raid_key = f"{attacker}-{defender}-{actual_x}-{actual_y}"
                                importance = self.adjust_importance_for_movement(
                                    raid_key,
                                    (actual_x, actual_y),
                                    base_importance,
                                    current_time
                                )
                                
                                if importance > self.RAID_THRESHOLD:
                                    raids.append({
                                        'position': (actual_x, actual_y),
                                        'attacker': attacker,
                                        'defender': defender,
                                        'importance': importance,
                                        'raid_key': raid_key,
                                        'is_frontier': dist_to_base > detection_radius * 0.7,
                                        'is_field_battle': False
                                    })
        
        # Clean up old raid history
        self.cleanup_raid_history(current_time)
        return self.cluster_raids(raids)
    


    def adjust_importance_for_movement(self, raid_key, current_pos, base_importance, current_time):
        """Adjust raid importance based on movement history, with special handling for field battles."""
        if raid_key not in self.raid_history:
            self.raid_history[raid_key] = {
                'positions': [current_pos],
                'last_update': current_time,
                'last_movement': current_time
            }
            return base_importance
        
        history = self.raid_history[raid_key]
        last_pos = history['positions'][-1]
        time_since_movement = current_time - history['last_movement']
        
        # Calculate distance moved
        distance = np.sqrt(
            (current_pos[0] - last_pos[0])**2 + 
            (current_pos[1] - last_pos[1])**2
        )
        
        # Update position history if significant movement detected
        if distance > self.min_movement_threshold:
            history['positions'].append(current_pos)
            history['last_movement'] = current_time
            time_since_movement = 0
            
            if len(history['positions']) > 5:
                history['positions'].pop(0)
        
        history['last_update'] = current_time
        
        # Different staleness calculations for field battles vs raids
        if 'battle-' in raid_key:  # Field battle
            staleness_factor = max(0.6, 1.0 - (time_since_movement / (self.staleness_threshold * 1.5)))
        else:  # Regular raid
            staleness_factor = max(0.2, 1.0 - (time_since_movement / self.staleness_threshold))
        
        return base_importance * staleness_factor

    def cleanup_raid_history(self, current_time):
        """Remove old raid records."""
        cleanup_threshold = current_time - (self.staleness_threshold * 2)
        keys_to_remove = []
        
        for raid_key, history in self.raid_history.items():
            if history['last_update'] < cleanup_threshold:
                keys_to_remove.append(raid_key)
        
        for key in keys_to_remove:
            del self.raid_history[key]

    def calculate_raid_importance(self, position, attacker_density, defender_density=None, radius=30):
        """Calculate raid importance prioritizing army proximity and meaningful movement."""
        x, y = position
        y_start = max(0, y - radius)
        y_end = min(attacker_density.shape[0], y + radius)
        x_start = max(0, x - radius)
        x_end = min(attacker_density.shape[1], x + radius)
        
        local_area = attacker_density[y_start:y_end, x_start:x_end]
        
        # Proximity score - check wider radius for nearby units
        proximity_score = 0
        if defender_density is not None:
            # Use larger radius for proximity check
            prox_radius = radius * 2
            prox_y_start = max(0, y - prox_radius)
            prox_y_end = min(attacker_density.shape[0], y + prox_radius)
            prox_x_start = max(0, x - prox_radius)
            prox_x_end = min(attacker_density.shape[1], x + prox_radius)
            
            attacker_presence = attacker_density[prox_y_start:prox_y_end, prox_x_start:prox_x_end]
            defender_presence = defender_density[prox_y_start:prox_y_end, prox_x_start:prox_x_end]
            
            # Calculate proximity based on both armies having units within radius
            if (np.max(attacker_presence) > self.scout_detection_threshold and 
                np.max(defender_presence) > self.scout_detection_threshold):
                proximity_score = 0.95  # High priority for nearby armies
        
        # Movement calculation - reduced sensitivity
        movement_importance = 0
        if self.prev_frame is not None:
            prev_local = self.prev_frame[y_start:y_end, x_start:x_end]
            if prev_local.shape == local_area.shape:
                diff = cv2.absdiff(local_area, prev_local)
                movement = np.mean(diff)
                movement_importance = min(0.7, movement * 3.0)  # Reduced multiplier
        
        # Static importance - slightly increased for forward buildings
        unit_presence = np.sum(local_area > self.scout_detection_threshold)
        static_importance = min(0.4, unit_presence / 25)  # Increased cap
        
        # Final importance calculation
        importance = max(
            proximity_score * 0.95,    # Highest weight for nearby armies
            movement_importance * 0.8, # Moderate weight for movement
            static_importance * 0.3   # Slightly increased weight for static presence
        )
        
        self.prev_frame = attacker_density.copy()
        return importance

    def cluster_raids(self, raids):
        """Cluster nearby raid detections to prevent duplicates."""
        if not raids:
            return []
            
        clustered_raids = []
        while raids:
            base_raid = raids.pop(0)
            base_x, base_y = base_raid['position']
            
            # Find all raids close to this one
            nearby_indices = []
            for i, raid in enumerate(raids):
                x, y = raid['position']
                if np.sqrt((x - base_x)**2 + (y - base_y)**2) < self.cluster_distance:
                    nearby_indices.append(i)
            
            # Merge nearby raids
            for i in sorted(nearby_indices, reverse=True):
                base_raid['importance'] = max(base_raid['importance'], raids[i]['importance'])
                raids.pop(i)
            
            clustered_raids.append(base_raid)
        
        return clustered_raids

    def visualize_territories(self, minimap_image, minimap_mask=None):
        """Debug visualization with mask support."""
        debug_img = minimap_image.copy()
        
        # Apply mask if provided
        if minimap_mask is not None:
            debug_img[minimap_mask == 0] = [128, 128, 128]  # Gray out non-playable areas
        
        for color in self.territories:
            # Visualize main base
            if self.territories[color]['main_base']:
                x, y = self.territories[color]['main_base']['position']
                cv2.circle(debug_img, (x, y), 30, (0, 255, 0), 2)
        
        cv2.imwrite('debug_territory_understanding.png', debug_img)
        
        # Save heatmap visualization
        if self.heat_map is not None:
            heat_vis = np.zeros_like(self.heat_map)
            if minimap_mask is not None:
                valid_area = minimap_mask > 0
                heat_vis[valid_area] = self.heat_map[valid_area]
            else:
                heat_vis = self.heat_map
                
            heat_vis = (heat_vis * 255).astype(np.uint8)
            heat_vis = cv2.applyColorMap(heat_vis, cv2.COLORMAP_JET)
            
            if minimap_mask is not None:
                heat_vis[~valid_area] = [128, 128, 128]
            
            cv2.imwrite('debug_heatmap.png', heat_vis)


