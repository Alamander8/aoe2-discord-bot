import time
import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import logging
import random
from collections import deque
from typing import Dict, List, Tuple, Optional
from threading import Lock 
import math
from betting_bridge import BettingBridge 
import requests

class ViewingQueue:
    def __init__(self, min_revisit_time: float = 4.0, proximity_radius: int = 50):
        self.queue = deque()
        self.viewed_positions = {}
        self.min_revisit_time = min_revisit_time
        self.proximity_radius = proximity_radius
        
        # New tracking attributes
        self.view_counts = {}  # Track how many times we've viewed each area
        self.last_base_visit = {}  # Track when we last visited each base
        self.staleness_threshold = 2  # Number of views before applying staleness
        self.base_visit_interval = 45.0  # Seconds between forced base checks
        self.max_view_count = 5
        self.staleness_penalty = 0.7

    def add_zone(self, zone: dict) -> None:
        if self._is_new_area(zone['position']):
            pos_key = f"{zone['position'][0]},{zone['position'][1]}"
            view_count = self.view_counts.get(pos_key, 0)
            
            # Enhanced staleness penalty
            if view_count > self.staleness_threshold:
                # Apply stronger penalty for static positions
                if not zone.get('is_moving', False):
                    zone['importance'] *= max(0.3, self.staleness_penalty ** (view_count - self.staleness_threshold))
                else:
                    # Lighter penalty for moving units
                    zone['importance'] *= max(0.5, 0.9 ** (view_count - self.staleness_threshold))
            
            self.queue.append(zone)
            self.view_counts[pos_key] = view_count + 1
            
            # Cap view count to prevent integer overflow
            if self.view_counts[pos_key] > self.max_view_count:
                self.view_counts[pos_key] = self.max_view_count

    def get_current_view(self) -> Optional[dict]:
        """Get the currently viewed zone without removing it from queue"""
        return self.queue[0] if self.queue else None

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
                
                # Record if this is a base visit
                if zone.get('type') == 'base_development':
                    self.record_base_visit(zone.get('color'))
                
                return zone
        return None
    
    def boost_base_priority(self, color):
        """Add a high-priority base check to the queue"""
        # This should be called by SpectatorCore which has access to base positions
        base_zone = {
            'position': None,  # Will be set by SpectatorCore
            'importance': 0.6,  # High importance to ensure it gets viewed
            'type': 'base_development',
            'color': color,
            'timestamp': time.time()
        }
        self.queue.appendleft(base_zone)  # Add to front of queue

    def record_base_visit(self, color):
        """Record when we visit a base"""
        if color:
            self.last_base_visit[color] = time.time()

    def reset_view_count(self, position):
        """Reset view count when we've moved far away"""
        pos_key = f"{position[0]},{position[1]}"
        for key in list(self.view_counts.keys()):
            x, y = map(int, key.split(','))
            dx = position[0] - x
            dy = position[1] - y
            if (dx*dx + dy*dy) > (self.proximity_radius * 2) ** 2:
                self.view_counts[key] = 0

    def clear(self) -> None:
        self.queue.clear()
        self.viewed_positions.clear()
        self.view_counts.clear()
        self.last_base_visit.clear()

    def calculate_distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Calculate Euclidean distance between two positions"""
        return np.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)



class BaseMonitor:
    def __init__(self, spectator_core):
        self.spectator_core = spectator_core
        self.last_base_check = {}
        self.base_check_interval = 35  # seconds
        self.min_base_view_time= 3.0
        self.growth_areas = {}
        self.last_positions = {}  # To track previous positions for growth detection
        self.forced_base_views={}
        self.last_base_view ={'Blue': 0, 'Red': 0}
        self.minimum_interval_between_checks = 10.0
        self.viewing_times = {'Blue': 0, 'Red': 0}
        self.last_view_update = time.time()
        
    def should_check_base(self, player_color, current_time):
        """Now returns a priority instead of forcing immediate view"""
        last_check = self.last_base_check.get(player_color, 0)
        if current_time - last_check >= self.base_check_interval:
            self.last_base_check[player_color] = current_time
            return True
        return False

    def update_viewing_times(self, current_color, current_time):
        """Track viewing time per player"""
        if current_color:
            time_delta = current_time - self.last_view_update
            self.viewing_times[current_color] = self.viewing_times.get(current_color, 0) + time_delta
        self.last_view_update = current_time

    def get_balance_multiplier(self, color):
        """Get multiplier to balance viewing time between players"""
        total_time = sum(self.viewing_times.values())
        if total_time == 0:
            return 1.0
        
        other_color = 'Red' if color == 'Blue' else 'Blue'
        color_percentage = self.viewing_times.get(color, 0) / total_time
        
        if color_percentage > 0.6:  # If we've spent more than 60% time on one player
            return 0.7  # Reduce importance
        elif color_percentage < 0.4:  # If we've spent less than 40% time
            return 1.4  # Increase importance
        return 1.0
    def get_tc_position(self, player_color):
        """Returns the TC position for the given player color"""
        if player_color in self.spectator_core.territory_tracker.territories:
            base = self.spectator_core.territory_tracker.territories[player_color]['main_base']
            if base:
                return base['position']
        return None


    def is_force_viewing_base(self, current_time):
        """Check if we're currently in a forced base view"""
        for color, end_time in list(self.forced_base_views.items()):
            if current_time < end_time:
                return True
            else:
                del self.forced_base_views[color]
        return False



    def get_next_growth_area(self, player_color):
        """Returns highest activity area in player's territory that matches player's color"""
        if player_color not in self.spectator_core.territory_tracker.territories:
            return None
            
        current_minimap = self.spectator_core.capture_minimap()
        if current_minimap is None:
            return self.get_tc_position(player_color)
                    
        player_density = self.spectator_core.territory_tracker.get_color_density(
            current_minimap,
            player_color,
            self.spectator_core.player_colors_config
        )
        
        if player_density is None:
            return self.get_tc_position(player_color)
            
        # Get main base position as reference
        base_pos = self.get_tc_position(player_color)
        if not base_pos:
            return None
            
        # Look for highest density of PLAYER'S units/buildings in their territory
        base_x, base_y = base_pos
        search_radius = 100
        
        y_start = max(0, base_y - search_radius)
        y_end = min(player_density.shape[0], base_y + search_radius)
        x_start = max(0, base_x - search_radius)
        x_end = min(player_density.shape[1], base_x + search_radius)
        
        # Get region around base
        roi = player_density[y_start:y_end, x_start:x_end]
        
        # Find highest density position
        max_y, max_x = np.unravel_index(np.argmax(roi), roi.shape)
        actual_x = x_start + max_x
        actual_y = y_start + max_y
        
        # Verify the point has meaningful activity
        if player_density[actual_y, actual_x] > 0.2:  # Threshold to ensure we find actual activity
            return (actual_x, actual_y)
        return base_pos  # Fallback to TC if no significant activity found
    
    def track_base_growth(self, player_color, current_frame):
        """Track base growth for a player"""
        if player_color not in self.growth_areas:
            self.growth_areas[player_color] = []
            
        # Compare with previous frame to detect new structures
        new_structures = self.detect_new_structures(player_color, current_frame)
        if new_structures:
            self.growth_areas[player_color].extend(new_structures)
            
        # Prune old growth areas after certain time
        self.prune_old_areas(player_color)
    
    def detect_new_structures(self, player_color, current_frame):
        """Detects new structures in the current frame"""
        # For now, returning empty list until we implement detection
        return []
        
    def prune_old_areas(self, player_color):
        """Removes old growth areas"""
        # Will implement pruning logic later
        pass




