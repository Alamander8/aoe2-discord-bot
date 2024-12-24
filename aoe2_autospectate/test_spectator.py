import time
import logging
import argparse
import cv2
import numpy as np
from autospectate.spectator_core import SpectatorCore
from autospectate.config import (
    MINIMAP_X, MINIMAP_Y, MINIMAP_WIDTH, MINIMAP_HEIGHT,
    GAME_AREA_X, GAME_AREA_Y, GAME_AREA_WIDTH, GAME_AREA_HEIGHT,
    PLAYER_HSV_RANGES, GAME_AGES, MINIMAP_PADDING,
    BUILDING_ICON_MIN_AREA, BUILDING_ICON_MAX_AREA, BUILDING_ICON_MIN_CIRCULARITY,
    MAX_PLAYERS, EXPECTED_PLAYERS_1V1, STARTING_TC_COUNT,
    AOE2_COMPANION_URL, GAME_MODE_FILTER
)

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('spectator_test.log'),
            logging.StreamHandler()
        ]
    )

def test_screen_capture(spectator):
    """Test screen capture functionality"""
    logging.info("Testing screen capture...")
    
    minimap = spectator.capture_minimap()
    if minimap is not None:
        logging.info("[PASS] Minimap capture successful")
        cv2.imwrite('debug_minimap.png', minimap)
    else:
        logging.error("[FAIL] Minimap capture failed")
    
    game_area = spectator.capture_game_area()
    if game_area is not None:
        logging.info("[PASS] Game area capture successful")
        cv2.imwrite('debug_game_area.png', game_area)
    else:
        logging.error("[FAIL] Game area capture failed")





def test_color_detection(spectator):
    """Test color detection on current screen with visual debug"""
    logging.info("Testing color detection...")
    
    minimap = spectator.capture_minimap()
    if minimap is not None:
        active_players = spectator.detect_building_icons(minimap, debug=True)
        if active_players:
            logging.info("Detected players:")
            for player_name, buildings in active_players.items():
                for building in buildings:
                    logging.info(f"  - {player_name}: Position {building['position']}, "
                               f"Area {building['area']}, Type {building['type']}")
        else:
            logging.info("No player buildings detected")






def test_activity_detection(spectator):
    """Test activity detection between frames"""
    logging.info("Testing activity detection...")
    
    prev_minimap = spectator.capture_minimap()
    logging.info("Move units or camera to generate activity...")
    time.sleep(1)
    curr_minimap = spectator.capture_minimap()
    
    if prev_minimap is not None and curr_minimap is not None:
        contours, magnitude = spectator.detect_activity(prev_minimap, curr_minimap)
        logging.info(f"Activity magnitude: {magnitude}")
        logging.info(f"Number of activity contours: {len(contours)}")
        
        # Draw activity areas on debug image
        debug_image = curr_minimap.copy()
        cv2.drawContours(debug_image, contours, -1, (0, 255, 0), 2)
        cv2.imwrite('debug_activity.png', debug_image)

def test_spectate_timed(spectator, duration):
    """Run the spectator for a specified duration to observe behavior."""
    logging.info(f"Starting {duration}-second spectate test...")
    
    try:
        start_time = time.time()
        end_time = start_time + duration
        iteration = 0
        
        while time.time() < end_time:
            iteration += 1
            logging.info(f"Test iteration {iteration}")
            
            # Capture current state
            minimap = spectator.capture_minimap()
            game_area = spectator.capture_game_area()
            
            if minimap is None or game_area is None:
                logging.error("Failed to capture screen")
                continue
            
            # Detect buildings and active players
            active_players = spectator.detect_building_icons(minimap)
            if active_players:
                logging.info(f"Current active players: {list(active_players.keys())}")
            
            # Run spectator logic
            spectator.run_spectator_iteration()
            
            # Log current status
            time_remaining = int(end_time - time.time())
            logging.info(f"Time remaining: {time_remaining}s")
            
            # Short sleep to prevent excessive CPU usage
            time.sleep(0.5)
        
        # Log test results
        logging.info(f"Test completed. Duration: {duration} seconds")
        logging.info(f"Player switches: {spectator.player_switches}")
        logging.info(f"Fights detected: {spectator.fights_detected}")
        logging.info(f"Average activity level: {spectator.total_activity / duration:.2f}")
        
    except KeyboardInterrupt:
        logging.info("Test stopped by user")
    except Exception as e:
        logging.error(f"Error during timed test: {e}")

def main():
    parser = argparse.ArgumentParser(description='Test AoE2 Spectator functionality')
    parser.add_argument('--test-all', action='store_true', help='Run all tests')
    parser.add_argument('--test-capture', action='store_true', help='Test screen capture')
    parser.add_argument('--test-colors', action='store_true', help='Test color detection')
    parser.add_argument('--test-activity', action='store_true', help='Test activity detection')
    parser.add_argument('--test-spectate', action='store_true', help='Test spectate functionality')
    parser.add_argument('--timed-test', type=int, help='Run a timed test for specified seconds')
    parser.add_argument('--debug-visual', action='store_true', help='Save debug visualizations')
    
    args = parser.parse_args()
    setup_logging()
    
    # Create config object
    config = type('Config', (), {
        'MINIMAP_X': MINIMAP_X,
        'MINIMAP_Y': MINIMAP_Y,
        'MINIMAP_WIDTH': MINIMAP_WIDTH,
        'MINIMAP_HEIGHT': MINIMAP_HEIGHT,
        'MINIMAP_PADDING': MINIMAP_PADDING,
        'GAME_AREA_X': GAME_AREA_X,
        'GAME_AREA_Y': GAME_AREA_Y,
        'GAME_AREA_WIDTH': GAME_AREA_WIDTH,
        'GAME_AREA_HEIGHT': GAME_AREA_HEIGHT,
        'PLAYER_HSV_RANGES': PLAYER_HSV_RANGES,
        'GAME_AGES': GAME_AGES,
        'BUILDING_ICON_MIN_AREA': BUILDING_ICON_MIN_AREA,
        'BUILDING_ICON_MAX_AREA': BUILDING_ICON_MAX_AREA,
        'BUILDING_ICON_MIN_CIRCULARITY': BUILDING_ICON_MIN_CIRCULARITY,
        'MAX_PLAYERS': MAX_PLAYERS,
        'EXPECTED_PLAYERS_1V1': EXPECTED_PLAYERS_1V1,
        'STARTING_TC_COUNT': STARTING_TC_COUNT,
        'AOE2_COMPANION_URL': AOE2_COMPANION_URL,
        'GAME_MODE_FILTER': GAME_MODE_FILTER
    })()
    
    spectator = SpectatorCore(config)
    
    try:
        if args.timed_test:
            test_spectate_timed(spectator, args.timed_test)
            return
            
        if args.test_all or args.test_capture:
            test_screen_capture(spectator)
            
        if args.test_all or args.test_colors:
            test_color_detection(spectator)
            
        if args.test_all or args.test_activity:
            test_activity_detection(spectator)
            
        if args.test_all or args.test_spectate:
            # Regular spectate test
            spectator.run_spectator()
            
    except KeyboardInterrupt:
        logging.info("Testing stopped by user")
    except Exception as e:
        logging.error(f"Error during testing: {e}")

if __name__ == "__main__":
    main()