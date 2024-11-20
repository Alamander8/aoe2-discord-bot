# autospectate/spectate_logic.py

import cv2
import numpy as np
import time
import threading
import matplotlib.pyplot as plt
import seaborn as sns
from autospectate.game_state import game_state
from autospectate.utils import (
    capture_screen,
    calculate_distance,
    click_position,
    drag_and_follow,
    log_info,
    log_error
)
from autospectate.windows_management import switch_to_window

def detect_player_activity(minimap_image, player_hsv_ranges):
    """
    Detects activity for each player based on HSV color masks.
    
    Args:
        minimap_image (numpy.ndarray): Captured minimap image in BGR format.
        player_hsv_ranges (dict): Dictionary containing HSV lower and upper bounds for each player.
    
    Returns:
        dict: Dictionary with player names as keys and count of detected pixels as values.
    """
    activity = {}
    try:
        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)
    except Exception as e:
        log_error(f"Error converting minimap to HSV: {e}")
        return activity

    for player, hsv_range in player_hsv_ranges.items():
        lower = np.array(hsv_range['lower'], dtype=np.uint8)
        upper = np.array(hsv_range['upper'], dtype=np.uint8)
        mask = cv2.inRange(hsv_image, lower, upper)
        pixel_count = cv2.countNonZero(mask)
        activity[player] = pixel_count

    return activity

def detect_blinking_icons(prev_activity, current_activity, blink_threshold=100):
    """
    Detects blinking by comparing previous and current activity counts.
    
    Args:
        prev_activity (dict): Previous activity counts for each player.
        current_activity (dict): Current activity counts for each player.
        blink_threshold (int): Minimum change in pixel count to consider as blinking.
    
    Returns:
        set: Set of player names who are blinking.
    """
    blinking_players = set()
    for player in current_activity:
        if player in prev_activity:
            change = abs(current_activity[player] - prev_activity[player])
            if change >= blink_threshold:
                blinking_players.add(player)
    return blinking_players

def spectate_player(player_name):
    """
    Spectates the specified player by clicking on their minimap position.
    
    Args:
        player_name (str): Name of the player to spectate.
    """
    try:
        # Retrieve player's minimap position from game_state
        player_position = game_state.player_positions.get(player_name)
        if player_position:
            # Convert minimap position to screen coordinates
            screen_x = game_state.config['MINIMAP_X'] + player_position[0]
            screen_y = game_state.config['MINIMAP_Y'] + player_position[1]
            click_position(screen_x, screen_y)
            log_info(f"Spectating player: {player_name} at position ({screen_x}, {screen_y})")
    
            # Perform drag and follow actions
            center_x = game_state.config['GAME_AREA_WIDTH'] // 2
            center_y = game_state.config['GAME_AREA_HEIGHT'] // 2
            drag_distance = 100  # Pixels to drag in each direction
    
            start_x = center_x - drag_distance
            start_y = center_y - drag_distance
            end_x = center_x + drag_distance
            end_y = center_y + drag_distance
    
            drag_and_follow(start_x, start_y, end_x, end_y, duration=1.5)
    
            # Switch to CaptureAge window
            switch_to_window('CaptureAge')
        else:
            log_error(f"Player position for {player_name} not found.")
    except Exception as e:
        log_error(f"Error spectating player {player_name}: {e}")

def generate_heatmap(activity_counts, width, height):
    """
    Generates a heatmap based on activity counts.
    
    Args:
        activity_counts (dict): Dictionary with player names and their activity pixel counts.
        width (int): Width of the minimap or game area.
        height (int): Height of the minimap or game area.
    
    Returns:
        numpy.ndarray: Heatmap image.
    """
    heatmap = np.zeros((height, width), dtype=np.float32)
    for player, count in activity_counts.items():
        if count > 0:
            # Assign a weight based on activity count
            # Customize this as per your requirements
            heatmap += count
    # Normalize the heatmap
    heatmap = cv2.normalize(heatmap, None, 0, 255, cv2.NORM_MINMAX)
    heatmap = heatmap.astype(np.uint8)
    return heatmap

def display_heatmap(heatmap):
    """
    Displays the heatmap using matplotlib and seaborn.
    
    Args:
        heatmap (numpy.ndarray): Heatmap image.
    """
    try:
        plt.figure(figsize=(10, 8))
        sns.heatmap(heatmap, cmap='hot', linewidths=0.5)
        plt.title('Activity Heatmap')
        plt.xlabel('X-axis')
        plt.ylabel('Y-axis')
        plt.show(block=False)
        plt.pause(0.001)  # Brief pause to allow the plot to render
    except Exception as e:
        log_error(f"Error displaying heatmap: {e}")

