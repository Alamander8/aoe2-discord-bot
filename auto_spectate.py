import time
import random
import threading
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab
import os

# Game state and constants
GAME_TIME = 0  # in seconds
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# Minimap location (adjust for your resolution)
MINIMAP_X = 860
MINIMAP_Y = 860
MINIMAP_WIDTH = 200
MINIMAP_HEIGHT = 200

# Main game area
GAME_AREA_X = 0
GAME_AREA_Y = 0
GAME_AREA_WIDTH = SCREEN_WIDTH
GAME_AREA_HEIGHT = SCREEN_HEIGHT

# AoE2 player colors (BGR for OpenCV)
PLAYER_COLORS = {
    'Blue': (255, 0, 0),
    'Red': (0, 0, 255),
    'Green': (0, 255, 0),
    'Teal': (255, 255, 0),
    'Yellow': (0, 255, 255),
    'Purple': (128, 0, 128),
    # 'Gray': (128, 128, 128),  # Removed Gray as it may not be reliable
    'Orange': (0, 165, 255)
}

# Define game ages and their corresponding time thresholds in seconds
GAME_AGES = [
    ('Dark Age', 0),
    ('Feudal Age', 600),
    ('Castle Age', 1200),
    ('Imperial Age', 1800)
]

# Load building templates for detection
BUILDING_TEMPLATES = {
    'Town Center': cv2.imread('town_center.png', cv2.IMREAD_COLOR),
    'Castle': cv2.imread('castle.png', cv2.IMREAD_COLOR)
}

# Validate that templates are loaded
for building, template in BUILDING_TEMPLATES.items():
    if template is None:
        print(f"Error: Template for {building} not found. Ensure 'town_center.png' and 'castle.png' are in the script directory.")
        exit(1)

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

game_state = GameState()

def capture_minimap():
    try:
        screenshot = ImageGrab.grab(bbox=(MINIMAP_X, MINIMAP_Y, MINIMAP_X + MINIMAP_WIDTH, MINIMAP_Y + MINIMAP_HEIGHT))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"Error capturing minimap: {e}")
        return None

def capture_game_area():
    try:
        screenshot = ImageGrab.grab(bbox=(GAME_AREA_X, GAME_AREA_Y, GAME_AREA_X + GAME_AREA_WIDTH, GAME_AREA_Y + GAME_AREA_HEIGHT))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"Error capturing game area: {e}")
        return None

def set_permanent_vision():
    pyautogui.hotkey('alt', 'f')
    time.sleep(0.5)
    pyautogui.hotkey('alt', 'f')
    game_state.vision_set = True
    print("Set permanent vision")

def toggle_stats():
    pyautogui.hotkey('alt', 'c')
    print("Toggled stats")

def detect_player_colors(image):
    player_colors = {}
    for color_name, color_bgr in PLAYER_COLORS.items():
        lower = np.array([max(c - 20, 0) for c in color_bgr])
        upper = np.array([min(c + 20, 255) for c in color_bgr])
        mask = cv2.inRange(image, lower, upper)
        if np.sum(mask) > 100:  # Adjust threshold as needed
            player_colors[color_name] = color_bgr
    return player_colors

def detect_activity(prev_image, curr_image):
    if prev_image is None or curr_image is None:
        return [], 0
    diff = cv2.absdiff(prev_image, curr_image)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    change_magnitude = np.sum(thresh)
    return contours, change_magnitude

def is_big_fight(curr_image, contours, current_age):
    # Define area thresholds based on age
    if current_age == 'Dark Age':
        area_threshold = 50
    elif current_age == 'Feudal Age':
        area_threshold = 100
    elif current_age == 'Castle Age':
        area_threshold = 200
    else:  # Imperial Age
        area_threshold = 300

    if len(contours) < 2:
        return False, set()

    large_contours = [c for c in contours if cv2.contourArea(c) > area_threshold]
    if len(large_contours) < 2:
        return False, set()

    colors_present = set()
    for contour in large_contours:
        mask = np.zeros(curr_image.shape[:2], np.uint8)
        cv2.drawContours(mask, [contour], 0, 255, -1)
        for color_name, color_bgr in game_state.player_colors.items():
            color_count = cv2.countNonZero(cv2.inRange(
                cv2.bitwise_and(curr_image, curr_image, mask=mask),
                np.array(color_bgr) - 20,
                np.array(color_bgr) + 20
            ))
            if color_count >= 5:  # At least 5 units of this color
                colors_present.add(color_name)
                if len(colors_present) >= 2:
                    return True, colors_present
    return False, set()

