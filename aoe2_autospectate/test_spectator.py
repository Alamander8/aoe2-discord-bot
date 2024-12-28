import time
import logging
import argparse
import cv2
import numpy as np
from autospectate.spectator_core import SpectatorCore
from autospectate.config import (
    MINIMAP_X, MINIMAP_Y, MINIMAP_WIDTH, MINIMAP_HEIGHT,
    GAME_AREA_X, GAME_AREA_Y, GAME_AREA_WIDTH, GAME_AREA_HEIGHT,
    PLAYER_HSV_RANGES, GAME_AGES, MINIMAP_PADDING
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
        
        # Generate territory visualization if in debug mode
        if spectator.debug_mode:
            spectator.territory_tracker.visualize_territories(minimap)
            logging.info("Territory visualization saved")
    else:
        logging.error("[FAIL] Minimap capture failed")

def test_territory_detection(spectator):
    """Test territory and heat map generation"""
    logging.info("Testing territory detection...")
    
    minimap = spectator.capture_minimap()
    if minimap is not None:
        # Update territory tracker
        spectator.territory_tracker.update(minimap, spectator.player_colors_config, spectator.active_colors)
        
        # Log territory information
        for color in spectator.active_colors:
            territory = spectator.territory_tracker.territories.get(color, {})
            if territory.get('main_base'):
                logging.info(f"{color} main base detected at {territory['main_base']['position']}")
            
            forward_positions = territory.get('forward_positions', [])
            logging.info(f"{color} has {len(forward_positions)} forward positions")
            
        # Generate heat map visualization
        if spectator.territory_tracker.heat_map is not None:
            heat_vis = (spectator.territory_tracker.heat_map * 255).astype(np.uint8)
            heat_vis = cv2.applyColorMap(heat_vis, cv2.COLORMAP_JET)
            cv2.imwrite('debug_heatmap.png', heat_vis)
            logging.info("Heat map visualization saved")

def test_raid_detection(spectator):
    """Test raid detection system"""
    logging.info("Testing raid detection...")
    
    minimap = spectator.capture_minimap()
    if minimap is not None:
        # Update territory understanding
        spectator.territory_tracker.update(minimap, spectator.player_colors_config, spectator.active_colors)
        
        # Check for raids
        raids = spectator.territory_tracker.detect_raids(minimap, spectator.player_colors_config)
        
        if raids:
            logging.info(f"Detected {len(raids)} potential raids:")
            for raid in raids:
                logging.info(f"  - {raid['attacker']} raiding {raid['defender']} "
                           f"(importance: {raid['importance']:.2f})")
                           
            # Visualize raids on debug image
            debug_img = minimap.copy()
            for raid in raids:
                x, y = raid['position']
                cv2.circle(debug_img, (x, y), 15, (0, 0, 255), 2)
            cv2.imwrite('debug_raids.png', debug_img)
        else:
            logging.info("No raids detected")

def test_activity_detection(spectator):
    """Test activity detection between frames"""
    logging.info("Testing activity detection...")
    
    prev_minimap = spectator.capture_minimap()
    logging.info("Move units or camera to generate activity...")
    time.sleep(1)
    curr_minimap = spectator.capture_minimap()
    
    if prev_minimap is not None and curr_minimap is not None:
        # Detect regular activity
        new_zones = spectator.detect_activity_zones(curr_minimap)
        
        logging.info(f"Found {len(new_zones)} activity zones")
        
        # Visualize activity
        debug_image = curr_minimap.copy()
        for zone in new_zones:
            x, y = zone['position']
            color = (0, 255, 0) if zone['color'] == 'Blue' else (0, 0, 255)
            cv2.circle(debug_image, (x, y), int(zone['area'] ** 0.5), color, 2)
        
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
            
            # Run spectator logic
            spectator.run_spectator_iteration()
            
            # Log current status
            time_remaining = int(end_time - time.time())
            logging.info(f"Time remaining: {time_remaining}s")
            
            # Save debug visuals periodically if enabled
            if spectator.debug_mode and iteration % 10 == 0:
                minimap = spectator.capture_minimap()
                if minimap is not None:
                    spectator.territory_tracker.visualize_territories(minimap)
            
            time.sleep(0.5)
        
        logging.info(f"Test completed. Duration: {duration} seconds")
        
    except KeyboardInterrupt:
        logging.info("Test stopped by user")
    except Exception as e:
        logging.error(f"Error during timed test: {e}")

def main():
    parser = argparse.ArgumentParser(description='Test AoE2 Spectator functionality')
    parser.add_argument('--test-all', action='store_true', help='Run all tests')
    parser.add_argument('--test-capture', action='store_true', help='Test screen capture')
    parser.add_argument('--test-territories', action='store_true', help='Test territory detection')
    parser.add_argument('--test-raids', action='store_true', help='Test raid detection')
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
        'GAME_AGES': GAME_AGES
    })()
    
    spectator = SpectatorCore(config)
    spectator.debug_mode = args.debug_visual
    
    try:
        if args.timed_test:
            test_spectate_timed(spectator, args.timed_test)
            return
            
        if args.test_all or args.test_capture:
            test_screen_capture(spectator)
            
        if args.test_all or args.test_territories:
            test_territory_detection(spectator)
            
        if args.test_all or args.test_raids:
            test_raid_detection(spectator)
            
        if args.test_all or args.test_activity:
            test_activity_detection(spectator)
            
        if args.test_all or args.test_spectate:
            spectator.run_spectator()
            
    except KeyboardInterrupt:
        logging.info("Testing stopped by user")
    except Exception as e:
        logging.error(f"Error during testing: {e}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    main()