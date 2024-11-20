import time
import random
import pyautogui
import cv2
import numpy as np
from PIL import ImageGrab

# Game state and constants
GAME_TIME = 0
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# Minimap location (adjust for your resolution)
MINIMAP_X, MINIMAP_Y = 860, 860
MINIMAP_WIDTH, MINIMAP_HEIGHT = 200, 200

# Player icon and military indicator locations (adjust these)
P1_ICON_X, P1_ICON_Y = 10, 10
P2_ICON_X, P2_ICON_Y = SCREEN_WIDTH - 210, 10
ICON_WIDTH, ICON_HEIGHT = 200, 50

# Chat area (adjust these)
CHAT_X, CHAT_Y = 10, SCREEN_HEIGHT - 150
CHAT_WIDTH, CHAT_HEIGHT = 300, 100

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

class GameState:
    def __init__(self):
        self.last_action_time = 0
        self.last_icon_click_time = 0
        self.last_chat_check_time = 0
        self.player_bases = {}

game_state = GameState()

def capture_screen_region(x, y, width, height):
    screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def capture_minimap():
    return capture_screen_region(MINIMAP_X, MINIMAP_Y, MINIMAP_WIDTH, MINIMAP_HEIGHT)

def capture_chat_area():
    return capture_screen_region(CHAT_X, CHAT_Y, CHAT_WIDTH, CHAT_HEIGHT)

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

def detect_color_interactions(minimap):
    interactions = []
    for color1, color_bgr1 in PLAYER_COLORS.items():
        mask1 = cv2.inRange(minimap, np.array(color_bgr1) - 20, np.array(color_bgr1) + 20)
        for color2, color_bgr2 in PLAYER_COLORS.items():
            if color1 != color2:
                mask2 = cv2.inRange(minimap, np.array(color_bgr2) - 20, np.array(color_bgr2) + 20)
                interaction = cv2.bitwise_and(mask1, mask2)
                if cv2.countNonZero(interaction) > 0:
                    contours, _ = cv2.findContours(interaction, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        largest_contour = max(contours, key=cv2.contourArea)
                        M = cv2.moments(largest_contour)
                        if M["m00"] != 0:
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"])
                            interactions.append((cx, cy, color1, color2))
    return interactions

def detect_enemy_near_base(minimap, bases):
    for base_color, base_pos in bases.items():
        base_mask = np.zeros(minimap.shape[:2], dtype=np.uint8)
        cv2.circle(base_mask, base_pos, 20, 255, -1)  # Adjust radius as needed
        for enemy_color, enemy_color_bgr in PLAYER_COLORS.items():
            if enemy_color != base_color:
                enemy_mask = cv2.inRange(minimap, np.array(enemy_color_bgr) - 20, np.array(enemy_color_bgr) + 20)
                enemy_near_base = cv2.bitwise_and(enemy_mask, enemy_mask, mask=base_mask)
                if cv2.countNonZero(enemy_near_base) > 0:
                    return base_pos  # Return the position of the base under potential attack
    return None

def click_and_follow(x, y):
    pyautogui.click(x, y)
    time.sleep(0.1)  # Short pause to ensure the click registers
    pyautogui.press('f')
    print(f"Clicked and following at ({x}, {y})")

def click_minimap(x, y):
    click_and_follow(MINIMAP_X + x, MINIMAP_Y + y)

def check_and_click_icons(player):
    icon_region = capture_screen_region(
        P1_ICON_X if player == 1 else P2_ICON_X,
        P1_ICON_Y if player == 1 else P2_ICON_Y,
        ICON_WIDTH, ICON_HEIGHT
    )
    
    gray = cv2.cvtColor(icon_region, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w > 10 and h > 10:  # Minimum size to be considered an icon
            click_x = (P1_ICON_X if player == 1 else P2_ICON_X) + x + w // 2
            click_y = (P1_ICON_Y if player == 1 else P2_ICON_Y) + y + h // 2
            click_and_follow(click_x, click_y)
            time.sleep(0.5)  # Wait between clicks

def check_chat_events():
    chat_image = capture_chat_area()
    gray = cv2.cvtColor(chat_image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Find the leftmost contour (assuming the clickable icon is on the left)
        leftmost_contour = min(contours, key=lambda c: cv2.boundingRect(c)[0])
        x, y, w, h = cv2.boundingRect(leftmost_contour)
        click_x = CHAT_X + x + w // 2
        click_y = CHAT_Y + y + h // 2
        click_and_follow(click_x, click_y)
        print("Clicked on chat event")
        return True
    return False

def auto_spectate():
    global GAME_TIME
    start_time = time.time()
    
    while True:
        try:
            current_time = time.time()
            GAME_TIME = int(current_time - start_time)
            
            minimap = capture_minimap()
            
            # Update player bases periodically
            if GAME_TIME % 60 == 0 or not game_state.player_bases:
                game_state.player_bases = detect_player_bases(minimap)
            
            # Check for enemies near bases (high priority)
            enemy_at_base = detect_enemy_near_base(minimap, game_state.player_bases)
            if enemy_at_base:
                click_minimap(*enemy_at_base)
                continue
            
            # Check for color interactions on the minimap
            interactions = detect_color_interactions(minimap)
            if interactions:
                interaction = random.choice(interactions)
                click_minimap(interaction[0], interaction[1])
                continue
            
            # Check chat events every 10 seconds
            if current_time - game_state.last_chat_check_time > 10:
                if check_chat_events():
                    game_state.last_chat_check_time = current_time
                    continue
            
            # Click player icons every 30 seconds
            if current_time - game_state.last_icon_click_time > 30:
                check_and_click_icons(1)  # Player 1
                check_and_click_icons(2)  # Player 2
                game_state.last_icon_click_time = current_time
                continue
            
            # If no specific events, click a random point on the minimap
            if current_time - game_state.last_action_time >= 5:
                random_x = random.randint(0, MINIMAP_WIDTH - 1)
                random_y = random.randint(0, MINIMAP_HEIGHT - 1)
                click_minimap(random_x, random_y)
                game_state.last_action_time = current_time
            
            time.sleep(0.1)  # Short sleep to prevent excessive CPU usage
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            time.sleep(1)  # Wait a bit before trying again

if __name__ == "__main__":
    try:
        print("Starting Refined AoE2 Auto-Spectator. Press Ctrl+C to stop.")
        auto_spectate()
    except KeyboardInterrupt:
        print("Auto-Spectator stopped by user.")