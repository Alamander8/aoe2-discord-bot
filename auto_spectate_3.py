import time
import random
import threading
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab


### Current issues:

### Event log is clicking the way bottom left of the screen. 
### It does a really bad job clicking on event log things
### Would rather it click minimap only, unless it is click dragging and pressing F to follow a big fight or 
### a group of units. It also really needs to bounce between the players a little more than it does. 
### It says "Focusing on Gray Player" and analyzing the strategy etc which is great, but
### Hows it getting gray? Are we sending the images in grayscale cause if we are then no wonder its doing bad. 



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

# Event log area (adjust these values)
EVENT_LOG_X = 10
EVENT_LOG_Y = 700
EVENT_LOG_WIDTH = 300
EVENT_LOG_HEIGHT = 100

# Event log icon coordinates
EVENT_LOG_ICON_X = 45
EVENT_LOG_ICON_Y = 950

# Age indicator area
AGE_INDICATOR = (SCREEN_WIDTH // 2 - 50, 10, 100, 30)

# AoE2 player colors (BGR for OpenCV)
PLAYER_COLORS = {
    'Blue': (255, 0, 0),
    'Red': (0, 0, 255),
    'Green': (0, 255, 0),
    'Yellow': (0, 255, 255),
    'Cyan': (255, 255, 0),
    'Purple': (128, 0, 128),
    'Orange': (0, 165, 255),
    'Gray': (128, 128, 128)
}

class GameState:
    def __init__(self):
        self.vision_set = False
        self.last_action_time = 0
        self.last_event_check_time = 0
        self.player_colors = {}
        self.current_focus = None
        self.focus_start_time = time.time()
        self.last_stats_toggle_time = 0
        self.current_age = 1
        self.player_ages = {}
        self.player_positions = []

game_state = GameState()

def capture_minimap():
    screenshot = ImageGrab.grab(bbox=(MINIMAP_X, MINIMAP_Y, MINIMAP_X + MINIMAP_WIDTH, MINIMAP_Y + MINIMAP_HEIGHT))
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def capture_game_area():
    screenshot = ImageGrab.grab(bbox=(GAME_AREA_X, GAME_AREA_Y, GAME_AREA_X + GAME_AREA_WIDTH, GAME_AREA_Y + GAME_AREA_HEIGHT))
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def capture_event_log():
    screenshot = ImageGrab.grab(bbox=(EVENT_LOG_X, EVENT_LOG_Y, EVENT_LOG_X + EVENT_LOG_WIDTH, EVENT_LOG_Y + EVENT_LOG_HEIGHT))
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

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
        mask = cv2.inRange(image, np.array(color_bgr) - 20, np.array(color_bgr) + 20)
        if np.sum(mask) > 100:  # Adjust threshold as needed
            player_colors[color_name] = color_bgr
    return player_colors

def detect_activity(prev_image, curr_image):
    diff = cv2.absdiff(prev_image, curr_image)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours

def is_big_fight(curr_image, contours):
    if len(contours) < 2:
        return False
    
    large_contours = [c for c in contours if cv2.contourArea(c) > 100]
    if len(large_contours) < 2:
        return False
    
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
                    return True
    return False

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

def monitor_event_log():
    while True:
        try:
            prev_log = capture_event_log()
            time.sleep(1)
            curr_log = capture_event_log()
            new_event = detect_new_event(prev_log, curr_log)
            if new_event:
                click_event_icon()
        except Exception as e:
            print(f"Error in monitor_event_log: {str(e)}")
            time.sleep(1)

def click_and_drag_follow(start_x, start_y, end_x, end_y):
    try:
        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragTo(end_x, end_y, duration=0.5, button='left')
        pyautogui.press('f')
        print("Following fight with click-and-drag")
    except pyautogui.FailSafeException:
        print("Fail-safe triggered during click and drag.")

def click_minimap(x, y):
    pyautogui.click(MINIMAP_X + x, MINIMAP_Y + y)

def detect_new_event(prev_log, curr_log):
    diff = cv2.absdiff(prev_log, curr_log)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        return True
    return False

def click_event_icon():
    pyautogui.click(EVENT_LOG_ICON_X, EVENT_LOG_ICON_Y)
    print(f"Clicked event log icon at ({EVENT_LOG_ICON_X}, {EVENT_LOG_ICON_Y})")

def monitor_event_log():
    prev_log = capture_event_log()
    while True:
        curr_log = capture_event_log()
        new_event = detect_new_event(prev_log, curr_log)
        if new_event:
            click_event_icon()
        prev_log = curr_log
        time.sleep(1)

def detect_player_positions(minimap):
    positions = []
    for color_name, color_bgr in game_state.player_colors.items():
        mask = cv2.inRange(minimap, np.array(color_bgr) - 20, np.array(color_bgr) + 20)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            M = cv2.moments(largest_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                positions.append((color_name, (cx, cy)))
    return positions

def detect_age_advancement(image):
    roi = image[AGE_INDICATOR[1]:AGE_INDICATOR[1]+AGE_INDICATOR[3], AGE_INDICATOR[0]:AGE_INDICATOR[0]+AGE_INDICATOR[2]]
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_roi, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if len(contours) > 0:
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        if area > 300:  # Adjust thresholds as needed
            return 4  # Imperial Age
        elif area > 200:
            return 3  # Castle Age
        elif area > 100:
            return 2  # Feudal Age
    return 1  # Dark Age

def analyze_player_strategy(player_color, age):
    if age == 1:
        print(f"Analyzing {player_color}'s Dark Age strategy: Scouting and eco setup")
    elif age == 2:
        print(f"Analyzing {player_color}'s Feudal Age strategy: Looking for new buildings")
    elif age == 3:
        print(f"Analyzing {player_color}'s Castle Age strategy: Checking for unique units and techs")
    elif age == 4:
        print(f"Analyzing {player_color}'s Imperial Age strategy: Looking for late-game army composition")

def auto_spectate():
    global GAME_TIME
    start_time = time.time()
    prev_minimap = capture_minimap()
    prev_game_area = capture_game_area()

    # Start event log monitoring in a separate thread
    event_thread = threading.Thread(target=monitor_event_log, daemon=True)
    event_thread.start()

    while True:
        try:
            current_time = time.time()
            GAME_TIME = int(current_time - start_time)

            if GAME_TIME == 600 and not game_state.vision_set:
                set_permanent_vision()

            if current_time - game_state.last_stats_toggle_time >= 10:
                toggle_stats()
                game_state.last_stats_toggle_time = current_time

            curr_minimap = capture_minimap()
            curr_game_area = capture_game_area()

            if not game_state.player_colors:
                game_state.player_colors = detect_player_colors(curr_minimap)

            game_state.player_positions = detect_player_positions(curr_minimap)

            activity_contours_minimap = detect_activity(prev_minimap, curr_minimap)
            activity_contours_game_area = detect_activity(prev_game_area, curr_game_area)

            current_age = detect_age_advancement(curr_game_area)

            # Adjusted player focus to happen more frequently
            action = random.choices(['fight', 'player_focus', 'minimap'], weights=[0.3, 0.5, 0.2])[0]

            if action == 'fight' and is_big_fight(curr_game_area, activity_contours_game_area):
                active_point = find_most_active_area(activity_contours_game_area)
                if active_point:
                    start_x = GAME_AREA_X + active_point[0] - 50
                    start_y = GAME_AREA_Y + active_point[1] - 50
                    end_x = start_x + 100
                    end_y = start_y + 100
                    click_and_drag_follow(start_x, start_y, end_x, end_y)
                    time.sleep(10)  # Watch the fight for 10 seconds
            elif action == 'player_focus':
                if game_state.player_positions:
                    player_color, position = random.choice(game_state.player_positions)
                    click_minimap(*position)
                    print(f"Focusing on {player_color} player")
                    player_age = game_state.player_ages.get(player_color, current_age)
                    analyze_player_strategy(player_color, player_age)
                    time.sleep(5)
            elif action == 'minimap' and current_time - game_state.last_action_time >= 2:
                active_point_minimap = find_most_active_area(activity_contours_minimap)
                if active_point_minimap:
                    click_minimap(*active_point_minimap)
                    print("Following active area on minimap")
                game_state.last_action_time = current_time

            # Update player ages
            for player, _ in game_state.player_positions:
                if player not in game_state.player_ages or current_age > game_state.player_ages[player]:
                    game_state.player_ages[player] = current_age
                    print(f"{player} advanced to {['Dark', 'Feudal', 'Castle', 'Imperial'][current_age - 1]} Age")

            prev_minimap = curr_minimap
            prev_game_area = curr_game_area
            time.sleep(0.5)  # Short sleep to prevent excessive CPU usage
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            time.sleep(1)  # Wait a bit before trying again

if __name__ == "__main__":
    try:
        print("Starting Enhanced AoE2 Auto-Spectator in 3 seconds. Press Ctrl+C to stop.")
        time.sleep(3)  # Wait for 3 seconds before starting
        auto_spectate()
    except KeyboardInterrupt:
        print("Auto-Spectator stopped by user.")