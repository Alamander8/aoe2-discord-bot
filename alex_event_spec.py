import time
import random
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab

# Base resolution for coordinate calculations
BASE_WIDTH = 1920
BASE_HEIGHT = 1080

# Game state and constants
GAME_TIME = 0  # in seconds
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# Scaling factors
SCALE_X = SCREEN_WIDTH / BASE_WIDTH
SCALE_Y = SCREEN_HEIGHT / BASE_HEIGHT

def scale_coordinate(x, y):
    return int(x * SCALE_X), int(y * SCALE_Y)

def scale_dimension(width, height):
    return int(width * SCALE_X), int(height * SCALE_Y)

# Dynamically calculated coordinates
MINIMAP_X, MINIMAP_Y = scale_coordinate(731, 0)
MINIMAP_WIDTH, MINIMAP_HEIGHT = scale_dimension(1195 - 731, 1195)

TOP_LEFT_X, TOP_LEFT_Y = scale_coordinate(210, BASE_HEIGHT - 1035)
TOP_LEFT_WIDTH, TOP_LEFT_HEIGHT = scale_dimension(579 - 210, 1035 - 979)

TOP_RIGHT_X, TOP_RIGHT_Y = scale_coordinate(1342, BASE_HEIGHT - 1035)
TOP_RIGHT_WIDTH, TOP_RIGHT_HEIGHT = scale_dimension(1711 - 1342, 1035 - 979)

EVENT_FEED_X, EVENT_FEED_Y = scale_coordinate(37, BASE_HEIGHT - 494)
EVENT_FEED_WIDTH, EVENT_FEED_HEIGHT = scale_dimension(76 - 37, 494 - 240)

# AoE2 player colors (BGR for OpenCV)
PLAYER_COLORS = {
    'Blue': (255, 0, 0),
    'Red': (0, 0, 255),
    'Green': (0, 255, 0),
    'Yellow': (0, 255, 255),
    'Cyan': (255, 255, 0),
    'Purple': (128, 0, 128),
    'Gray': (128, 128, 128),
    'Orange': (0, 165, 255),
}

class GameState:
    def __init__(self):
        self.vision_set = False
        self.last_action_time = 0
        self.player_colors = {}
        self.current_focus = None
        self.focus_start_time = time.time()
        self.last_stats_toggle_time = 0
        self.simultaneous_fights = []
        self.player_view_times = {color: 0 for color in PLAYER_COLORS}

game_state = GameState()

def capture_area(x, y, width, height):
    screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def capture_minimap():
    return capture_area(MINIMAP_X, MINIMAP_Y, MINIMAP_WIDTH, MINIMAP_HEIGHT)

def capture_top_left():
    return capture_area(TOP_LEFT_X, TOP_LEFT_Y, TOP_LEFT_WIDTH, TOP_LEFT_HEIGHT)

def capture_top_right():
    return capture_area(TOP_RIGHT_X, TOP_RIGHT_Y, TOP_RIGHT_WIDTH, TOP_RIGHT_HEIGHT)

def capture_event_feed():
    return capture_area(EVENT_FEED_X, EVENT_FEED_Y, EVENT_FEED_WIDTH, EVENT_FEED_HEIGHT)

def detect_activity(prev_image, curr_image):
    diff = cv2.absdiff(prev_image, curr_image)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours

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

def click_minimap(x, y):
    click_x = MINIMAP_X + x
    click_y = MINIMAP_Y + y
    pyautogui.click(click_x, click_y)
    print(f"Clicked on minimap at ({x}, {y})")

def detect_unit_icons(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    icon_contours = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if 100 < area < 1000:  # Adjust these values based on your icon size
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h
            if 0.8 < aspect_ratio < 1.2:  # Assuming icons are roughly square
                icon_contours.append((x, y, w, h))
    
    return icon_contours

def click_unit_icon_and_follow():
    section = random.choice(['left', 'right'])
    if section == 'left':
        image = capture_top_left()
        base_x, base_y = TOP_LEFT_X, TOP_LEFT_Y
        icons = detect_unit_icons(image)
        icons.sort(key=lambda x: x[0])  # Sort from left to right
    else:
        image = capture_top_right()
        base_x, base_y = TOP_RIGHT_X, TOP_RIGHT_Y
        icons = detect_unit_icons(image)
        icons.sort(key=lambda x: x[0], reverse=True)  # Sort from right to left
    
    if icons:
        icon = random.choice(icons)
        x, y, w, h = icon
        click_x = base_x + x + w // 2
        click_y = base_y + y + h // 2
        pyautogui.click(click_x, click_y)
        pyautogui.press('f')
        print(f"Clicked on unit icon in {section} section and started following")
    else:
        print(f"No unit icons detected in {section} section")

def detect_event_icons(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    icon_contours = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if 50 < area < 500:  # Adjust these values based on your icon size
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h
            if 0.8 < aspect_ratio < 1.2:  # Assuming icons are roughly square
                icon_contours.append((x, y, w, h))
    
    return icon_contours

def click_event_feed_icon():
    image = capture_event_feed()
    icons = detect_event_icons(image)
    
    if icons:
        icon = random.choice(icons)
        x, y, w, h = icon
        click_x = EVENT_FEED_X + x + w // 2
        click_y = EVENT_FEED_Y + y + h // 2
        pyautogui.click(click_x, click_y)
        print("Clicked on event feed icon")
    else:
        print("No event icons detected in event feed")

def balance_player_views():
    total_time = sum(game_state.player_view_times.values())
    if total_time == 0:
        return random.choice(list(PLAYER_COLORS.keys()))
    least_viewed_player = min(game_state.player_view_times, key=game_state.player_view_times.get)
    return least_viewed_player

def update_player_view_time(player_color):
    current_time = time.time()
    if game_state.current_focus:
        game_state.player_view_times[game_state.current_focus] += current_time - game_state.focus_start_time
    game_state.current_focus = player_color
    game_state.focus_start_time = current_time

def auto_spectate():
    global GAME_TIME
    start_time = time.time()
    last_action_time = 0
    action_interval = 3  # Perform an action every 3 seconds
    prev_minimap = capture_minimap()
    
    while True:
        try:
            current_time = time.time()
            GAME_TIME = int(current_time - start_time)
            
            if current_time - last_action_time >= action_interval:
                curr_minimap = capture_minimap()
                activity_contours = detect_activity(prev_minimap, curr_minimap)
                
                # 70% chance to use activity detection, 30% chance for other actions
                if random.random() < 0.7 and activity_contours:
                    active_point = find_most_active_area(activity_contours)
                    if active_point:
                        click_minimap(*active_point)
                else:
                    action = random.choice(['event_feed', 'unit_icon'])
                    if action == 'event_feed':
                        click_event_feed_icon()
                    elif action == 'unit_icon':
                        click_unit_icon_and_follow()
                
                player_to_focus = balance_player_views()
                update_player_view_time(player_to_focus)
                
                last_action_time = current_time
                prev_minimap = curr_minimap
            
            time.sleep(0.1)  # Short sleep to prevent excessive CPU usage
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            time.sleep(1)

if __name__ == "__main__":
    try:
        print("Starting Enhanced AoE2 Auto-Spectator with balanced activity and icon detection. Press Ctrl+C to stop.")
        auto_spectate()
    except KeyboardInterrupt:
        print("Auto-Spectator stopped by user.")