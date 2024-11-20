import time
import random
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab
from collections import deque

# Game state and constants
GAME_TIME = 0
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# Adjust these values based on your screen setup
MINIMAP_X, MINIMAP_Y = 860, 860
MINIMAP_WIDTH, MINIMAP_HEIGHT = 200, 200

# AoE2 player colors (BGR for OpenCV)
PLAYER_COLORS = {
    'Blue': (255, 0, 0),
    'Red': (0, 0, 255),
    'Green': (0, 255, 0),
    'Yellow': (0, 255, 255),
    'Cyan': (255, 255, 0),
    'Pink': (255, 0, 255),
    'Gray': (128, 128, 128),
    'Orange': (0, 165, 255)
}

# Number of frames to keep in the buffer
FRAME_BUFFER_SIZE = 10

class GameState:
    def __init__(self):
        self.fow_toggled = False
        self.zoomed_out = False
        self.last_action_time = 0
        self.player_bases = {}
        self.minimap_buffer = deque(maxlen=FRAME_BUFFER_SIZE)

game_state = GameState()

def capture_minimap():
    screenshot = ImageGrab.grab(bbox=(MINIMAP_X, MINIMAP_Y, MINIMAP_X + MINIMAP_WIDTH, MINIMAP_Y + MINIMAP_HEIGHT))
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def toggle_fow_and_zoom():
    pyautogui.hotkey('alt', 'd')
    pyautogui.hotkey('alt', 'f')
    game_state.fow_toggled = True
    
    try:
        pyautogui.moveTo(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        pyautogui.scroll(-3)
        game_state.zoomed_out = True
    except:
        print("Mouse wheel zoom failed, using '3' key as fallback")
        pyautogui.press('3')
        game_state.zoomed_out = True
    
    print("Toggled fog of war settings and zoomed out")

def detect_player_bases(minimap):
    bases = {}
    for color_name, color_bgr in PLAYER_COLORS.items():
        mask = cv2.inRange(minimap, np.array(color_bgr) - 20, np.array(color_bgr) + 20)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest_contour) > 100:
                M = cv2.moments(largest_contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    bases[color_name] = (cx, cy)
    return bases

def detect_activity(prev_minimap, curr_minimap):
    diff = cv2.absdiff(prev_minimap, curr_minimap)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours

def prioritize_activity(contours, player_bases):
    if not contours:
        return None

    priority_scores = []
    for contour in contours:
        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # Calculate base proximity score
        base_proximity_score = 0
        for base_color, base_pos in player_bases.items():
            distance = np.sqrt((cx - base_pos[0])**2 + (cy - base_pos[1])**2)
            base_proximity_score += 1 / (distance + 1)  # Add 1 to avoid division by zero

        # Calculate size score
        size_score = cv2.contourArea(contour) / (MINIMAP_WIDTH * MINIMAP_HEIGHT)

        # Calculate edge penalty (to slightly discourage constant edge checking)
        edge_penalty = 0
        if cx < 10 or cx > MINIMAP_WIDTH - 10 or cy < 10 or cy > MINIMAP_HEIGHT - 10:
            edge_penalty = 0.1

        # Combine scores
        total_score = base_proximity_score + size_score - edge_penalty
        priority_scores.append((total_score, (cx, cy)))

    # Return the point with the highest priority score
    return max(priority_scores, key=lambda x: x[0])[1] if priority_scores else None

def detect_enemy_in_base(minimap, player_bases):
    for base_color, base_pos in player_bases.items():
        base_color_bgr = PLAYER_COLORS[base_color]
        for enemy_color, enemy_color_bgr in PLAYER_COLORS.items():
            if enemy_color != base_color:
                # Create a mask for the base area
                base_mask = np.zeros(minimap.shape[:2], dtype=np.uint8)
                cv2.circle(base_mask, base_pos, 20, 255, -1)  # Adjust radius as needed

                # Check for enemy color in the base area
                enemy_in_base = cv2.bitwise_and(minimap, minimap, mask=base_mask)
                enemy_color_mask = cv2.inRange(enemy_in_base, np.array(enemy_color_bgr) - 20, np.array(enemy_color_bgr) + 20)

                if cv2.countNonZero(enemy_color_mask) > 50:  # Adjust threshold as needed
                    return base_pos  # Return the position of the base under attack

    return None

def click_minimap(x, y):
    pyautogui.click(MINIMAP_X + x, MINIMAP_Y + y)

def auto_spectate():
    global GAME_TIME
    start_time = time.time()
    prev_minimap = capture_minimap()
    
    while True:
        try:
            current_time = time.time()
            GAME_TIME = int(current_time - start_time)
            
            if GAME_TIME == 3 and not game_state.fow_toggled:
                toggle_fow_and_zoom()
            
            curr_minimap = capture_minimap()
            game_state.minimap_buffer.append(curr_minimap)
            
            # Update player bases periodically
            if GAME_TIME % 60 == 0 or not game_state.player_bases:
                game_state.player_bases = detect_player_bases(curr_minimap)
            
            # First, check for enemy incursions into bases
            enemy_in_base_pos = detect_enemy_in_base(curr_minimap, game_state.player_bases)
            if enemy_in_base_pos:
                click_minimap(*enemy_in_base_pos)
                print("Enemy detected in a player's base! Focusing on the action.")
                time.sleep(5)  # Focus on this for a bit longer
            elif current_time - game_state.last_action_time >= 2:
                # Detect and prioritize activity
                activity_contours = detect_activity(prev_minimap, curr_minimap)
                priority_point = prioritize_activity(activity_contours, game_state.player_bases)
                
                if priority_point:
                    click_minimap(*priority_point)
                    print(f"Following high-priority activity at {priority_point}")
                    game_state.last_action_time = current_time
            
            prev_minimap = curr_minimap
            time.sleep(0.1)  # Short sleep to prevent excessive CPU usage
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            time.sleep(1)  # Wait a bit before trying again

if __name__ == "__main__":
    try:
        print("Starting Optimized AoE2 Auto-Spectator. Press Ctrl+C to stop.")
        auto_spectate()
    except KeyboardInterrupt:
        print("Auto-Spectator stopped by user.")