def find_most_active_area(contours):
    if not contours:
        return None
    largest_contour = max(contours, key=cv2.contourArea)
    M = cv2.moments(largest_contour)
    if M["m00"] != 0:
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        return (cx, cy)
    return None

def click_and_drag_follow(start_x, start_y, end_x, end_y, duration=0.5):
    try:
        pyautogui.moveTo(start_x, start_y, duration=0.2)
        pyautogui.dragTo(end_x, end_y, duration=duration, button='left')
        pyautogui.press('f')
        print("Following fight with click-and-drag and pressing 'F'")
    except pyautogui.FailSafeException:
        print("Fail-safe triggered during click and drag.")

def click_minimap(x, y):
    try:
        pyautogui.click(MINIMAP_X + x, MINIMAP_Y + y)
        print(f"Clicked minimap at ({MINIMAP_X + x}, {MINIMAP_Y + y})")
    except pyautogui.FailSafeException:
        print("Fail-safe triggered during minimap click.")

def update_game_age(game_state):
    global GAME_TIME
    for age, threshold in reversed(GAME_AGES):
        if GAME_TIME >= threshold:
            if game_state.current_age != age:
                game_state.current_age = age
                print(f"Game Age: {age}")
            break

def find_player_position(minimap_image, player_name):
    """
    Attempts to locate the player's position on the minimap.
    Returns the (x, y) coordinates if found, else None.
    """
    color_bgr = PLAYER_COLORS.get(player_name)
    if not color_bgr:
        print(f"No color defined for player: {player_name}")
        return None

    lower = np.array([max(c - 20, 0) for c in color_bgr])
    upper = np.array([min(c + 20, 255) for c in color_bgr])
    mask = cv2.inRange(minimap_image, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        # Assume the largest contour corresponds to the player's position
        largest_contour = max(contours, key=cv2.contourArea)
        M = cv2.moments(largest_contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            return (cx, cy)
    return None

def detect_buildings(minimap_image):
    """
    Detects buildings on the minimap using template matching.
    Returns a list of detected buildings with their types and positions.
    """
    detected_buildings = []
    for building_name, template in BUILDING_TEMPLATES.items():
        res = cv2.matchTemplate(minimap_image, template, cv2.TM_CCOEFF_NORMED)
        threshold = 0.8  # Adjust as needed
        loc = np.where(res >= threshold)
        w, h = template.shape[:2]
        for pt in zip(*loc[::-1]):
            center_x = pt[0] + w // 2
            center_y = pt[1] + h // 2
            detected_buildings.append({
                'type': building_name,
                'position': (center_x, center_y)
            })
    return detected_buildings

def auto_spectate():
    global GAME_TIME
    start_time = time.time()
    prev_minimap = capture_minimap()
    prev_game_area = capture_game_area()

    # Execute initial key presses to toggle fog of war
    pyautogui.hotkey('alt', 'd')
    time.sleep(0.5)
    pyautogui.hotkey('alt', 'f')
    time.sleep(0.5)
    print("Toggled fog of war with ALT+D and ALT+F")

    while True:
        try:
            current_time = time.time()
            GAME_TIME = int(current_time - start_time)

            # Update game age based on elapsed time
            update_game_age(game_state)

            # Set permanent vision at 10 minutes (600 seconds)
            if GAME_TIME >= 600 and not game_state.vision_set:
                set_permanent_vision()

            # Toggle stats every 10 seconds
            if current_time - game_state.last_stats_toggle_time >= 10:
                toggle_stats()
                game_state.last_stats_toggle_time = current_time

            curr_minimap = capture_minimap()
            curr_game_area = capture_game_area()

            # Detect player colors if not already detected
            if not game_state.player_colors:
                game_state.player_colors = detect_player_colors(curr_minimap)
                if game_state.player_colors:
                    print(f"Detected player colors: {list(game_state.player_colors.keys())}")

            # Detect buildings on the minimap
            buildings = detect_buildings(curr_minimap)
            for building in buildings:
                b_type = building['type']
                b_pos = building['position']
                if b_type not in game_state.permanent_structures:
                    game_state.permanent_structures[b_type] = b_pos
                    print(f"Detected new {b_type} at position {b_pos}")

            # Detect activity on minimap and game area
            activity_contours_minimap, change_magnitude_minimap = detect_activity(prev_minimap, curr_minimap)
            activity_contours_game_area, change_magnitude_game_area = detect_activity(prev_game_area, curr_game_area)

            # Track changes for big change detection
            game_state.change_history.append(change_magnitude_game_area)
            if len(game_state.change_history) > 10:  # Keep last 10 change magnitudes
                game_state.change_history.pop(0)
            average_change = sum(game_state.change_history) / len(game_state.change_history)

            # Define a threshold for big changes (e.g., 1.5 times the average change)
            BIG_CHANGE_THRESHOLD = 1.5 * average_change if average_change > 0 else 1000

            # Detect and handle big fights based on activity and big changes
            is_fight, players_involved = is_big_fight(curr_game_area, activity_contours_game_area, game_state.current_age)
            is_big_change = change_magnitude_game_area > BIG_CHANGE_THRESHOLD

            if (is_fight or is_big_change) and players_involved:
                # Identify conflicting players (players with troops in each other's bases)
                # For simplicity, assume that if multiple players are involved, they are in conflict
                game_state.conflict_players.update(players_involved)

                # Manage cooldown to balance screen time (e.g., 15 seconds cooldown)
                if current_time - game_state.last_fight_time >= 15 and game_state.conflict_players:
                    # Prepare spectate queue if empty
                    if not game_state.spectate_queue:
                        game_state.spectate_queue = list(game_state.conflict_players)
                        random.shuffle(game_state.spectate_queue)  # Randomize order

                    # Get the next player to spectate
                    player_to_follow = game_state.spectate_queue.pop(0)
                    game_state.conflict_players.discard(player_to_follow)

                    # Log the player being followed
                    print(f"Following player: {player_to_follow}")

                    # Find the player's position on the minimap
                    player_position = find_player_position(curr_minimap, player_to_follow)
                    if player_position:
                        # Introduce a 1-second delay before clicking
                        time.sleep(1)

                        # Click on the player's position on the minimap
                        click_minimap(*player_position)

                        # Click-and-drag across the center of the screen with extended duration
                        center_x = SCREEN_WIDTH // 2
                        center_y = SCREEN_HEIGHT // 2
                        drag_distance = 100  # Pixels to drag in each direction

                        start_x = center_x - drag_distance
                        start_y = center_y - drag_distance
                        end_x = center_x + drag_distance
                        end_y = center_y + drag_distance

                        click_and_drag_follow(start_x, start_y, end_x, end_y, duration=1.5)  # Extended duration

                        # Update last fight time
                        game_state.last_fight_time = current_time

                        # Optional: Continue focusing until fight ends (requires fight tracking)
                        # For simplicity, we'll pause for a longer duration
                        time.sleep(10)  # Extended pause to watch the fight
                    else:
                        print(f"Could not find position for player: {player_to_follow}")

            elif current_time - game_state.last_action_time >= 2:  # Action every 2 seconds
                active_point_minimap = find_most_active_area(activity_contours_minimap)
                if active_point_minimap:
                    # Introduce a 1-second delay before clicking
                    time.sleep(1)
                    click_minimap(*active_point_minimap)
                    print("Following active area on minimap")
                game_state.last_action_time = current_time

            prev_minimap = curr_minimap
            prev_game_area = curr_game_area
            time.sleep(0.5)  # Short sleep to prevent excessive CPU usage
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            time.sleep(1)  # Wait a bit before trying again

if __name__ == "__main__":
    try:
        print("Starting AoE2 Auto-Spectator. Press Ctrl+C to stop.")
        auto_spectate()
    except KeyboardInterrupt:
        print("Auto-Spectator stopped by user.")
