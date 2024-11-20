# autospectate/main.py

import time
import random
import threading
from autospectate.config import (
    AOE2_COMPANION_URL,
    PLAYER_HSV_RANGES,
    GAME_MODE_FILTER,
    GAME_AGES,
    MINIMAP_X,
    MINIMAP_Y,
    MINIMAP_WIDTH,
    MINIMAP_HEIGHT,
    GAME_AREA_X,
    GAME_AREA_Y,
    GAME_AREA_WIDTH,
    GAME_AREA_HEIGHT
)
from autospectate.game_state import game_state
from autospectate.web_automation import find_and_spectate_game
from autospectate.spectate_logic import (
    start_spectate_logic_threads
)
from autospectate.utils import (
    setup_logging,
    log_info,
    log_error,
    capture_screen,
    calculate_distance,
    click_position,
    drag_and_follow
)
from autospectate.windows_management import switch_to_window
from playwright.sync_api import sync_playwright

def update_game_age():
    for age, threshold in reversed(GAME_AGES):
        if game_state.GAME_TIME >= threshold:
            if game_state.current_age != age:
                game_state.current_age = age
                log_info(f"Game Age: {age}")
            break

def auto_spectate():
    global game_state
    start_time = time.time()
    prev_minimap = capture_screen(
        (game_state.config['MINIMAP_X'],
         game_state.config['MINIMAP_Y'],
         game_state.config['MINIMAP_X'] + game_state.config['MINIMAP_WIDTH'],
         game_state.config['MINIMAP_Y'] + game_state.config['MINIMAP_HEIGHT'])
    )
    prev_game_area = capture_screen(
        (game_state.config['GAME_AREA_X'],
         game_state.config['GAME_AREA_Y'],
         game_state.config['GAME_AREA_X'] + game_state.config['GAME_AREA_WIDTH'],
         game_state.config['GAME_AREA_Y'] + game_state.config['GAME_AREA_HEIGHT'])
    )

    # Start spectate logic threads
    start_spectate_logic_threads()

    with sync_playwright() as playwright:
        spectated, match_info = find_and_spectate_game(playwright, {
            'AOE2_COMPANION_URL': AOE2_COMPANION_URL,
            'GAME_MODE_FILTER': GAME_MODE_FILTER
        })
        if not spectated:
            log_error("No game spectated. Exiting.")
            return

        while True:
            try:
                current_time = time.time()
                game_state.GAME_TIME = int(current_time - start_time)

                # Update game age
                update_game_age()

                # Set permanent vision at 10 minutes (600 seconds)
                if game_state.GAME_TIME >= 600 and not game_state.vision_set:
                    # Implement set_permanent_vision logic if needed
                    # For example:
                    # set_permanent_vision()
                    game_state.vision_set = True
                    log_info("Set permanent vision")

                # Toggle stats every 10 seconds
                if current_time - game_state.last_stats_toggle_time >= 10:
                    # Implement toggle_stats logic if needed
                    # For example:
                    # toggle_stats()
                    game_state.last_stats_toggle_time = current_time
                    log_info("Toggled stats")

                # Capture current minimap and game area
                curr_minimap = capture_screen(
                    (game_state.config['MINIMAP_X'],
                     game_state.config['MINIMAP_Y'],
                     game_state.config['MINIMAP_X'] + game_state.config['MINIMAP_WIDTH'],
                     game_state.config['MINIMAP_Y'] + game_state.config['MINIMAP_HEIGHT'])
                )
                curr_game_area = capture_screen(
                    (game_state.config['GAME_AREA_X'],
                     game_state.config['GAME_AREA_Y'],
                     game_state.config['GAME_AREA_X'] + game_state.config['GAME_AREA_WIDTH'],
                     game_state.config['GAME_AREA_Y'] + game_state.config['GAME_AREA_HEIGHT'])
                )

                # Update player positions and handle activities in separate threads

                # Additional processing can be added here

                # Short sleep to prevent excessive CPU usage
                time.sleep(0.1)
            except Exception as e:
                log_error(f"An error occurred: {str(e)}")
                time.sleep(1)  # Wait a bit before trying again

if __name__ == "__main__":
    try:
        # Setup logging
        setup_logging('autospectate.log')

        log_info("Starting AoE2 Auto-Spectator. Press Ctrl+C to stop.")
        auto_spectate()
    except KeyboardInterrupt:
        log_info("Auto-Spectator stopped by user.")
    except Exception as e:
        from autospectate.utils import log_error
        log_error(f"Unexpected error: {e}")