class SpectatorCore:
    def __init__(self, config, betting_bridge=None):
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
        self.game_start_time = time.time()
        self.last_minimap = None
        self.current_mask = None
        self.minimap_lock = Lock() 
        self.last_military_check = 0
        self.military_check_interval = 8.0
        self.recent_visits = []
        self.last_density_map = None
        self.last_expansion_check = {
            'Blue': 0,
            'Red': 0
        }
        self.max_expansion_importance = 2.0 

        # betting
        self.betting_bridge = betting_bridge

        # Initialize
        self.base_monitor = BaseMonitor(self)
        
        # Color configuration - get from passed config object
        self.player_colors_config = getattr(config, 'PLAYER_HSV_RANGES', {})
        
        # Activity thresholds
        self.min_activity_area = 40
        self.large_activity_threshold = 150
        
        # Timing settings
        self.min_view_duration = 3.0
        self.max_view_duration = 5.0
        self.combat_view_duration = 10.0
        self.last_switch_time = time.time()
        self.last_visit_times = {
            'Blue': {'military': 0, 'economy': 0},
            'Red': {'military': 0, 'economy': 0}
        }
        
        # Previous frame storage for movement detection
        self.prev_frame = None
        self.movement_weight = 0.7  # Moderate boost for movement
        self.static_weight = 0.2  # Still significant weight for static elements

        # Initialize territory tracker with building parameters from config
        building_params = {
            'min_area': getattr(config, 'BUILDING_ICON_MIN_AREA', 15),
            'max_area': getattr(config, 'BUILDING_ICON_MAX_AREA', 50),
            'min_circularity': getattr(config, 'BUILDING_ICON_MIN_CIRCULARITY', 0.6)
        }
        self.territory_tracker = TerritoryTracker(building_params)
        self.viewing_queue = ViewingQueue(min_revisit_time=3.0, proximity_radius=50)
        
        # Active colors for 1v1
        self.active_colors = ['Blue', 'Red']

        self.recent_visits = {}
        
        # Debug flags
        self.debug_mode = False
        self.last_minimap_mask = None

    def _cleanup_recent_visits(self, current_time, retention_time=60.0):
        """Remove old visits from tracking"""
        self.recent_visits = [
            visit for visit in self.recent_visits 
            if current_time - visit['timestamp'] < retention_time
        ]


    def calculate_expansion_importance(self, color, current_time, base_importance=0.7):
        """Calculate ramping importance for expansion checks"""
        time_since_check = current_time - self.last_expansion_check.get(color, 0)
        
        # Start ramping up after 30 seconds, cap at max_expansion_importance
        ramp_factor = min(self.max_expansion_importance, 1.0 + (time_since_check - 30) / 60)
        
        # Never exceed military importance
        return min(base_importance * ramp_factor, 2.0)

    def add_fallback_views(self, all_activities, current_time):
        """Add balanced fallback views between players"""
        # Track last fallback color
        if not hasattr(self, 'last_fallback_color'):
            self.last_fallback_color = None

        # If we have no activities, add balanced fallback views
        if not all_activities:
            # Determine which color to start with
            if self.last_fallback_color == 'Blue':
                colors = ['Red', 'Blue']
            else:
                colors = ['Blue', 'Red']

            for color in colors:
                base_pos = self.base_monitor.get_tc_position(color)
                if base_pos:
                    all_activities.append({
                        'position': base_pos,
                        'importance': 0.1 *(0.8 + random.random() * 0.4),  # Very low importance with random variation
                        'type': 'fallback_view',
                        'color': color,
                        'timestamp': current_time
                    })
                    self.last_fallback_color = color
                    break  # Only add one fallback view at a time


    def decide_next_view(self, curr_minimap, mask, military_mode=False):
        """
        Enhanced view decision making with better economic activity integration
        and static building handling.
        """
        try:
            all_activities = []
            current_time = time.time()

            # Clean up old visits
            self._cleanup_recent_visits(current_time)
            
            # Track time since last eco view for force check logic
            time_since_eco = {
                'Blue': current_time - self.last_visit_times['Blue']['economy'],
                'Red': current_time - self.last_visit_times['Red']['economy']
            }
            needs_eco_check = any(t > 45.0 for t in time_since_eco.values())

            # Handle territory breaches (with increased importance)
            breaches = self.check_territory_breaches(curr_minimap, mask)
            for breach in breaches:
                breach['importance'] *= 3.5
                if breach.get('color'):
                    balance_multiplier = self.base_monitor.get_balance_multiplier(breach['color'])
                    breach['importance'] *= balance_multiplier
                all_activities.append(breach)
                
            # Get military activities
            military_data = self.check_military_situation(curr_minimap, mask, military_mode=military_mode)
            military_activities = military_data['activities']
            
            # Filter out likely static buildings from military activities
            military_activities = [
                act for act in military_activities 
                if act.get('is_moving', False) or  # Moving units are definitely military
                (act.get('movement_score', 0) > 0.08) or  # Increased movement threshold
                (act.get('area', 0) < 25)  # Small units are likely military
            ]
            
            # Enhance military proximity detection
            for activity in military_activities:
                enemy_units = [a for a in military_activities if a['color'] != activity['color']]
                nearby_enemies = [
                    e for e in enemy_units 
                    if self.calculate_distance(activity['position'], e['position']) < 35
                ]
                
                # Multiple enemies nearby increases importance
                if nearby_enemies:
                    activity['importance'] *= (1.0 + (len(nearby_enemies) * 0.3))
                    if len(nearby_enemies) >= 2:
                        activity['type'] = 'potential_engagement'
                        activity['importance'] *= 1.7
                
                # Combat detection
                closest_enemy = min([self.calculate_distance(activity['position'], e['position']) 
                                for e in enemy_units], default=1000)
                
                # Check proximity to enemy base
                enemy_color = 'Red' if activity['color'] == 'Blue' else 'Blue'
                enemy_base = self.base_monitor.get_tc_position(enemy_color)
                if enemy_base:
                    dist_to_enemy_base = self.calculate_distance(activity['position'], enemy_base)
                    # Higher importance when closer to enemy base
                    activity['importance'] *= max(1.0, 2.5 - (dist_to_enemy_base / 50))
                
                # Combat detection
                if closest_enemy < 25:  # More sensitive combat detection
                    activity['type'] = 'major_combat'
                    activity['importance'] *= 5.0
                    activity['view_duration'] = self.combat_view_duration
                elif closest_enemy < 35:  # New tier for nearby units
                    activity['type'] = 'potential_combat'
                    activity['importance'] *= 2.6
                
                # Movement bonus
                if activity.get('is_moving', False):
                    activity['importance'] *= 3.5  # Bigger bonus for movement
                    # Add check for direction relative to enemy base
                    if enemy_base:
                        vector_to_enemy = (
                            enemy_base[0] - activity['position'][0],
                            enemy_base[1] - activity['position'][1]
                        )
                        if vector_to_enemy[0] * vector_to_enemy[0] + vector_to_enemy[1] * vector_to_enemy[1] > 0:
                            activity['importance'] *= 1.6  # Extra boost if moving toward enemy
                
                # Time balance factor
                time_since_military = current_time - self.last_visit_times[activity['color']]['military']
                if time_since_military > 20:
                    activity['importance'] *= 2.0

                # Apply viewing time balance
                if activity.get('color'):
                    balance_multiplier = self.base_monitor.get_balance_multiplier(activity['color'])
                    activity['importance'] *= balance_multiplier
                
                all_activities.append(activity)

            # Detect quiet period (no movement) - at main function level
            movement_detected = any(act.get('is_moving', False) for act in military_activities)
            if not movement_detected:
                quiet_period_activities = []
                
                # Check latest territory expansions for both players
                for color in ['Blue', 'Red']:
                    # Get territory density for this color
                    density = self.territory_tracker.get_color_density(
                        curr_minimap, color, self.player_colors_config, mask
                    )
                    
                    if density is not None:
                        # Get main base position as reference
                        base_pos = self.base_monitor.get_tc_position(color)
                        if not base_pos:
                            continue
                            
                        # Look for highest density areas away from main base
                        y_start = max(0, base_pos[1] - 80)
                        y_end = min(density.shape[0], base_pos[1] + 80)
                        x_start = max(0, base_pos[0] - 80)
                        x_end = min(density.shape[1], base_pos[0] + 80)
                        
                        # Get region around base
                        roi = density[y_start:y_end, x_start:x_end]
                        
                        # Find top 3 density positions
                        flat_indices = np.argsort(roi.ravel())[-3:]
                        positions = [(x_start + (idx % roi.shape[1]), 
                                    y_start + (idx // roi.shape[1])) 
                                    for idx in flat_indices]
                        
                        for i, pos in enumerate(positions):
                            if density[pos[1], pos[0]] > 0.2:  # Ensure meaningful activity
                                if not self._is_recently_visited(pos):
                                    base_importance = 0.7 - (i * 0.1)
                                    ramped_importance = self.calculate_expansion_importance(
                                        color, 
                                        current_time, 
                                        base_importance
                                    )
                                    
                                    quiet_period_activities.append({
                                        'position': pos,
                                        'importance': ramped_importance,
                                        'type': 'quiet_period_expansion_check',
                                        'color': color,
                                        'timestamp': current_time
                                    })
                
                all_activities.extend(quiet_period_activities)

            # Add economic activities in these cases:
            # 1. No major combat
            # 2. Haven't checked economy in a while
            # 3. Few military activities
            if (not any(a.get('type') == 'major_combat' for a in all_activities) and 
                (needs_eco_check or len(military_activities) < 2)) and not military_mode:
                
                # Add economic activities with exploration
                self.add_economic_activities(all_activities, curr_minimap, mask)

                # Base checks with reduced importance
                bases = self.check_base_development()
                if bases:
                    for base in bases:
                        time_since_eco = current_time - self.last_visit_times[base['color']]['economy']
                        base_boost = min(2.0, time_since_eco / 30.0)
                        # Higher base importance when we need an eco check
                        base_multiplier = 0.6 if needs_eco_check else 0.4
                        base['importance'] = base['importance'] * base_multiplier * base_boost
                        if base.get('color'):
                            balance_multiplier = self.base_monitor.get_balance_multiplier(base['color'])
                            base['importance'] *= balance_multiplier
                        all_activities.append(base)
                
                # General activities
                general = self.detect_activity_zones(curr_minimap, mask)
                if general:
                    for activity in general:
                        activity['importance'] *= 0.3
                        if activity.get('color'):
                            balance_multiplier = self.base_monitor.get_balance_multiplier(activity['color'])
                            activity['importance'] *= balance_multiplier
                        all_activities.append(activity)

                # Add exploration points for expansion checking
                for color in ['Blue', 'Red']:
                    if time_since_eco[color] > 25:
                        explore_pos = self.get_base_exploration_point(color, mask)
                        if explore_pos and not self._is_recently_visited(explore_pos):
                            all_activities.append({
                                'position': explore_pos,
                                'importance': 0.4 * (time_since_eco[color] / 30.0),
                                'type': 'base_exploration',
                                'color': color,
                                'timestamp': current_time
                            })

            # Fallback views if needed
            if not all_activities:
                self.add_fallback_views(all_activities, current_time)

            # Sort and deduplicate activities
            all_activities.sort(key=lambda x: x['importance'], reverse=True)
            activities = self._deduplicate_activities(all_activities)
            
            # Update tracking for selected activity
            if activities:
                self.recent_visits.append({
                    'position': activities[0]['position'],
                    'timestamp': current_time
                })
                
                if activities[0].get('type') == 'quiet_period_expansion_check':
                    self.last_expansion_check[activities[0]['color']] = current_time
                    
                logging.info(f"Selected activity: {activities[0].get('type')} with importance {activities[0].get('importance', 0.0):.2f}")
            else:
                logging.warning("No activities found for next view")
            
            return activities
            
        except Exception as e:
            logging.error(f"Error in decide_next_view: {e}")
            return []
        

        
    def handle_major_combat(self, position):
        """Convert minimap position to screen coordinates and perform drag-follow only for army vs army"""
        try:
            # First click position and verify combat
            self.click_minimap(position[0], position[1], self.current_mask)
            time.sleep(0.4)  # Wait for camera to center
            
            # Verify both armies are present in combat
            if not self.verify_active_combat(self.last_minimap, self.current_mask, position):
                logging.info("No active combat detected, using regular view")
                return
                
            screen_x = self.game_area_x + int((position[0] / self.minimap_width) * self.game_area_width)
            screen_y = self.game_area_y + int((position[1] / self.minimap_height) * self.game_area_height)
            
            box_width = int(self.game_area_width * 0.5)
            box_height = int(self.game_area_height * 0.5)
            
            start_x = max(self.game_area_x, screen_x - (box_width // 2))
            start_y = max(self.game_area_y, screen_y - (box_height // 2))
            end_x = min(self.game_area_x + self.game_area_width, start_x + box_width)
            end_y = min(self.game_area_y + self.game_area_height, start_y + box_height)
            
            self.drag_and_follow(start_x, start_y, end_x, end_y)
            self.forced_view_until = time.time() + 15.0  # 15 seconds minimum for major combat
            logging.info(f"Initiated drag-follow for army vs army combat")
                
        except Exception as e:
            logging.error(f"Error in handle_major_combat: {e}")


    def drag_and_follow(
        self, 
        center_x,
        center_y,
        width_ratio=0.6,
        height_ratio=0.35,
        duration=1.0
    ):
        """
        Perform a drag-and-follow, ensuring we stay away from each edge 
        of our game area by a specified margin.
        """

        left_margin = 300
        right_margin = 300
        top_margin = 300
        bottom_margin = 300

        try:
            box_width = int(self.game_area_width * width_ratio)
            box_height = int(self.game_area_height * height_ratio)

            # Compute the nominal top-left and bottom-right from center
            start_x = center_x - box_width // 2
            start_y = center_y - box_height // 2
            end_x = start_x + box_width
            end_y = start_y + box_height

            # Define the safe bounding box within your game area
            safe_min_x = self.game_area_x + left_margin
            safe_max_x = (self.game_area_x + self.game_area_width) - right_margin
            safe_min_y = self.game_area_y + top_margin
            safe_max_y = (self.game_area_y + self.game_area_height) - bottom_margin

            # Clamp all four sides
            start_x = max(safe_min_x, min(safe_max_x, start_x))
            end_x   = max(safe_min_x, min(safe_max_x, end_x))
            start_y = max(safe_min_y, min(safe_max_y, start_y))
            end_y   = max(safe_min_y, min(safe_max_y, end_y))

            # If the box collapses, skip
            if end_x <= start_x or end_y <= start_y:
                logging.warning("Drag box is invalid/collapsed; skipping drag.")
                return

            # Move mouse to start
            pyautogui.moveTo(start_x, start_y, duration=0.2)
            time.sleep(0.05)

            # Perform the drag
            pyautogui.mouseDown(button='left')
            pyautogui.moveTo(end_x, end_y, duration=duration)
            pyautogui.mouseUp(button='left')

            # Press 'f' to follow
            time.sleep(0.3)
            pyautogui.press('f')

            logging.info(
                f"Drag-follow from ({start_x}, {start_y}) to ({end_x}, {end_y}). "
                f"Margins: L={left_margin}, R={right_margin}, T={top_margin}, B={bottom_margin}"
            )

        except Exception as e:
            logging.error(f"Error in drag_and_follow: {e}")
            pyautogui.mouseUp(button='left')


    def verify_active_combat(self, minimap_image, mask, position):
        """Verify both armies are actively present in the same area"""
        try:
            # Define search area around position
            search_radius = 10  # Adjusted for minimap scale
            x, y = position
            
            # Get densities for both armies in this area
            blue_density = self.territory_tracker.get_color_density(
                minimap_image, 'Blue', self.player_colors_config, mask
            )
            red_density = self.territory_tracker.get_color_density(
                minimap_image, 'Red', self.player_colors_config, mask
            )
            
            if blue_density is None or red_density is None:
                return False
                
            # Define region of interest
            y_start = max(0, y - search_radius)
            y_end = min(blue_density.shape[0], y + search_radius)
            x_start = max(0, x - search_radius)
            x_end = min(blue_density.shape[1], x + search_radius)
            
            # Check if both armies have significant presence in this area
            blue_presence = np.max(blue_density[y_start:y_end, x_start:x_end]) > 0.25
            red_presence = np.max(red_density[y_start:y_end, x_start:x_end]) > 0.25
            
            return blue_presence and red_presence
        except Exception as e:
            logging.error(f"Error verifying combat: {e}")
            return False


    def check_territory_breaches(self, curr_minimap, mask):
        """Check for units in enemy territory"""
        breaches = []
        
        for color in ['Blue', 'Red']:
            enemy_color = 'Red' if color == 'Blue' else 'Blue'
            
            # Get enemy territory
            enemy_territory = self.territory_tracker.get_territory_mask(enemy_color)
            if enemy_territory is None:
                continue
                
            # Check for units in enemy territory
            density = self.territory_tracker.get_color_density(
                curr_minimap, color, self.player_colors_config, mask
            )
            
            if density is not None:
                # Find units in enemy territory
                breaching_units = (density > self.territory_tracker.scout_detection_threshold) & (enemy_territory > 0.3)
                
                if np.any(breaching_units):
                    # Find centroids of breaching groups
                    contours, _ = cv2.findContours(breaching_units.astype(np.uint8), 
                                                cv2.RETR_EXTERNAL, 
                                                cv2.CHAIN_APPROX_SIMPLE)
                    
                    for contour in contours:
                        area = cv2.contourArea(contour)
                        if area > 15:  # Even small groups are interesting if in enemy territory
                            M = cv2.moments(contour)
                            if M["m00"] != 0:
                                cx = int(M["m10"] / M["m00"])
                                cy = int(M["m01"] / M["m00"])
                                
                                breaches.append({
                                    'position': (cx, cy),
                                    'area': area,
                                    'color': color,
                                    'importance': min(1.0, area / 30.0) * 3.0,  # High importance for breaches
                                    'type': 'territory_breach',
                                    'timestamp': time.time()
                                })
        
        return breaches
    
    def get_minimap_state(self):
        """Capture all minimap-related state in one locked operation."""
        try:
            with self.minimap_lock:
                curr_minimap = self.capture_minimap()
                if curr_minimap is None:
                    return None, None
                    
                mask = self.calculate_minimap_mask(curr_minimap)
                if mask is None:
                    return None, None
                    
                return curr_minimap, mask
        except Exception as e:
            logging.error(f"Error capturing minimap state: {e}")
            return None, None



    def get_base_exploration_point(self, color, mask=None):
        """Get a point to explore around player's base with intelligent resource positioning"""
        try:
            base_pos = self.get_tc_position(color)
            if not base_pos:
                return None
            
            # Get territory density for this color to find active areas
            density = self.territory_tracker.get_color_density(
                self.last_minimap, color, self.player_colors_config, mask
            )
            
            if density is not None:
                # Look for activity clusters in base territory
                y_start = max(0, base_pos[1] - 50)
                y_end = min(density.shape[0], base_pos[1] + 50)
                x_start = max(0, base_pos[0] - 50)
                x_end = min(density.shape[1], base_pos[0] + 50)
                
                base_territory = density[y_start:y_end, x_start:x_end]
                
                # Find points of interest (areas with activity)
                points = np.where(base_territory > 0.2)
                if len(points[0]) > 0:
                    # Randomly select from active points, favoring unexplored areas
                    idx = random.randint(0, len(points[0]) - 1)
                    explore_x = x_start + points[1][idx]
                    explore_y = y_start + points[0][idx]
                    
                    # Check if point has been recently visited
                    if not self._is_recently_visited((explore_x, explore_y)):
                        return (explore_x, explore_y)
            
            # Fallback: use directional exploration
            directions = [
                (-30, -30),  # Back/left (likely woodlines)
                (50, -30),   # Back/right (likely gold/stone)
                (0, 50),     # Forward (likely expansion)
                (-50, 0),    # Left (likely resources)
                (50, 0),     # Right (likely resources)
            ]
            
            # Try each direction until finding unvisited point
            for x_offset, y_offset in directions:
                point = (
                    base_pos[0] + x_offset,
                    base_pos[1] + y_offset
                )
                if not self._is_recently_visited(point) and self._is_valid_point(point, mask):
                    return point
                    
            return base_pos  # Fallback to TC if no good points found
            
        except Exception as e:
            logging.error(f"Error getting exploration point: {e}")
            return base_pos


    def is_likely_building_icon(self, contour, frame):
        """Enhanced building detection using template matching"""
        area = cv2.contourArea(contour)
        
        # Quick check for size range
        if area < 15 or area > 25:  # Typical TC/Castle size range
            return False
            
        # Check shape characteristics
        perimeter = cv2.arcLength(contour, True)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = area / hull_area if hull_area > 0 else 0
        circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0
        
        # If basic shape checks pass, try template matching
        if solidity > 0.95 and circularity > 0.8:
            building_type = self.detect_building_type(contour, frame)
            return building_type is not None
            
        return False

    def add_economic_activities(self, all_activities, curr_minimap, mask):
        """Add economic activities with focus on expansion and new activity"""
        try:
            current_time = time.time()
            
            for color in ['Blue', 'Red']:
                # Get territory density to detect economic activity
                density = self.territory_tracker.get_color_density(
                    curr_minimap, color, self.player_colors_config, mask
                )
                
                if density is not None:
                    # Get main base position as reference
                    base_pos = self.base_monitor.get_tc_position(color)
                    if not base_pos:
                        continue
                    
                    # Compare with previous density if available
                    if hasattr(self, 'last_eco_density') and color in self.last_eco_density:
                        prev_density = self.last_eco_density[color]
                        if prev_density is not None and prev_density.shape == density.shape:
                            # Look for new construction/activity
                            diff = density - prev_density
                            new_activity = np.where(diff > 0.2)  # Significant new activity
                            for i in range(len(new_activity[0])):
                                y, x = new_activity[0][i], new_activity[1][i]
                                dist_from_base = self.calculate_distance((x, y), base_pos)
                                if dist_from_base > 30:  # If significantly away from base
                                    if not self._is_recently_visited((x, y)):
                                        all_activities.append({
                                            'position': (x, y),
                                            'importance': 0.7,  # Higher importance for new expansion
                                            'type': 'economic_expansion',
                                            'color': color,
                                            'timestamp': current_time
                                        })
                    
                    # Store current density for next comparison
                    if not hasattr(self, 'last_eco_density'):
                        self.last_eco_density = {}
                    self.last_eco_density[color] = density.copy()
                    
                    # Check unexplored areas around base
                    time_since_eco = current_time - self.last_visit_times[color]['economy']
                    if time_since_eco > 20:  # Frequent enough to catch expansions
                        explore_pos = self.get_base_exploration_point(color, mask)
                        if explore_pos and not self._is_recently_visited(explore_pos):
                            dist_from_base = self.calculate_distance(explore_pos, base_pos)
                            if dist_from_base > 30:  # Prioritize expansion areas
                                all_activities.append({
                                    'position': explore_pos,
                                    'importance': 0.6 * (time_since_eco / 30.0),  # Scales with time
                                    'type': 'expansion_exploration',
                                    'color': color,
                                    'timestamp': current_time
                                })
                            
                    # Add periodic base check with low importance
                    time_since_base = current_time - self.last_visit_times[color]['economy']
                    if time_since_base > 45.0:  # Long time since checking base
                        all_activities.append({
                            'position': base_pos,
                            'importance': 0.3,  # Low importance to avoid overshadowing military
                            'type': 'base_check',
                            'color': color,
                            'timestamp': current_time
                        })
                        
        except Exception as e:
            logging.error(f"Error adding economic activities: {e}")

    def _is_recently_visited(self, position, threshold=30.0):
        """Check if a position has been visited recently"""
        current_time = time.time()
        return any(
            self.calculate_distance(position, visit['position']) < 30 and
            current_time - visit['timestamp'] < threshold
            for visit in self.recent_visits
        )

    def _is_valid_point(self, point, mask):
        """Check if a point is within valid minimap bounds"""
        if mask is None:
            return True
        x, y = point
        return (0 <= x < mask.shape[1] and 
                0 <= y < mask.shape[0] and 
                mask[y, x] > 0)







    def calculate_military_importance(self, position, color, area, is_moving):
        """Enhanced military importance calculation that heavily favors units away from their home base"""
        # Get home base position
        own_base = self.base_monitor.get_tc_position(color)
        if not own_base:
            return min(1.0, area / 15.0)  # Fallback to simple area-based importance
            
        # Calculate distance from own base
        dist_from_home = self.calculate_distance(position, own_base)
        
        # Calculate base importance from unit size
        base_importance = min(1.0, area / 15.0)  * 1.2 # Adjusted for minimap scale
        
        # Heavy bonus for being away from home base
        # Start scaling up at 50 pixels, max bonus at 150 pixels
        distance_multiplier = min(4.0, max(1.0, dist_from_home / 25))
        
        # Movement is very important
        movement_multiplier = 4.0 if is_moving else 0.2
        
        # Check if in enemy territory
        enemy_color = 'Red' if color == 'Blue' else 'Blue'
        enemy_density = self.territory_tracker.get_color_density(enemy_color)
        territory_multiplier = 1.1
        
        if enemy_density is not None:
            x, y = position
            if x < enemy_density.shape[1] and y < enemy_density.shape[0]:
                territory_control = enemy_density[y, x]
                
                # Get average control in surrounding area
                area_size = 8
                x_start = max(0, x - area_size)
                x_end = min(enemy_density.shape[1], x + area_size)
                y_start = max(0, y - area_size)
                y_end = min(enemy_density.shape[0], y + area_size)
                area_control = np.mean(enemy_density[y_start:y_end, x_start:x_end])
                
                if territory_control > 0.5:  # Deep in enemy territory
                    territory_multiplier = 4.5  # Slightly higher
                elif territory_control > 0.2:  # Near enemy territory
                    territory_multiplier = 2.5
                
                # Additional boost if in contested area (both players have presence)
                if area_control > 0.3 and area_control < 0.7:
                    territory_multiplier *= 1.5
        
        # Static position penalty for large areas (likely buildings)
        if area > 20 and not is_moving:  # TC/Castle sized
            importance = base_importance * 0.1  # Heavy penalty for static large objects
        else:
            # Combine all factors with adjusted weights
            importance = (base_importance * 
                        distance_multiplier * 
                        movement_multiplier * 
                        territory_multiplier)
        
        logging.debug(f"Military importance calculation: base={base_importance:.2f}, " 
                    f"dist_mult={distance_multiplier:.2f}, move_mult={movement_multiplier:.2f}, "
                    f"terr_mult={territory_multiplier:.2f}, final={importance:.2f}")
        
        return importance


    def detect_building_type(self, contour, frame):
        """
        Determine if a contour matches TC or Castle template
        Returns: None, 'tc', or 'castle'
        """
        try:
            # Get contour region
            x, y, w, h = cv2.boundingRect(contour)
            roi = frame[y:y+h, x:x+w]
            
            # Convert ROI to grayscale
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            
            # Load and resize templates to match ROI size
            tc_template = cv2.imread('templates/town_center.png', cv2.IMREAD_GRAYSCALE)
            castle_template = cv2.imread('templates/castle.png', cv2.IMREAD_GRAYSCALE)
            
            if tc_template is not None and castle_template is not None:
                tc_template = cv2.resize(tc_template, (w, h))
                castle_template = cv2.resize(castle_template, (w, h))
                
                # Template matching
                tc_match = cv2.matchTemplate(gray_roi, tc_template, cv2.TM_CCOEFF_NORMED)
                castle_match = cv2.matchTemplate(gray_roi, castle_template, cv2.TM_CCOEFF_NORMED)
                
                tc_val = cv2.minMaxLoc(tc_match)[1]
                castle_val = cv2.minMaxLoc(castle_match)[1]
                
                # Threshold for matching
                if tc_val > 0.8:
                    return 'tc'
                elif castle_val > 0.8:
                    return 'castle'
                    
            return None
        except Exception as e:
            logging.error(f"Error in building detection: {e}")
            return None



    def find_all_buildings(self, military_map):
        """Find all building positions using template matching"""
        # Convert to grayscale
        gray = cv2.cvtColor(military_map, cv2.COLOR_BGR2GRAY)
        building_positions = []
        
        for template_path in ['templates/town_center.png', 'templates/castle.png']:
            try:
                template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                if template is not None:
                    # Use template matching
                    res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                    threshold = 0.8
                    locations = np.where(res >= threshold)
                    for pt in zip(*locations[::-1]):  # Switch columns and rows
                        building_positions.append((pt[0], pt[1]))
            except Exception as e:
                logging.error(f"Error loading template {template_path}: {e}")
                
        return building_positions

    def is_near_building(self, position, building_positions, threshold=15):
        """Check if a position is near any known building"""
        x, y = position
        for bx, by in building_positions:
            if abs(x - bx) < threshold and abs(y - by) < threshold:
                return True
        return False


    #If changing, make sure you're sure
    # Then make sure again
    # Then only adjust weights
    # THEN make logic changes
    def check_military_situation(self, curr_minimap, mask, military_mode=False):
        """
        Comprehensive military situation detector with improved combat detection,
        enhanced staleness tracking, and better static structure filtering.
        """
        try:
            military_activities = []
            military_data = {
                'activities': [],
                'high_density': False,
                'military_map': None
            }
            
            current_time = time.time()
            
            # Cleanup old tracking data
            if hasattr(self, 'position_visit_counts'):
                if not hasattr(self, 'last_position_cleanup'):
                    self.last_position_cleanup = current_time
                if current_time - self.last_position_cleanup > 30:  # Cleanup every 30 seconds
                    self.position_visit_counts.clear()
                    self.last_position_cleanup = current_time
            
            # Clean up old persistent position tracking
            if hasattr(self, 'position_first_seen'):
                for pos_key in list(self.position_first_seen.keys()):
                    if current_time - self.position_first_seen[pos_key] > 120:  # 2 minutes
                        del self.position_first_seen[pos_key]
                        del self.persistent_positions[pos_key]

            # Get military map with caching
            if not military_mode:
                if hasattr(self, '_cached_military_map') and \
                    current_time - self._last_military_cache < 5.0:  # 5-second cache
                    military_map = self._cached_military_map
                else:
                    with self.minimap_lock:
                        self.toggle_military_view()
                        time.sleep(0.2)
                        military_map = self.capture_minimap()
                        if military_map is None:
                            raise Exception("Failed to capture military map")
                        self._cached_military_map = military_map
                        self._last_military_cache = current_time
                        # Return to normal view
                        self.toggle_military_view()
                        self.toggle_military_view()
            else:
                military_map = curr_minimap

            military_data['military_map'] = military_map
            
            # Store positions for proximity checks
            player_positions = {'Blue': [], 'Red': []}
            
            # Adjusted thresholds for minimap scale
            is_early_game = not any(self.territory_tracker.castle_age_reached.values())
            area_threshold = 5  # Reduced to catch small military units
            
            for color in ['Blue', 'Red']:
                own_base = self.base_monitor.get_tc_position(color)
                density = self.territory_tracker.get_color_density(
                    military_map, color, self.player_colors_config, mask
                )
                
                if density is not None:
                    # Convert density to uint8 for OpenCV operations
                    density_img = (density * 255).astype(np.uint8)
                    
                    # Check overall military presence
                    total_military_presence = np.sum(density > 0.15)  # More sensitive
                    military_data['high_density'] = total_military_presence > 50
                    
                    # Find potential military units
                    significant = (density > 0.12).astype(np.uint8)  # Lower threshold
                    contours, _ = cv2.findContours(significant, cv2.RETR_EXTERNAL, 
                                            cv2.CHAIN_APPROX_SIMPLE)
                    
                    for contour in contours:
                        area = cv2.contourArea(contour)
                        if area < area_threshold:  # Skip extremely small noise
                            continue
                            
                        M = cv2.moments(contour)
                        if M["m00"] != 0:
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"])
                            
                            # Check for movement with smaller window
                            is_moving = False
                            movement_score = 0
                            if hasattr(self, 'last_military_map') and self.last_military_map is not None:
                                prev_region = cv2.getRectSubPix(
                                    self.last_military_map, 
                                    (7, 7),  # Small window for precise movement detection
                                    (cx, cy)
                                )
                                curr_region = cv2.getRectSubPix(
                                    military_map,
                                    (7, 7),
                                    (cx, cy)
                                )
                                movement_score = np.mean(cv2.absdiff(prev_region, curr_region))
                                is_moving = movement_score > 0.08  # Sensitive to small movements
                            
                            # Track position persistence
                            pos_key = f"{cx},{cy}"
                            if not hasattr(self, 'position_first_seen'):
                                self.position_first_seen = {}
                                self.persistent_positions = {}
                                
                            if pos_key not in self.position_first_seen:
                                self.position_first_seen[pos_key] = current_time
                                self.persistent_positions[pos_key] = 0
                            elif not is_moving and movement_score < 0.05:
                                self.persistent_positions[pos_key] = self.persistent_positions.get(pos_key, 0) + 1
                            
                            # Skip if this is likely a building (TC/Castle)
                            if area > 20 and not is_moving:  # Large static area
                                # Check if it's very solid (like a building icon)
                                y_start = max(0, cy - 2)
                                y_end = min(density.shape[0], cy + 3)
                                x_start = max(0, cx - 2)
                                x_end = min(density.shape[1], cx + 3)
                                region = density[y_start:y_end, x_start:x_end]
                                if np.mean(region) > 0.8:  # Very solid/filled shape
                                    continue
                            
                            # Check consecutive static views
                            consecutive_static_views = 0
                            if hasattr(self, 'position_visit_counts'):
                                consecutive_static_views = self.position_visit_counts.get(pos_key, 0)
                                
                            if consecutive_static_views > 2 and not is_moving:
                                # Require more significant movement for frequently viewed positions
                                required_movement = 0.08 + (consecutive_static_views * 0.02)
                                if movement_score < required_movement:
                                    continue
                            
                            # Calculate distance from base
                            dist_from_home = 1000  # Default to large distance
                            if own_base:
                                dist_from_home = self.calculate_distance((cx, cy), own_base)
                            
                            # Calculate base importance
                            importance = 0.5  # Base importance
                            
                            # Movement is critical - much higher importance for moving units
                            if is_moving:
                                importance *= 4.0
                            
                            # Distance from base importance
                            if dist_from_home > 30:  # Significantly away from base
                                importance *= 3.0
                            elif dist_from_home > 20:  # Moderately away
                                importance *= 2.0
                                
                            # Heavily penalize large static areas (likely buildings)
                            if area > 50 and movement_score < 0.05:
                                importance *= 0.1
                            
                            # Early game bonus
                            if is_early_game:
                                importance *= 1.5
                            
                            # Enhanced staleness penalty based on movement and persistence
                            if hasattr(self, 'position_visit_counts'):
                                visit_count = self.position_visit_counts.get(pos_key, 0)
                                if visit_count > 0:
                                    if not is_moving and movement_score < 0.05:
                                        # Much harsher decay for static objects
                                        importance *= max(0.15, 0.5 ** visit_count)
                                    else:
                                        # Normal decay for moving units
                                        importance *= max(0.3, 0.7 ** visit_count)
                            
                            # Apply persistence penalty
                            if self.persistent_positions.get(pos_key, 0) > 5:
                                time_static = current_time - self.position_first_seen[pos_key]
                                if time_static > 30:  # If static for more than 30 seconds
                                    importance *= 0.3
                            
                            # Create activity
                            activity = {
                                'position': (cx, cy),
                                'area': area,
                                'color': color,
                                'importance': importance,
                                'type': 'field_military' if dist_from_home > 20 else 'military_units',
                                'is_moving': is_moving,
                                'movement_score': movement_score,
                                'high_density': military_data['high_density'],
                                'timestamp': current_time
                            }
                            
                            # Check position ratio relative to enemy base
                            enemy_color = 'Red' if color == 'Blue' else 'Blue'
                            enemy_base = self.base_monitor.get_tc_position(enemy_color)
                            
                            if enemy_base and own_base:
                                dist_to_enemy_base = self.calculate_distance((cx, cy), enemy_base)
                                total_dist = self.calculate_distance(own_base, enemy_base)
                                
                                if total_dist > 0:  # Avoid division by zero
                                    position_ratio = dist_to_enemy_base / total_dist
                                    
                                    # Modify importance based on position ratio
                                    if position_ratio > 0.8:
                                        activity['importance'] *= 0.2  # Heavy penalty for very back positions
                                    elif position_ratio > 0.6:
                                        activity['importance'] *= 0.5  # Moderate penalty for back positions
                                    elif position_ratio < 0.5:
                                        activity['importance'] *= 1.5  # Bonus for forward positions
                            
                            # Store position and add to activities
                            player_positions[color].append((cx, cy))
                            military_activities.append(activity)
                            
                            # Track this position for future staleness calculation
                            if not hasattr(self, 'position_visit_counts'):
                                self.position_visit_counts = {}
                            self.position_visit_counts[pos_key] = self.position_visit_counts.get(pos_key, 0) + 1

            # Store current military map for next comparison
            self.last_military_map = military_map.copy()

            # Check for combat with increased sensitivity
            for activity in military_activities:
                enemy_color = 'Red' if activity['color'] == 'Blue' else 'Blue'
                pos = activity['position']
                
                for enemy_pos in player_positions[enemy_color]:
                    dist = self.calculate_distance(pos, enemy_pos)
                    if dist < 35:  # Increased from 25 - more sensitive to nearby units
                        activity['type'] = 'major_combat'
                        activity['importance'] *= 4.5  # Increased from 4.0 for stronger combat priority
                        activity['view_duration'] = self.combat_view_duration
                        break
            
            military_data['activities'] = self._deduplicate_activities(
                military_activities, proximity_threshold=12  # Smaller radius
            )
            return military_data
                
        except Exception as e:
            logging.error(f"Error in check_military_situation: {e}")
            return {'activities': [], 'high_density': False, 'military_map': None}

    def _deduplicate_activities(self, military_activities, proximity_threshold=12):
        """Enhanced deduplication that preserves more distinct military movements"""
        if not military_activities:
            return []
            
        # First sort by importance
        military_activities.sort(key=lambda x: x['importance'], reverse=True)
        
        # Keep track of positions per player
        player_positions = {'Blue': [], 'Red': []}
        unique_activities = []
        
        for activity in military_activities:
            pos = activity['position']
            color = activity['color']
            
            # Check distance from same player's activities
            is_unique = True
            for prev_pos in player_positions[color]:
                if self.calculate_distance(pos, prev_pos) < proximity_threshold:
                    is_unique = False
                    break
            
            if is_unique:
                unique_activities.append(activity)
                player_positions[color].append(pos)
                
                # Make sure we don't queue too many activities
                if len(player_positions[color]) >= 3:  # Keep up to 3 activities per player
                    continue
        
        return unique_activities


    def determine_closest_base(self, position):
        """Determine which player's base is closest to the given position"""
        closest_color = None
        min_distance = float('inf')
        
        for color in self.active_colors:
            base_pos = self.base_monitor.get_tc_position(color)
            if base_pos:
                distance = self.calculate_distance(position, base_pos)
                if distance < min_distance:
                    min_distance = distance
                    closest_color = color
        
        return closest_color


    def detect_building_under_attack(self, military_map):
        """
        Detect white flashing of buildings under attack in military view.
        Returns list of positions where buildings are being attacked.
        """
        try:
            # Convert to HSV to detect white flashing
            hsv = cv2.cvtColor(military_map, cv2.COLOR_BGR2HSV)
            
            # White has very low saturation and high value
            white_mask = cv2.inRange(hsv, 
                np.array([0, 0, 200], dtype=np.uint8),  # Very low saturation, high value
                np.array([180, 30, 255], dtype=np.uint8)
            )
            
            # Find white flashing areas
            contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            attack_positions = []
            for contour in contours:
                area = cv2.contourArea(contour)
                # Buildings have a specific size range when flashing
                if 150 < area < 300:  # Adjust these thresholds as needed
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        attack_positions.append((cx, cy))
            
            return attack_positions
        except Exception as e:
            logging.error(f"Error detecting building attacks: {e}")
            return []

    def detect_large_military_presence(self, minimap_image, minimap_mask):
        """
        Detect large concentrations of military units using the military-only view.
        Returns positions and sizes of significant military gatherings.
        """
        try:
            results = []
            
            with self.minimap_lock:
                # Switch to military view
                self.toggle_military_view()
                time.sleep(0.2)
                
                military_map = self.capture_minimap()
                if military_map is None:
                    self.toggle_military_view()  # First toggle back
                    self.toggle_military_view()  # Second toggle back
                    return []
                    
                for color in ['Blue', 'Red']:
                    density = self.territory_tracker.get_color_density(
                        military_map, 
                        color, 
                        self.player_colors_config, 
                        minimap_mask
                    )
                    
                    if density is not None:
                        significant = (density > 0.25).astype(np.uint8)
                        contours, _ = cv2.findContours(
                            significant, 
                            cv2.RETR_EXTERNAL, 
                            cv2.CHAIN_APPROX_SIMPLE
                        )
                        
                        for contour in contours:
                            area = cv2.contourArea(contour)
                            if area > 100:  # Adjust this threshold based on your screenshot
                                M = cv2.moments(contour)
                                if M["m00"] != 0:
                                    cx = int(M["m10"] / M["m00"])
                                    cy = int(M["m01"] / M["m00"])
                                    
                                    importance = min(1.0, area / 200)
                                    
                                    results.append({
                                        'position': (cx, cy),
                                        'area': area,
                                        'color': color,
                                        'importance': importance,
                                        'type': 'military_mass'
                                    })
                
                # Return to normal view
                self.toggle_military_view()  # First toggle back
                self.toggle_military_view()  # Second toggle back
                
            return sorted(results, key=lambda x: x['importance'], reverse=True)
            
        except Exception as e:
            logging.error(f"Error detecting military presence: {e}")
            # Make sure we toggle back even if there's an error
            try:
                with self.minimap_lock:
                    self.toggle_military_view()  # First toggle back
                    self.toggle_military_view()  # Second toggle back
            except:
                pass
            return []

    def run_spectator(self):
        """Main spectator loop."""
        logging.info("Starting spectator")
        try:
            # Trigger betting start
            if self.betting_bridge:
                self.betting_bridge.on_game_start()
                
            while True:
                iteration_result = self.run_spectator_iteration()
                if not iteration_result:  # Game has ended
                    # Get winner before cleanup
                    winner = self.determine_winner()
                    if winner and self.betting_bridge:
                        self.betting_bridge.on_game_end(winner)
                    logging.info("Game has ended, exiting spectator loop")
                    return True  # Clean exit - game ended normally
                time.sleep(0.5)  # Prevent excessive CPU usage
                        
        except KeyboardInterrupt:
            logging.info("Spectator stopped by user")
            return False
        except Exception as e:
            logging.error(f"Error in spectator loop: {e}")
            return False

    def run_spectator_iteration(self):
        """Run a single iteration of the spectator logic."""
        try:
            if self.detect_game_over():
                winner = self.determine_winner()
                if winner and hasattr(self, 'betting_bridge') and self.betting_bridge:
                    self.betting_bridge.on_game_end(winner)
                logging.info(f"Game ended with winner: {winner}")
                return False

            current_time = time.time()
            curr_minimap, mask = self.get_minimap_state()
            if curr_minimap is None or mask is None:
                return True

            self.current_mask = mask
            self.last_minimap = curr_minimap
            
            # Initialize view tracking if needed
            if not hasattr(self, 'current_view_position'):
                self.current_view_position = None
                self.time_at_position = 0
                self.max_view_time = 10.0
                self.last_positions = []
                self.forced_view_until = 0
                self.combat_perspective = 'defender'
                self.last_perspective_switch = 0
                self.perspective_switch_interval = 15.0
                self.last_military_view = 0
                self.last_switch_time = current_time  # Add explicit initialization

            # Get comprehensive military situation once per iteration
            military_data = self.check_military_situation(curr_minimap, mask, military_mode=False)
            military_activities = military_data['activities']
            high_density = military_data['high_density']
                
            # Handle high density military situations first
            if high_density and current_time - self.last_military_view > 15.0:
                large_military = [act for act in military_activities if act['area'] > 100]
                if large_military:
                    # First check if there are any opposing forces nearby
                    potential_conflicts = []
                    for act in large_military:
                        enemy_color = 'Red' if act['color'] == 'Blue' else 'Blue'
                        enemy_activities = [a for a in military_activities if a['color'] == enemy_color]
                        
                        # Check for any nearby enemy units
                        for enemy_act in enemy_activities:
                            dist = self.calculate_distance(act['position'], enemy_act['position'])
                            if dist < 35:  # 50 pixel radius for potential conflict
                                act['has_enemy_nearby'] = True
                                potential_conflicts.append(act)
                                break

                    if potential_conflicts:  # Only force view if there's potential conflict
                        # Sort by importance to pick the most significant conflict
                        act = max(potential_conflicts, key=lambda x: x['importance'])
                        if act.get('type') == 'major_combat':
                            self.handle_major_combat(act['position'])
                        else:
                            self.click_minimap(act['position'][0], act['position'][1], mask)
                        self.last_military_view = current_time
                        self.last_switch_time = current_time
                        logging.info(f"Forced military check due to high density situation with nearby opposition")
                        return True

            # Add base checks to viewing queue instead of forcing them
            if current_time - self.last_military_view > 5.0:
                for color in ['Blue', 'Red']:
                    if self.base_monitor.should_check_base(color, current_time):
                        base_pos = self.base_monitor.get_tc_position(color)
                        if base_pos:
                            self.viewing_queue.add_zone({
                                'position': base_pos,
                                'importance': 0.8,
                                'type': 'base_check',
                                'color': color,
                                'timestamp': current_time
                            })
                            logging.info(f"Added base check for {color} to viewing queue")

            # Update territory understanding
            self.territory_tracker.update(curr_minimap, self.player_colors_config, 
                                        self.active_colors, mask)

            # Handle view duration
            current_activity = self.viewing_queue.get_current_view()
            if current_activity and current_activity.get('type') == 'combat_zone':
                current_view_duration = self.combat_view_duration
            else:
                current_view_duration = random.uniform(self.min_view_duration, self.max_view_duration)

            if current_time < self.forced_view_until:
                return True

            # Determine if view switch is needed
            should_switch = False
            time_since_last_switch = current_time - self.last_switch_time

            # Force a switch if we've been in one place too long
            if time_since_last_switch >= max(self.max_view_time, current_view_duration + 2.0):
                should_switch = True
                logging.info("Forcing view switch due to timeout")
            elif self.current_view_position:
                time_spent = current_time - self.time_at_position
                pos_key = f"{self.current_view_position[0]},{self.current_view_position[1]}"
                view_count = self.viewing_queue.view_counts.get(pos_key, 0)
                
                if (time_spent > self.max_view_time or 
                    (view_count > self.viewing_queue.staleness_threshold and 
                    not current_activity.get('is_moving', False))):
                    should_switch = True

            # Handle view switching
            if should_switch or (time_since_last_switch >= current_view_duration):
                # Use the already collected military data
                activities = self.decide_next_view(military_data['military_map'], mask, military_mode=True)
                
                if activities:
                    next_activity = activities[0]
                    pos = next_activity['position']
                    
                    if self.is_point_in_minimap(pos[0], pos[1], mask):
                        # Handle different activity types
                        if next_activity.get('type') == 'major_combat':
                            # Verify combat before doing drag-follow
                            if self.verify_active_combat(curr_minimap, mask, pos):
                                self.handle_major_combat(pos)
                            else:
                                self.click_minimap(pos[0], pos[1], mask)
                        elif next_activity.get('type') in ['base_exploration', 'eco_activity']:
                            self.click_minimap(pos[0], pos[1], mask)
                            logging.info(f"Exploring {next_activity.get('type')} for {next_activity.get('color', 'unknown')}")
                        elif next_activity.get('type') == 'combat_zone':
                            if self.combat_perspective == 'defender':
                                defender_base = self.base_monitor.get_tc_position(next_activity.get('defender'))
                                if defender_base:
                                    pos = self._adjust_combat_position(pos, defender_base, 5)
                            self.click_minimap(pos[0], pos[1], mask)
                        elif next_activity.get('type') == 'territory_breach':
                            # Enhanced handling for territory breaches
                            enemy_color = 'Red' if next_activity['color'] == 'Blue' else 'Blue'
                            enemy_base = self.base_monitor.get_tc_position(enemy_color)
                            if enemy_base:
                                # Adjust view position to better show the breach context
                                pos = self._adjust_combat_position(pos, enemy_base, 5)
                            self.click_minimap(pos[0], pos[1], mask)
                        else:
                            self.click_minimap(pos[0], pos[1], mask)
                        
                        self.last_switch_time = current_time
                        self._update_view_position(pos, current_time)
                        
                        logging.info(f"Switched to {next_activity.get('color', 'unknown')} "
                                f"{next_activity.get('type', 'activity')} "
                                f"(area: {next_activity.get('area', 0):.1f}, "
                                f"importance: {next_activity.get('importance', 1.0):.1f}, "
                                f"moving: {next_activity.get('is_moving', False)})")

            # Handle combat perspective switching with proper view updates
            if current_time - self.last_perspective_switch >= self.perspective_switch_interval:
                old_perspective = self.combat_perspective
                self.combat_perspective = 'attacker' if self.combat_perspective == 'defender' else 'defender'
                self.last_perspective_switch = current_time
                logging.info(f"Switched combat perspective to {self.combat_perspective}")
                
                # Force a view update if we're watching combat
                current_activity = self.viewing_queue.get_current_view()
                if (current_activity and 
                    current_activity.get('type') in ['major_combat', 'combat_zone', 'territory_breach']):
                    activities = self.decide_next_view(curr_minimap, mask, military_mode=True)
                    if activities and activities[0].get('type') in ['major_combat', 'combat_zone', 'territory_breach']:
                        base_color = activities[0].get('defender' if self.combat_perspective == 'defender' else 'color')
                        base_pos = self.base_monitor.get_tc_position(base_color) if base_color else None
                        pos = activities[0]['position']
                        if base_pos:
                            pos = self._adjust_combat_position(pos, base_pos, 5)
                        self.click_minimap(pos[0], pos[1], mask)
                        logging.info(f"Updated combat view for new {self.combat_perspective} perspective")

            return True

        except Exception as e:
            logging.error(f"Error in spectator iteration: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return True
        
        
    def _adjust_combat_position(self, pos, base_pos, offset):
        """Adjust viewing position for combat based on defender's base position."""
        dx = base_pos[0] - pos[0]
        dy = base_pos[1] - pos[1]
        distance = np.sqrt(dx*dx + dy*dy)
        
        if distance > 0:
            return (
                int(pos[0] + (dx/distance) * offset),
                int(pos[1] + (dy/distance) * offset)
            )
        return pos



    def capture_minimap(self):
        """Captures the minimap area of the screen."""
        try:
            x1 = self.minimap_x
            y1 = self.minimap_y
            x2 = self.minimap_x + self.minimap_width
            y2 = self.minimap_y + self.minimap_height
            
            screenshot = None 
            frame = None 
            try:
                screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
                frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                return frame
            finally:
                #explicit cleanup
                if screenshot:
                    screenshot.close()
                    #let frame be garbage collected since its being returned
            
            if self.debug_mode:
                cv2.imwrite('debug_raw_minimap.png', frame)
                
        except Exception as e:
            logging.error(f"Error capturing minimap: {e}")
            return None

    def toggle_military_view(self):
        """Toggle the military-only view state"""
        pyautogui.hotkey('alt', 'm')
        time.sleep(0.1)  # Small delay to ensure view changes

    def detect_military_activity(self):
        """Detect military activity with enhanced proximity scoring"""
        try:
            self.minimap_lock.acquire()
            
            # Switch to military view
            self.toggle_military_view()
            time.sleep(0.2)
            
            military_map = self.capture_minimap()
            if military_map is not None:
                # Get separate activity zones for each player
                blue_military = self.detect_activity_zones(military_map, self.current_mask, specific_color='Blue')
                red_military = self.detect_activity_zones(military_map, self.current_mask, specific_color='Red')
                
                combined_zones = []
                proximity_radius = 40  # Radius to check for nearby enemy units
                
                # Check each blue zone for nearby red zones and vice versa
                for blue_zone in blue_military:
                    nearby_red = [red for red in red_military if 
                                self.calculate_distance(blue_zone['position'], red['position']) < proximity_radius]
                    if nearby_red:
                        # Boost importance based on proximity
                        blue_zone['importance'] *= 1.4  # Higher boost for military convergence
                        blue_zone['type'] = 'military_convergence'
                        combined_zones.append(blue_zone)
                    else:
                        combined_zones.append(blue_zone)
                
                # Add remaining red zones
                for red_zone in red_military:
                    if not any(self.calculate_distance(red_zone['position'], z['position']) < proximity_radius 
                            for z in combined_zones):
                        combined_zones.append(red_zone)
                
                military_activity = sorted(combined_zones, key=lambda x: x['importance'], reverse=True)
            else:
                military_activity = []
                
            # Return to normal view (two toggles needed)
            self.toggle_military_view()
            self.toggle_military_view()
            time.sleep(0.2)
            
            return military_activity
        finally:
            self.minimap_lock.release()


    def detect_game_over(self):
        """Detect game end by monitoring resource numbers for changes."""
        try:
            current_time = time.time()
            
            if not hasattr(self, 'game_start_time'):
                self.game_start_time = current_time
                return False

            if current_time - self.game_start_time < 180: 
                return False

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
            
            # Keep only last 5 snapshots (32 seconds worth)
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
                    
                    winner = self.determine_winner()
                    if winner:
                        logging.info(f"Winner detected: {winner}")
                        if hasattr(self, 'betting_bridge') and self.betting_bridge:
                            self.betting_bridge.on_game_end(winner)
                    return True
                                
            return False

        except Exception as e:
            logging.error(f"Error in game over detection: {e}")
            return False
    
    def determine_winner(self):
        """Detect winner by analyzing victory screen text"""
        try:
            victory_box = (
                800,   # X start
                120,   # Y start 
                1120,  # X end
                300    # Y end
            )
            
            screenshot = ImageGrab.grab(bbox=victory_box)
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)
            
            blue_text = cv2.inRange(frame, 
                np.array([100, 150, 200]), 
                np.array([140, 255, 255])
            )
            
            red_text = cv2.inRange(frame, 
                np.array([0, 150, 200]), 
                np.array([10, 255, 255])
            )
            
            if self.debug_mode:
                cv2.imwrite('debug_final_victory.png', 
                        cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR))
            
            blue_pixels = np.sum(blue_text > 0)
            red_pixels = np.sum(red_text > 0)
            
            threshold = 100  # Minimum pixels to consider valid
            
            if blue_pixels > threshold and blue_pixels > red_pixels:
                return 'Blue'
            elif red_pixels > threshold and red_pixels > blue_pixels:
                return 'Red'
                
            return None
            
        except Exception as e:
            logging.error(f"Error determining winner: {e}")
            return None


    def detect_activity_zones(self, minimap_image, minimap_mask, specific_color=None):
        """Detect activity zones with mask support."""
        activity_zones = []
        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)

        # If specific_color is provided, only check that color
        colors_to_check = [specific_color] if specific_color else self.active_colors

        for color in colors_to_check:
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
                            importance = min(area / 120, 5)
                            activity_zones.append({
                                'position': (cx, cy),
                                'area': area,
                                'color': color,
                                'importance': importance,
                                'timestamp': time.time()
                            })

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
        self.current_view_position = position
        self.time_at_position = time
        self.last_positions.append(position)
        if len(self.last_positions) > 5:
            self.last_positions.pop(0)
            
        # Reset view counts for areas we've moved away from
        self.viewing_queue.reset_view_count(position)
        
        # Update visit tracking
        current_view = self.viewing_queue.get_current_view()
        if current_view:
            activity_type = 'military' if current_view['type'] in ['military_units', 'combat_zone'] else 'economy'
            self.last_visit_times[current_view['color']][activity_type] = time


    def _get_military_map(self):
        """Get military map with caching"""
        current_time = time.time()
        
        if hasattr(self, '_cached_military_map'):
            if current_time - self._last_military_cache > 5.0:
                del self._cached_military_map
                del self._last_military_cache
                
        if hasattr(self, '_cached_military_map'):  # Cache valid for 5 seconds
            return self._cached_military_map
        
        with self.minimap_lock:
            self.toggle_military_view()
            time.sleep(0.2)
            military_map = self.capture_minimap()
            self.toggle_military_view()
            time.sleep(0.2)
            self.toggle_military_view()
            
            if military_map is not None:
                self._cached_military_map = military_map
                self._last_military_cache = current_time
                
            return military_map


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
            vertical_shift = int(height * 0.05)
            top_adjustment = 9
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
    def __init__(self, building_params=None):
        """Initialize the territory tracker with updated parameters."""
        self.territories = {}
        self.heat_map = None
        self.last_update = 0
        self.update_interval = 1.0  # Reduced for more frequent updates
        self.last_density_map = None
        self.prev_frame = {}
        
        # Detection thresholds
        self.RAID_THRESHOLD = 0.3
        self.scout_detection_threshold = 0.05
        self.early_game_multiplier = 1.8
        self.base_detection_threshold = 0.20
        
        # Parameters for clustering
        self.cluster_distance = 25
        self.detection_radius = 30
        
        # Building parameters from config (or defaults)
        if building_params:
            self.BUILDING_ICON_MIN_AREA = building_params.get('min_area', 15)
            self.BUILDING_ICON_MAX_AREA = building_params.get('max_area', 50)
            self.BUILDING_ICON_MIN_CIRCULARITY = building_params.get('min_circularity', 0.6)
        else:
            self.BUILDING_ICON_MIN_AREA = 15
            self.BUILDING_ICON_MAX_AREA = 50
            self.BUILDING_ICON_MIN_CIRCULARITY = 0.6
        
        # Raid tracking
        self.raid_history = {}
        self.staleness_threshold = 8.0
        self.min_movement_threshold = 15
        self.movement_check_interval = 2.0

        # Movement detection weights
        self.movement_weight = 0.4
        self.static_weight = 0.6

        self.castle_age_reached = {
            'Blue': False,
            'Red': False
        }

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
        

        # Clear old prev_frames periodically
        if len(self.prev_frame) > 2:  # Keep only recent frames
            old_keys = list(self.prev_frame.keys())[:-2]  # Keep last 2
            for key in old_keys:
                del self.prev_frame[key]

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



    def get_territory_mask(self, color):
        """
        Get a binary mask showing territory controlled by a specific color.
        Returns a numpy array where 1 indicates controlled territory.
        """
        try:
            if color not in self.territories:
                return None
                
            if not self.territories[color]['main_base']:
                return None
                
            # Create empty mask
            territory_mask = np.zeros_like(self.heat_map) if self.heat_map is not None else None
            if territory_mask is None:
                return None
                
            # Get base position for reference
            base_x, base_y = self.territories[color]['main_base']['position']
            
            # Create influence map around buildings
            if 'building_positions' in self.territories[color]:
                for x, y in self.territories[color]['building_positions']:
                    # Create gaussian influence around each building
                    y_indices, x_indices = np.ogrid[-y:territory_mask.shape[0]-y, -x:territory_mask.shape[1]-x]
                    radius = 20  # Adjusted for minimap scale
                    mask = x_indices*x_indices + y_indices*y_indices <= radius*radius
                    territory_mask[mask] += 1
            
            # Add base influence
            y_indices, x_indices = np.ogrid[-base_y:territory_mask.shape[0]-base_y, -base_x:territory_mask.shape[1]-base_x]
            base_radius = 30  # Larger radius for main base
            base_mask = x_indices*x_indices + y_indices*y_indices <= base_radius*base_radius
            territory_mask[base_mask] += 2  # Higher weight for base area
            
            # Normalize to [0, 1]
            if np.max(territory_mask) > 0:
                territory_mask = territory_mask / np.max(territory_mask)
            
            return territory_mask

        except Exception as e:
            logging.error(f"Error generating territory mask: {e}")
            return None


    def detect_raids(self, minimap_image, hsv_ranges, minimap_mask=None):
        """Detect raids with enhanced movement detection and proper minimap scaling"""
        try:
            raids = []
            current_time = time.time()
            
            if not hasattr(self, 'prev_frame'):
                self.prev_frame = {}
            
            for attacker in self.territories:
                for defender in self.territories:
                    if attacker != defender:
                        attacker_units = self.get_color_density(minimap_image, attacker, hsv_ranges, minimap_mask)
                        defender_density = self.get_color_density(minimap_image, defender, hsv_ranges, minimap_mask)
                        
                        if attacker_units is None:
                            continue
                        
                        # Get movement map for attacker units
                        movement_map = None
                        if attacker in self.prev_frame and self.prev_frame[attacker] is not None:
                            prev_density = self.prev_frame[attacker]
                            if prev_density.shape == attacker_units.shape:
                                movement_map = cv2.absdiff(attacker_units, prev_density)
                        
                        # Store current frame for next comparison
                        self.prev_frame[attacker] = attacker_units.copy()
                        
                        # Look for raiding conditions
                        defender_base = self.territories[defender]['main_base']
                        if defender_base:
                            base_x, base_y = defender_base['position']
                            scan_radius = 40  # Reduced from 80 for minimap scale
                            
                            y_start = max(0, base_y - scan_radius)
                            y_end = min(attacker_units.shape[0], base_y + scan_radius)
                            x_start = max(0, base_x - scan_radius)
                            x_end = min(attacker_units.shape[1], base_x + scan_radius)
                            
                            region = attacker_units[y_start:y_end, x_start:x_end]
                            movement = None if movement_map is None else movement_map[y_start:y_end, x_start:x_end]
                            
                            # Look for significant unit presence
                            significant_presence = region > self.scout_detection_threshold
                            if np.any(significant_presence):
                                y_indices, x_indices = np.where(significant_presence)
                                
                                for y, x in zip(y_indices, x_indices):
                                    actual_x = x + x_start
                                    actual_y = y + y_start
                                    
                                    # Skip if outside minimap
                                    if minimap_mask is not None and not minimap_mask[actual_y, actual_x]:
                                        continue
                                    
                                    # Skip if no movement
                                    if movement is not None:
                                        movement_score = movement[y, x]
                                        if movement_score < 0.05:  # Skip stationary units
                                            continue
                                    
                                    # Calculate distance from defender's base
                                    dist_to_base = np.sqrt((actual_x - base_x)**2 + (actual_y - base_y)**2)
                                    
                                    # Calculate importance with movement priority
                                    local_area = attacker_units[
                                        max(0, actual_y - 15):min(attacker_units.shape[0], actual_y + 15),
                                        max(0, actual_x - 15):min(attacker_units.shape[1], actual_x + 15)
                                    ]
                                    
                                    unit_mass = np.sum(local_area > self.scout_detection_threshold)
                                    size_score = min(0.6, unit_mass / 15)  # Reduced from 30
                                    
                                    # Movement score (highest priority)
                                    movement_score = 0
                                    if movement is not None:
                                        local_movement = movement[
                                            max(0, y - 15):min(movement.shape[0], y + 15),
                                            max(0, x - 15):min(movement.shape[1], x + 15)
                                        ]
                                        movement_score = min(0.9, np.mean(local_movement) * 4.0)  # Increased multiplier
                                    
                                    # Distance factor (closer to enemy base = higher importance)
                                    distance_factor = min(1.0, dist_to_base / 50)  # Reduced from 200
                                    
                                    # Calculate final importance
                                    importance = (
                                        movement_score * 0.7 +     # Movement highest priority
                                        size_score * 0.4 +         # Unit mass matters but less
                                        (1.0 - distance_factor) * 0.4  # Distance from base
                                    )
                                    
                                    # Extra boost for being very close to enemy base
                                    if dist_to_base < 25:  # Was 100
                                        importance *= 2.0
                                    
                                    # Apply bonus for significant movement
                                    if movement_score > 0.3:
                                        importance *= 1.5
                                    
                                    if importance > self.RAID_THRESHOLD:
                                        raids.append({
                                            'position': (actual_x, actual_y),
                                            'attacker': attacker,
                                            'defender': defender,
                                            'importance': importance,
                                            'raid_key': f"{attacker}-{defender}-{actual_x}-{actual_y}",
                                            'is_moving': movement_score > 0.1 if movement is not None else False,
                                            'type': 'raid'
                                        })

            # Clean up old raid history
            self.cleanup_raid_history(current_time)
            
            # Cluster similar raids
            return self.cluster_raids(raids)
                
        except Exception as e:
            logging.error(f"Error in detect_raids: {e}")
            return []
        

    def adjust_importance_for_movement(self, raid_key, current_pos, base_importance, current_time):
        """Adjust raid importance with faster decay for static positions"""
        if raid_key not in self.raid_history:
            self.raid_history[raid_key] = {
                'positions': [current_pos],
                'last_update': current_time,
                'last_movement': current_time,
                'static_time': 0
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
        
        # Update position history if significant movement
        if distance > self.min_movement_threshold:
            history['positions'].append(current_pos)
            history['last_movement'] = current_time
            history['static_time'] = 0
            time_since_movement = 0
            
            if len(history['positions']) > 5:
                history['positions'].pop(0)
        else:
            history['static_time'] += current_time - history['last_update'] * 1.2
        
        history['last_update'] = current_time
        
        # Enhanced staleness calculation
        static_penalty = min(0.6, history['static_time'] / 8.0)  # Faster decay for static positions
        movement_bonus = min(0.5, distance / 15.0)  # Bonus for movement
        
        staleness_factor = max(0.15, 
            1.0 - (time_since_movement / self.staleness_threshold) - static_penalty + movement_bonus
        )
        
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

    def calculate_raid_importance(self, position, attacker_density, defender_density, movement_map=None, radius=30):
        """Calculate raid importance with enhanced movement priority"""
        x, y = position
        local_area = self.get_local_area(attacker_density, x, y, radius)
        
        # Base importance from unit presence
        unit_mass = np.sum(local_area > self.scout_detection_threshold)
        size_score = min(0.6, unit_mass / 30)  # Lower base importance
        
        # Movement score (highest priority)
        movement_score = 0
        if movement_map is not None:
            movement_local = self.get_local_area(movement_map, x, y, radius)
            movement = np.mean(movement_local)
            movement_score = min(0.9, movement * 3.0)  # Higher cap for movement
        
        # Distance from defender's base (for raid validation)
        defender_base = self.territories[self.current_defender]['main_base']
        if defender_base:
            dist_to_base = self.calculate_distance(position, defender_base['position'])
            distance_factor = min(1.0, dist_to_base / 200)  # Further = less likely to be a raid
        else:
            distance_factor = 0.5
        
        # Calculate final importance
        importance = (
            movement_score * 0.5 +  # Movement is highest priority
            size_score * 0.3 +      # Unit mass matters but less
            (1.0 - distance_factor) * 0.2  # Distance from base
        )
        
        return importance * (1.5 if movement_score > 0.3 else 1.0)  # Bonus for significant movement
    

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

    def update_territory_understanding(self, minimap_image, hsv_ranges, minimap_mask=None):
        """Build comprehensive territory understanding over time."""
        territory_map = np.zeros_like(minimap_image[:,:,0], dtype=np.float32)
        
        for color in self.territories:
            # Get current density
            density = self.get_color_density(minimap_image, color, hsv_ranges, minimap_mask)
            
            # Track building positions (more stable than units)
            building_mask = cv2.inRange(
                cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV),
                np.array(hsv_ranges[color]['icon']['lower'], dtype=np.uint8),
                np.array(hsv_ranges[color]['icon']['upper'], dtype=np.uint8)
            )
            
            if 'building_positions' not in self.territories[color]:
                self.territories[color]['building_positions'] = []
            
            # Find building contours
            contours, _ = cv2.findContours(building_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                if cv2.contourArea(contour) > self.BUILDING_ICON_MIN_AREA:
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        self.territories[color]['building_positions'].append((cx, cy))
            
            # Create territory influence map
            if self.territories[color]['building_positions']:
                for x, y in self.territories[color]['building_positions']:
                    # Add gaussian influence around each building
                    influence_radius = 20  # Was 40
                    y_coords, x_coords = np.ogrid[-y:territory_map.shape[0]-y, -x:territory_map.shape[1]-x]
                    mask = x_coords*x_coords + y_coords*y_coords <= influence_radius*influence_radius
                    territory_map[mask] += 1
        
        # Normalize and store
        if np.max(territory_map) > 0:
            territory_map = territory_map / np.max(territory_map)
        self.territory_map = territory_map
        
        # Enhanced visualization
        debug_img = minimap_image.copy()
        for color in self.territories:
            if self.territories[color]['building_positions']:
                color_val = {"Blue": (255, 0, 0), "Red": (0, 0, 255)}[color]
                
                # Draw building positions
                for x, y in self.territories[color]['building_positions']:
                    cv2.circle(debug_img, (x, y), 2, color_val, -1)
                
                # Draw territory boundaries
                territory_mask = (territory_map > 0.3).astype(np.uint8)
                contours, _ = cv2.findContours(territory_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(debug_img, contours, -1, color_val, 1)
        
        cv2.imwrite('debug_territory_understanding.png', debug_img)
        
        # Also save territory heatmap
        territory_heat = (territory_map * 255).astype(np.uint8)
        territory_heat = cv2.applyColorMap(territory_heat, cv2.COLORMAP_JET)
        cv2.imwrite('debug_territory_heat.png', territory_heat)

