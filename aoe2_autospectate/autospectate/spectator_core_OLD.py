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

class CombatQueue:
    def __init__(self):
        self.active_fights = []
        self.last_visit_times = {}
        self.min_revisit_delay = 3.0  # Minimum seconds before revisiting same fight
        
    def add_combat(self, combat_zone):
        fight_id = f"{combat_zone['position'][0]}_{combat_zone['position'][1]}"
        # Only add if not too close to existing fights
        if not any(self.calculate_distance(combat_zone['position'], f['position']) < 50 
                  for f in self.active_fights):
            self.active_fights.append({
                'id': fight_id,
                'position': combat_zone['position'],
                'importance': combat_zone['importance'],
                'first_seen': time.time()
            })
            
    def get_next_combat(self, current_time):
        if not self.active_fights:
            return None
            
        # Filter fights we've seen too recently
        eligible_fights = [f for f in self.active_fights 
                         if current_time - self.last_visit_times.get(f['id'], 0) > self.min_revisit_delay]
        
        if eligible_fights:
            # Sort by importance but also consider time since last view
            fight = max(eligible_fights, 
                       key=lambda x: x['importance'] * (1 + 0.1 * (current_time - self.last_visit_times.get(x['id'], x['first_seen']))))
            self.last_visit_times[fight['id']] = current_time
            return fight
            
        return None


