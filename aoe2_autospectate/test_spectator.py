import time
import logging
import argparse
import cv2
import numpy as np
from autospectate.spectator_core import SpectatorCore
from autospectate.config import (
    MINIMAP_X, MINIMAP_Y, MINIMAP_WIDTH, MINIMAP_HEIGHT,
    GAME_AREA_X, GAME_AREA_Y, GAME_AREA_WIDTH, GAME_AREA_HEIGHT,
    PLAYER_HSV_RANGES, GAME_AGES
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
        # Detect colors with debug visualization
        colors = spectator.detect_player_colors(minimap, debug=True)
        
        if colors:
            logging.info("Detected players:")
            for color_name, info in colors.items():
                logging.info(f"  - {color_name}: Position {info['position']}, "
                           f"Confidence {info['confidence']:.2f}%, Area {info['area']}")
        else:
            logging.info("No player colors detected")

def test_activity_detection(spectator):
    """Test activity detection between frames"""
    logging.info("Testing activity detection...")
    
    prev_minimap = spectator.capture_minimap()
    logging.info("Move units or camera to generate activity...")
    time.sleep(1)  # Wait for user to create some activity
    curr_minimap = spectator.capture_minimap()
    
    if prev_minimap is not None and curr_minimap is not None:
        contours, magnitude = spectator.detect_activity(prev_minimap, curr_minimap)
        logging.info(f"Activity magnitude: {magnitude}")
        logging.info(f"Number of activity contours: {len(contours)}")
        
        # Draw activity areas on debug image
        debug_image = curr_minimap.copy()
        cv2.drawContours(debug_image, contours, -1, (0, 255, 0), 2)
        cv2.imwrite('debug_activity.png', debug_image)

def test_spectate_action(spectator):
    """Test actual spectating functionality"""
    logging.info("Testing spectate action...")
    
    minimap = spectator.capture_minimap()
    if minimap is not None:
        colors = spectator.detect_player_colors(minimap)
        if colors:
            # Try to spectate each detected player
            for color_name, info in colors.items():
                logging.info(f"Attempting to spectate {color_name} at position {info['position']}")
                spectator.click_minimap(*info['position'])
                
                # Perform test drag action
                center_x = spectator.game_area_width // 2
                center_y = spectator.game_area_height // 2
                drag_distance = 100
                
                spectator.click_and_drag_follow(
                    center_x - drag_distance,
                    center_y - drag_distance,
                    center_x + drag_distance,
                    center_y + drag_distance,
                    duration=1.5
                )
                time.sleep(2)  # Wait between players
        else:
            logging.info("No players detected to spectate")

def main():
    parser = argparse.ArgumentParser(description='Test AoE2 Spectator functionality')
    parser.add_argument('--test-all', action='store_true', help='Run all tests')
    parser.add_argument('--test-capture', action='store_true', help='Test screen capture')
    parser.add_argument('--test-colors', action='store_true', help='Test color detection')
    parser.add_argument('--test-activity', action='store_true', help='Test activity detection')
    parser.add_argument('--test-spectate', action='store_true', help='Test spectate functionality')
    parser.add_argument('--debug-visual', action='store_true', help='Save debug visualizations')
    
    args = parser.parse_args()
    setup_logging()
    
    # Create config object
    config = type('Config', (), {
        'MINIMAP_X': MINIMAP_X,
        'MINIMAP_Y': MINIMAP_Y,
        'MINIMAP_WIDTH': MINIMAP_WIDTH,
        'MINIMAP_HEIGHT': MINIMAP_HEIGHT,
        'GAME_AREA_X': GAME_AREA_X,
        'GAME_AREA_Y': GAME_AREA_Y,
        'GAME_AREA_WIDTH': GAME_AREA_WIDTH,
        'GAME_AREA_HEIGHT': GAME_AREA_HEIGHT,
        'PLAYER_HSV_RANGES': PLAYER_HSV_RANGES,
        'GAME_AGES': GAME_AGES
    })()
    
    spectator = SpectatorCore(config)
    
    try:
        if args.test_all or args.test_capture:
            test_screen_capture(spectator)
            
        if args.test_all or args.test_colors:
            test_color_detection(spectator)
            
        if args.test_all or args.test_activity:
            test_activity_detection(spectator)
            
        if args.test_all or args.test_spectate:
            test_spectate_action(spectator)
            
    except KeyboardInterrupt:
        logging.info("Testing stopped by user")
    except Exception as e:
        logging.error(f"Error during testing: {e}")

if __name__ == "__main__":
    main()