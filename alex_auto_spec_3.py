import time
import random
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab

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
    'Yellow': (0, 255, 255)
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

game_state = GameState()

def capture_minimap():
    screenshot = ImageGrab.grab(bbox=(MINIMAP_X, MINIMAP_Y, MINIMAP_X + MINIMAP_WIDTH, MINIMAP_Y + MINIMAP_HEIGHT))
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def capture_game_area():
    screenshot = ImageGrab.grab(bbox=(GAME_AREA_X, GAME_AREA_Y, GAME_AREA_X + GAME_AREA_WIDTH, GAME_AREA_Y + GAME_AREA_HEIGHT))
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
    
    large_contours = [c for c in contours if cv2.contourArea(c) > 80]  # Reduced threshold
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
            if color_count >= 4:  # Reduced threshold
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

def detect_simultaneous_fights(minimap):
    fights = []
    for color1 in PLAYER_COLORS:
        for color2 in PLAYER_COLORS:
            if color1 != color2:
                mask1 = cv2.inRange(minimap, np.array(PLAYER_COLORS[color1]) - 20, np.array(PLAYER_COLORS[color1]) + 20)
                mask2 = cv2.inRange(minimap, np.array(PLAYER_COLORS[color2]) - 20, np.array(PLAYER_COLORS[color2]) + 20)
                
                contours1, _ = cv2.findContours(mask1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                contours2, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                for c1 in contours1:
                    for c2 in contours2:
                        if cv2.contourArea(c1) > 50 and cv2.contourArea(c2) > 50:  # Adjust threshold as needed
                            m1 = cv2.moments(c1)
                            m2 = cv2.moments(c2)
                            if m1["m00"] != 0 and m2["m00"] != 0:
                                cx1, cy1 = int(m1["m10"] / m1["m00"]), int(m1["m01"] / m1["m00"])
                                cx2, cy2 = int(m2["m10"] / m2["m00"]), int(m2["m01"] / m2["m00"])
                                distance = np.sqrt((cx1 - cx2)**2 + (cy1 - cy2)**2)
                                if distance < 50:  # Adjust distance threshold as needed
                                    fights.append(((cx1, cy1), (cx2, cy2)))
    return fights

def auto_spectate():
    global GAME_TIME
    start_time = time.time()
    prev_minimap = capture_minimap()
    prev_game_area = capture_game_area()
    
    while True:
        try:
            current_time = time.time()
            GAME_TIME = int(current_time - start_time)
            
            # Set permanent vision at 10 minutes
            if GAME_TIME == 600 and not game_state.vision_set:
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
            
            # Detect simultaneous fights on minimap
            game_state.simultaneous_fights = detect_simultaneous_fights(curr_minimap)
            
            # Detect activity on minimap and game area
            activity_contours_minimap = detect_activity(prev_minimap, curr_minimap)
            activity_contours_game_area = detect_activity(prev_game_area, curr_game_area)
            
            if game_state.simultaneous_fights:
                # Bounce between simultaneous fights
                for fight in game_state.simultaneous_fights:
                    for point in fight:
                        click_minimap(*point)
                        time.sleep(5)  # Watch each fight for 5 seconds
            elif is_big_fight(curr_game_area, activity_contours_game_area):
                active_point = find_most_active_area(activity_contours_game_area)
                if active_point:
                    start_x = GAME_AREA_X + active_point[0] - 50
                    start_y = GAME_AREA_Y + active_point[1] - 50
                    end_x = start_x + 100
                    end_y = start_y + 100
                    click_and_drag_follow(start_x, start_y, end_x, end_y)
                    time.sleep(10)  # Watch the fight for 10 seconds
            elif current_time - game_state.last_action_time >= 2:  # Action every 2 seconds
                active_point_minimap = find_most_active_area(activity_contours_minimap)
                if active_point_minimap:
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