class TerritoryTracker:
    def __init__(self):
        self.territories = {}  # Will be populated with detected player colors
        self.heat_map = None
        self.last_update = 0
        self.update_interval = 2.0  # Update territory map every 2 seconds
        self.BASE_CHECK_INTERVAL = 10.0
        self.last_base_check = 0
        self.RAID_THRESHOLD = 0.6
        
    def initialize_player(self, color):
        """Add a new player color to track."""
        if color not in self.territories:
            self.territories[color] = {
                'main_base': None,
                'forward_positions': [],
                'control_zones': [],
                'last_activity': {}
            }

    def get_color_density(self, minimap_image, color, hsv_ranges):
        """Calculate density map for a specific color."""
        hsv = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)
        ranges = hsv_ranges[color]
        
        # Combine normal and building masks
        normal_mask = cv2.inRange(hsv, 
            np.array(ranges['normal']['lower'], dtype=np.uint8),
            np.array(ranges['normal']['upper'], dtype=np.uint8))
        
        building_mask = cv2.inRange(hsv,
            np.array(ranges['icon']['lower'], dtype=np.uint8),
            np.array(ranges['icon']['upper'], dtype=np.uint8))
            
        combined_mask = cv2.add(normal_mask, building_mask)
        
        # Create density map using gaussian blur
        density = cv2.GaussianBlur(combined_mask, (21, 21), 0)
        density = density.astype(float) / 255.0
        
        return density

    def identify_main_base(self, density_map):
        """Find the main base location (highest sustained density)."""
        # Use large kernel to find sustained high density
        kernel = np.ones((31, 31), np.float32) / (31 * 31)
        sustained_density = cv2.filter2D(density_map, -1, kernel)
        
        # Find the maximum density point
        max_val = sustained_density.max()
        if max_val > 0.3:  # Threshold for base detection
            y, x = np.unravel_index(sustained_density.argmax(), sustained_density.shape)
            return {'position': (x, y), 'density': max_val}
        return None

    def identify_forward_positions(self, density_map, main_base, min_distance=100):
        """Find forward positions with enhanced distance and density thresholding."""
        if not main_base:
            return []
                
        # Use stricter thresholding for forward positions
        thresh = cv2.threshold(density_map, 0.5, 1.0, cv2.THRESH_BINARY)[1]
        
        # Clean up noise
        kernel = np.ones((5,5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # Find contours of dense areas
        contours, _ = cv2.findContours(thresh.astype(np.uint8), cv2.RETR_EXTERNAL, 
                                    cv2.CHAIN_APPROX_SIMPLE)
        
        forward_positions = []
        main_x, main_y = main_base['position']
        map_diagonal = np.sqrt(density_map.shape[0]**2 + density_map.shape[1]**2)
        
        for contour in contours:
            M = cv2.moments(contour)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                
                # Calculate distance from main base
                dist = np.sqrt((cx - main_x)**2 + (cy - main_y)**2)
                
                # Check if far enough from main base but not too far
                if min_distance < dist < map_diagonal * 0.7:
                    area = cv2.contourArea(contour)
                    if area > 100:  # Minimum area threshold
                        # Calculate strategic value based on distance and size
                        strategic_value = (dist / min_distance) * (area / 100)
                        
                        forward_positions.append({
                            'position': (cx, cy),
                            'area': area,
                            'distance_from_base': dist,
                            'strategic_value': strategic_value
                        })
        
        # Sort by strategic value
        return sorted(forward_positions, key=lambda x: x['strategic_value'], reverse=True)

    def detect_territory_changes(self, current_density_map):
        """Track significant changes in territory control."""
        if not hasattr(self, 'last_density_map'):
            self.last_density_map = current_density_map
            return None
            
        # Calculate territory change
        diff_map = current_density_map - self.last_density_map
        expansion_threshold = 0.3  # Significant territory change threshold
        
        expansion_zones = []
        # Find areas of significant increase
        y_coords, x_coords = np.where(diff_map > expansion_threshold)
        
        if len(x_coords) > 0:
            # Use clustering to group nearby expansion points
            from scipy.cluster.hierarchy import fclusterdata
            if len(x_coords) > 1:
                points = np.column_stack((x_coords, y_coords))
                labels = fclusterdata(points, t=30, criterion='distance')  # 30 pixel radius clusters
                
                for label in np.unique(labels):
                    cluster_points = points[labels == label]
                    center_x = np.mean(cluster_points[:,0])
                    center_y = np.mean(cluster_points[:,1])
                    area = len(cluster_points)
                    
                    expansion_zones.append({
                        'position': (int(center_x), int(center_y)),
                        'area': area,
                        'importance': 0.5,  # Medium priority
                        'type': 'expansion'
                    })
        
        self.last_density_map = current_density_map
        return expansion_zones


    def detect_raids(self, minimap_image, hsv_ranges):
        """Detect potential raids with increased sensitivity for early game."""
        raids = []
        current_time = time.time()
        early_game_multiplier = 1.5  # Increase sensitivity in early game
        
        for attacker in self.territories:
            for defender in self.territories:
                if attacker != defender:
                    # Get attacker units with higher sensitivity
                    attacker_units = self.get_color_density(minimap_image, attacker, hsv_ranges)
                    defender_base = self.territories[defender]['main_base']
                    
                    if defender_base:
                        base_x, base_y = defender_base['position']
                        
                        # Check for any units near the defender's base
                        radius = 50  # Increased detection radius
                        roi = attacker_units[
                            max(0, base_y-radius):min(attacker_units.shape[0], base_y+radius),
                            max(0, base_x-radius):min(attacker_units.shape[1], base_x+radius)
                        ]
                        
                        if np.max(roi) > 0.1:  # Lower threshold for detection
                            # Find all significant unit positions
                            y_coords, x_coords = np.where(roi > 0.1)
                            
                            for y, x in zip(y_coords, x_coords):
                                actual_x = x + max(0, base_x-radius)
                                actual_y = y + max(0, base_y-radius)
                                
                                importance = self.calculate_raid_importance(
                                    (actual_x, actual_y),
                                    attacker_units,
                                    radius=30  # Smaller radius for more precise importance calculation
                                ) * early_game_multiplier
                                
                                if importance > self.RAID_THRESHOLD * 0.7:  # Lower threshold
                                    raids.append({
                                        'position': (actual_x, actual_y),
                                        'attacker': attacker,
                                        'defender': defender,
                                        'importance': importance
                                    })
        
        return raids


    def visualize_territories(self, minimap_image):
        """Debug visualization of territory understanding."""
        debug_img = minimap_image.copy()
        
        for color in self.territories:
            # Visualize main base
            if self.territories[color]['main_base']:
                x, y = self.territories[color]['main_base']['position']
                cv2.circle(debug_img, (x, y), 30, (0, 255, 0), 2)  # Green circle for main base
                
            # Visualize forward positions
            for pos in self.territories[color]['forward_positions']:
                x, y = pos['position']
                cv2.circle(debug_img, (x, y), 15, (255, 0, 0), 2)  # Red circle for forward positions
                
        cv2.imwrite('debug_territory_understanding.png', debug_img)
        
        # Save heatmap visualization
        if self.heat_map is not None:
            heat_vis = (self.heat_map * 255).astype(np.uint8)
            heat_vis = cv2.applyColorMap(heat_vis, cv2.COLORMAP_JET)
            cv2.imwrite('debug_heatmap.png', heat_vis)

    def calculate_raid_importance(self, position, attacker_density, radius=30):
        """Calculate raid importance with better scaling."""
        x, y = position
        local_area = attacker_density[
            max(0, y-radius):min(attacker_density.shape[0], y+radius),
            max(0, x-radius):min(attacker_density.shape[1], x+radius)
        ]
        
        unit_presence = np.sum(local_area > 0.1)
        max_density = np.max(local_area)
        avg_density = np.mean(local_area)
        
        # More granular scaling
        importance = (
            min(0.6, unit_presence / 20) +  # Cap at 0.6 for unit count
            min(0.3, max_density * 0.8) +   # Cap at 0.3 for peak density
            min(0.1, avg_density)           # Cap at 0.1 for average density
        )
        
        return importance

    def update(self, minimap_image, hsv_ranges, active_colors):
        """Update territory understanding."""
        current_time = time.time()
        if current_time - self.last_update < self.update_interval:
            return
            
        self.last_update = current_time
        
        # Initialize heat map
        self.heat_map = np.zeros_like(minimap_image[:,:,0], dtype=float)
        
        # Update each player's territory
        for color in active_colors:
            self.initialize_player(color)
            density = self.get_color_density(minimap_image, color, hsv_ranges)
            
            # Update territory info
            main_base = self.identify_main_base(density)
            if main_base:
                self.territories[color]['main_base'] = main_base
                forward_positions = self.identify_forward_positions(density, main_base)
                self.territories[color]['forward_positions'] = forward_positions
            
            # Update heat map
            self.heat_map += density






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
        
        # Territory tracking
        self.territory_tracker = TerritoryTracker()
        self.active_colors = ['Blue', 'Red']  # Expandable for future
        
        # Initialize viewing queue
        self.viewing_queue = ViewingQueue(min_revisit_time=4.0, proximity_radius=50)

        # Debug flags
        self.debug_mode = False
        self.last_minimap_mask = None

    def capture_minimap(self):
        """Capture the minimap area of the screen."""
        try:
            x1 = self.minimap_x
            y1 = self.minimap_y
            x2 = self.minimap_x + self.minimap_width
            y2 = self.minimap_y + self.minimap_height
            
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            if self.debug_mode:
                cv2.imwrite('debug_minimap.png', frame)
                
            return frame
        except Exception as e:
            logging.error(f"Error capturing minimap: {e}")
            return None

    def calculate_minimap_mask(self, minimap_image):
        """Create a mask for the minimap with the sides pushed out further for precise alignment."""
        try:
            height, width = minimap_image.shape[:2]
            mask = np.zeros((height, width), dtype=np.uint8)

            # Fine-tuning parameters
            vertical_shift = int(height * 0.03)  # Base upward shift for diamond
            top_adjustment = 8  # Keep the top adjustment from earlier
            side_expansion = 14  # Push sides out further for final alignment
            bottom_alignment = int(height * 0.88)  # Keep bottom aligned

            diamond_points = np.array([
                [width // 2, int(height * 0.01) - vertical_shift + top_adjustment],  # Top point unchanged
                [int(width * 0.99) + side_expansion, height // 2 - vertical_shift],  # Right point pushed out
                [width // 2, bottom_alignment],  # Bottom point unchanged
                [int(width * 0.01) - side_expansion, height // 2 - vertical_shift]  # Left point pushed out
            ], dtype=np.int32)

            # Fill the diamond (red playable area)
            cv2.fillPoly(mask, [diamond_points], 255)

            # Define adjusted triangular UI cutouts (green triangles)
            ui_cutouts = [
                # Top-left triangle
                np.array([[0, 0], 
                        [width // 2, int(height * 0.01) - vertical_shift + top_adjustment],  # Match diamond top point
                        [0, int(height * 0.35)]], dtype=np.int32),

                # Top-right triangle
                np.array([[width // 2, int(height * 0.01) - vertical_shift + top_adjustment], 
                        [width, 0], 
                        [width, int(height * 0.35)]], dtype=np.int32),

                # Bottom-right triangle
                np.array([[width, height // 2 - vertical_shift], 
                        [width, height], 
                        [width // 2, bottom_alignment]], dtype=np.int32),  # Match bottom point

                # Bottom-left triangle
                np.array([[0, height // 2 - vertical_shift], 
                        [width // 2, bottom_alignment],  # Match bottom point
                        [0, height]], dtype=np.int32)
            ]

            # Remove the green UI regions from the mask
            for ui_region in ui_cutouts:
                cv2.fillPoly(mask, [ui_region], 0)

            # Debugging visualization
            if self.debug_mode:
                debug_img = minimap_image.copy()
                # Draw the red playable boundary
                cv2.polylines(debug_img, [diamond_points], isClosed=True, color=(0, 0, 255), thickness=2)
                # Draw the green cutout boundaries
                for ui_region in ui_cutouts:
                    cv2.polylines(debug_img, [ui_region], isClosed=True, color=(0, 255, 0), thickness=2)
                # Save the debug images
                cv2.imwrite('debug_red_boundary_final_push.png', debug_img)
                cv2.imwrite('debug_mask_final_push.png', mask)

            return mask

        except Exception as e:
            logging.error(f"Error calculating minimap mask: {e}")
            return None











    

    def is_point_in_minimap(self, x: int, y: int, mask=None):
        """Check if a point is within the valid minimap area."""
        try:
            if mask is None:
                curr_minimap = self.capture_minimap()
                if curr_minimap is None:
                    return False
                mask = self.calculate_minimap_mask(curr_minimap)
                if mask is None:
                    return False
            
            # Check bounds
            if not (0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]):
                return False
                
            # Check if point is in valid area
            return bool(mask[y, x])
            
        except Exception as e:
            logging.error(f"Error checking point in minimap: {e}")
            return False
        
    def validate_position(self, position, mask=None):
        """Validate a (x,y) position tuple against the minimap mask."""
        try:
            x, y = position
            return self.is_point_in_minimap(x, y, mask)
        except Exception as e:
            logging.error(f"Error validating position: {e}")
            return False

    def click_minimap(self, x: int, y: int, mask=None):
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

    def detect_activity_zones(self, minimap_image):
        """Detect all activity zones on the minimap."""
        activity_zones = []
        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)

        # Get the mask first
        mask = self.calculate_minimap_mask(minimap_image)
        if mask is None:
            return activity_zones

        for color in self.active_colors:
            ranges = self.player_colors_config[color]
            
            # Detect normal unit activity
            lower = np.array(ranges['normal']['lower'], dtype=np.uint8)
            upper = np.array(ranges['normal']['upper'], dtype=np.uint8)
            color_mask = cv2.inRange(hsv_image, lower, upper)
            
            # Apply the minimap mask to the color detection
            color_mask = cv2.bitwise_and(color_mask, mask)
            
            # Clean up noise
            kernel = np.ones((3,3), np.uint8)
            color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel)
            
            contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > self.min_activity_area:
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        
                        # Calculate importance based on size
                        importance = min(area / 100, 5)  # Cap importance at 5
                        
                        # Only add if point is within mask
                        if mask[cy, cx]:
                            activity_zones.append({
                                'position': (cx, cy),
                                'area': area,
                                'color': color,
                                'importance': importance,
                                'timestamp': time.time()
                            })

            if self.debug_mode:
                debug_img = minimap_image.copy()
                cv2.drawContours(debug_img, contours, -1, (0, 255, 0), 2)
                cv2.imwrite(f'debug_activity_{color}.png', debug_img)

        # Sort by importance
        return sorted(activity_zones, key=lambda x: x['importance'], reverse=True)




    def handle_raid(self, raid, mask):
        """Handle raid detection and camera movement."""
        x, y = raid['position']
        if self.is_point_in_minimap(x, y, mask):
            self.click_minimap(x, y, mask)
            self.last_switch_time = time.time()
            logging.info(f"Focusing raid: {raid['attacker']} raiding {raid['defender']} "
                        f"(importance: {raid['importance']:.2f})")
            return True
        return False

    def handle_forward_position(self, position, color, mask):
        """Handle forward position monitoring."""
        x, y = position['position']
        if self.is_point_in_minimap(x, y, mask):
            self.click_minimap(x, y, mask)
            self.last_switch_time = time.time()
            logging.info(f"Checking {color} forward position "
                        f"(area: {position['area']:.1f}, "
                        f"distance from base: {position['distance_from_base']:.1f})")
            return True
        return False

    def run_spectator_iteration(self):
        """Run a single iteration of the spectator logic with enhanced decision making and view control."""
        try:
            curr_time = time.time()
            curr_minimap = self.capture_minimap()
            if curr_minimap is None:
                return

            # Initialize view tracking if not exists
            if not hasattr(self, 'current_view_position'):
                self.current_view_position = None
                self.time_at_position = 0
                self.max_view_time = 10.0  # Maximum 10 seconds at one position
                self.last_positions = []    # Track recent positions
                self.forced_view_until = 0  # Track when forced view should end

            # Get minimap mask and update territory tracker
            mask = self.calculate_minimap_mask(curr_minimap)
            self.territory_tracker.update(curr_minimap, self.player_colors_config, self.active_colors)
            
            current_view_duration = random.uniform(self.min_view_duration, self.max_view_duration)

            # Check if we're in a forced temporary view
            if curr_time < self.forced_view_until:
                return

            # Check if we've been looking at the same area too long
            if self.current_view_position:
                time_spent = curr_time - self.time_at_position
                if time_spent > self.max_view_time:
                    # Force a temporary view change
                    temp_zones = self.detect_activity_zones(curr_minimap)
                    if temp_zones:
                        # Filter out recent positions
                        new_zones = [z for z in temp_zones if all(
                            self.calculate_distance(z['position'], p) > 50 
                            for p in self.last_positions
                        )]
                        if new_zones:
                            zone = random.choice(new_zones[:3])
                            self.click_minimap(*zone['position'])
                            self.last_switch_time = curr_time
                            self.forced_view_until = curr_time + 2.0  # Force 2-second view
                            self.last_positions.append(zone['position'])
                            if len(self.last_positions) > 5:
                                self.last_positions.pop(0)
                            logging.info(f"Forced temporary view change (area: {zone['area']:.1f})")
                            return

            # Normal view switching logic
            if curr_time - self.last_switch_time >= current_view_duration:
                # Priority 1: Check for high-importance raids
                raids = self.territory_tracker.detect_raids(curr_minimap, self.player_colors_config)
                if raids:
                    raids.sort(key=lambda x: x['importance'], reverse=True)
                    top_raid = raids[0]
                    
                    if top_raid['importance'] > 0.8:
                        # High importance raid - always focus
                        if self.handle_raid(top_raid, mask):
                            self._update_view_position(top_raid['position'], curr_time)
                            return
                    elif top_raid['importance'] > 0.6 and random.random() > 0.3:
                        # Medium importance raid - 70% chance to focus
                        if self.handle_raid(top_raid, mask):
                            self._update_view_position(top_raid['position'], curr_time)
                            return
                    elif random.random() > 0.7:
                        # Low importance raid - 30% chance to focus
                        if self.handle_raid(top_raid, mask):
                            self._update_view_position(top_raid['position'], curr_time)
                            return

                # Priority 2: Check territory expansion
                expansion_zones = self.territory_tracker.detect_territory_changes(self.territory_tracker.heat_map)
                if expansion_zones and random.random() > 0.7:  # 30% chance to check expansion
                    zone = random.choice(expansion_zones)
                    if self.is_point_in_minimap(zone['position'][0], zone['position'][1], mask):
                        self.click_minimap(*zone['position'])
                        self.last_switch_time = curr_time
                        self._update_view_position(zone['position'], curr_time)
                        logging.info(f"Checking territory expansion (area: {zone['area']:.1f})")
                        return

                # Priority 3: Check forward positions with random selection
                for color in self.active_colors:
                    territory = self.territory_tracker.territories[color]
                    if territory['forward_positions']:
                        # Randomly select from top 3 forward positions
                        top_positions = territory['forward_positions'][:3]
                        selected_pos = random.choice(top_positions)
                        if self.handle_forward_position(selected_pos, color, mask):
                            self._update_view_position(selected_pos['position'], curr_time)
                            return

                # Priority 4: Normal activity with enhanced variety
                new_zones = self.detect_activity_zones(curr_minimap)
                if new_zones:
                    # Add randomization to zone selection
                    importance_threshold = random.uniform(0.3, 0.7)
                    valid_zones = [
                        zone for zone in new_zones 
                        if zone['importance'] > importance_threshold and
                        self.is_point_in_minimap(zone['position'][0], zone['position'][1], mask)
                    ]
                    
                    if valid_zones:
                        # Randomly select from top zones
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

        except Exception as e:
            logging.error(f"Error in spectator iteration: {e}")
            import traceback
            logging.error(traceback.format_exc())

    def _update_view_position(self, position, time):
        """Helper method to update view position tracking."""
        self.current_view_position = position
        self.time_at_position = time
        self.last_positions.append(position)
        if len(self.last_positions) > 5:
            self.last_positions.pop(0)

            
    def calculate_distance(self, pos1, pos2):
        """Calculate Euclidean distance between two positions."""
        return np.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

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
        
        # Territory tracking
        self.territory_tracker = TerritoryTracker()
        self.active_colors = ['Blue', 'Red']  # Expandable for future
        
        # Initialize viewing queue
        self.viewing_queue = ViewingQueue(min_revisit_time=4.0, proximity_radius=50)

        # Debug flags
        self.debug_mode = False
        self.last_minimap_mask = None

    def capture_minimap(self):
        """Capture the minimap area of the screen."""
        try:
            x1 = self.minimap_x
            y1 = self.minimap_y
            x2 = self.minimap_x + self.minimap_width
            y2 = self.minimap_y + self.minimap_height
            
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            if self.debug_mode:
                cv2.imwrite('debug_minimap.png', frame)
                
            return frame
        except Exception as e:
            logging.error(f"Error capturing minimap: {e}")
            return None

    def is_point_in_minimap(self, x: int, y: int, mask) -> bool:
        """Check if a point is within the playable minimap area."""
        if mask is None:
            mask = self.last_minimap_mask
            if mask is None:
                return False
        
        try:
            if 0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]:
                return bool(mask[y, x])
            return False
        except Exception as e:
            logging.error(f"Error checking point in minimap: {e}")
            return False

    def click_minimap(self, x: int, y: int, mask=None):
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


    def handle_raid(self, raid, mask):
        """Handle raid detection and camera movement."""
        x, y = raid['position']
        if self.is_point_in_minimap(x, y, mask):
            self.click_minimap(x, y, mask)
            self.last_switch_time = time.time()
            logging.info(f"Focusing raid: {raid['attacker']} raiding {raid['defender']} "
                        f"(importance: {raid['importance']:.2f})")
            return True
        return False

    def handle_forward_position(self, position, color, mask):
        """Handle forward position monitoring."""
        x, y = position['position']
        if self.is_point_in_minimap(x, y, mask):
            self.click_minimap(x, y, mask)
            self.last_switch_time = time.time()
            logging.info(f"Checking {color} forward position "
                        f"(area: {position['area']:.1f}, "
                        f"distance from base: {position['distance_from_base']:.1f})")
            return True
        return False

    def run_spectator_iteration(self):
        """Run a single iteration of the spectator logic."""
        try:
            curr_time = time.time()
            curr_minimap = self.capture_minimap()
            if curr_minimap is None:
                return

            # Get minimap mask and update territory tracker
            mask = self.calculate_minimap_mask(curr_minimap)
            self.territory_tracker.update(curr_minimap, self.player_colors_config, self.active_colors)
            
            current_view_duration = random.uniform(self.min_view_duration, self.max_view_duration)

            if curr_time - self.last_switch_time >= current_view_duration:
                # Priority 1: Check for raids
                raids = self.territory_tracker.detect_raids(curr_minimap, self.player_colors_config)
                if raids:
                    raids.sort(key=lambda x: x['importance'], reverse=True)
                    if self.handle_raid(raids[0], mask):
                        return

                # Priority 2: Check forward positions
                for color in self.active_colors:
                    territory = self.territory_tracker.territories[color]
                    if territory['forward_positions']:
                        positions = sorted(territory['forward_positions'],
                                        key=lambda x: x['area'], reverse=True)
                        if self.handle_forward_position(positions[0], color, mask):
                            return

                # Priority 3: Normal activity
                new_zones = self.detect_activity_zones(curr_minimap)
                for zone in new_zones:
                    if self.is_point_in_minimap(zone['position'][0], zone['position'][1], mask):
                        self.viewing_queue.add_zone(zone)

                next_view = self.viewing_queue.get_next_view()
                if next_view:
                    x, y = next_view['position']
                    if self.is_point_in_minimap(x, y, mask):
                        self.click_minimap(x, y, mask)
                        self.last_switch_time = curr_time
                        logging.info(f"Switched to {next_view['color']} activity "
                                f"(area: {next_view['area']:.1f}, "
                                f"importance: {next_view.get('importance', 1.0):.1f})")

        except Exception as e:
            logging.error(f"Error in spectator iteration: {e}")
            import traceback
            logging.error(traceback.format_exc())

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