def process_activity():
    """
    Continuously captures the minimap, detects player activity, identifies blinking icons,
    and prioritizes spectating blinking players.
    """
    global game_state
    prev_activity = {}
    blink_cooldowns = {player: 0 for player in game_state.config['PLAYER_HSV_RANGES'].keys()}
    while True:
        try:
            # Capture minimap
            minimap = capture_screen(
                (game_state.config['MINIMAP_X'],
                 game_state.config['MINIMAP_Y'],
                 game_state.config['MINIMAP_X'] + game_state.config['MINIMAP_WIDTH'],
                 game_state.config['MINIMAP_Y'] + game_state.config['MINIMAP_HEIGHT'])
            )
            if minimap is None:
                log_error("Failed to capture minimap.")
                time.sleep(1)
                continue

            # Detect player activity
            current_activity = detect_player_activity(minimap, game_state.config['PLAYER_HSV_RANGES'])
            log_info(f"Player Activity: {current_activity}")

            # Detect blinking icons
            blinking_players = detect_blinking_icons(prev_activity, current_activity)
            current_time = time.time()
            for player in blinking_players:
                if current_time >= blink_cooldowns[player]:
                    log_info(f"Blinking Player Detected: {player}")
                    spectate_player(player)
                    blink_cooldowns[player] = current_time + 5  # 5-second cooldown

            prev_activity = current_activity
            time.sleep(1)  # Adjust the interval as needed
        except Exception as e:
            log_error(f"Error in process_activity: {e}")
            time.sleep(1)

def generate_and_display_heatmap_loop():
    """
    Continuously captures the minimap, generates heatmaps based on activity, and displays them.
    """
    global game_state
    while True:
        try:
            # Capture minimap
            minimap = capture_screen(
                (game_state.config['MINIMAP_X'],
                 game_state.config['MINIMAP_Y'],
                 game_state.config['MINIMAP_X'] + game_state.config['MINIMAP_WIDTH'],
                 game_state.config['MINIMAP_Y'] + game_state.config['MINIMAP_HEIGHT'])
            )
            if minimap is None:
                log_error("Failed to capture minimap for heatmap.")
                time.sleep(5)
                continue

            # Detect player activity
            current_activity = detect_player_activity(minimap, game_state.config['PLAYER_HSV_RANGES'])
            log_info(f"Player Activity for Heatmap: {current_activity}")

            # Generate heatmap
            heatmap = generate_heatmap(current_activity, game_state.config['MINIMAP_WIDTH'], game_state.config['MINIMAP_HEIGHT'])

            # Display heatmap
            display_heatmap(heatmap)

            time.sleep(5)  # Update every 5 seconds
        except Exception as e:
            log_error(f"Error in generate_and_display_heatmap_loop: {e}")
            time.sleep(5)

def update_player_positions(minimap_image, player_hsv_ranges):
    """
    Updates the player's positions based on color detection.
    
    Args:
        minimap_image (numpy.ndarray): Captured minimap image in BGR format.
        player_hsv_ranges (dict): Dictionary containing HSV lower and upper bounds for each player.
    """
    try:
        hsv_image = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2HSV)
    except Exception as e:
        log_error(f"Error converting minimap to HSV for position update: {e}")
        return

    for player, hsv_range in player_hsv_ranges.items():
        lower = np.array(hsv_range['lower'], dtype=np.uint8)
        upper = np.array(hsv_range['upper'], dtype=np.uint8)
        mask = cv2.inRange(hsv_image, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            # Assume the largest contour corresponds to the player's position
            largest_contour = max(contours, key=cv2.contourArea)
            M = cv2.moments(largest_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                game_state.player_positions[player] = (cx, cy)
                log_info(f"Updated position for {player}: ({cx}, {cy})")
            else:
                log_error(f"Zero division error while calculating moments for {player}.")
        else:
            log_error(f"No contours found for {player}.")

def activity_and_position_updater():
    """
    Thread function to update player positions and handle activity.
    """
    global game_state
    prev_activity = {}
    blink_cooldowns = {player: 0 for player in game_state.config['PLAYER_HSV_RANGES'].keys()}
    while True:
        try:
            # Capture minimap
            minimap = capture_screen(
                (game_state.config['MINIMAP_X'],
                 game_state.config['MINIMAP_Y'],
                 game_state.config['MINIMAP_X'] + game_state.config['MINIMAP_WIDTH'],
                 game_state.config['MINIMAP_Y'] + game_state.config['MINIMAP_HEIGHT'])
            )
            if minimap is None:
                log_error("Failed to capture minimap for activity and position update.")
                time.sleep(1)
                continue

            # Update player positions
            update_player_positions(minimap, game_state.config['PLAYER_HSV_RANGES'])

            # Detect player activity
            current_activity = detect_player_activity(minimap, game_state.config['PLAYER_HSV_RANGES'])
            log_info(f"Player Activity: {current_activity}")

            # Detect blinking icons
            blinking_players = detect_blinking_icons(prev_activity, current_activity)
            current_time = time.time()
            for player in blinking_players:
                if current_time >= blink_cooldowns[player]:
                    log_info(f"Blinking Player Detected: {player}")
                    spectate_player(player)
                    blink_cooldowns[player] = current_time + 5  # 5-second cooldown

            prev_activity = current_activity
            time.sleep(1)  # Adjust the interval as needed
        except Exception as e:
            log_error(f"Error in activity_and_position_updater: {e}")
            time.sleep(1)

def start_spectate_logic_threads():
    """
    Initializes and starts the necessary threads for spectate logic.
    """
    # Thread for processing activity and spectating blinking players
    activity_thread = threading.Thread(target=activity_and_position_updater, daemon=True)
    activity_thread.start()
    log_info("Started activity and position updater thread.")

    # Thread for generating and displaying heatmaps
    heatmap_thread = threading.Thread(target=generate_and_display_heatmap_loop, daemon=True)
    heatmap_thread.start()
    log_info("Started heatmap generation thread.")

def detect_and_handle_events():
    """
    Placeholder for additional event detection and handling logic.
    """
    # Implement any additional event detection here
    pass

# Add more functions as needed for comprehensive spectate logic
