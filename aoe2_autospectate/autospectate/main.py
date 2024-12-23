import time
import logging
from playwright.sync_api import sync_playwright
from autospectate.spectator_core import SpectatorCore
from autospectate.config import (
    MINIMAP_X, MINIMAP_Y, MINIMAP_WIDTH, MINIMAP_HEIGHT,
    GAME_AREA_X, GAME_AREA_Y, GAME_AREA_WIDTH, GAME_AREA_HEIGHT,
    PLAYER_HSV_RANGES, GAME_AGES, AOE2_COMPANION_URL, GAME_MODE_FILTER
)
from autospectate.web_automation import find_and_spectate_game
from autospectate.windows_management import switch_to_window

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('autospectate.log'),
            logging.StreamHandler()
        ]
    )

def main():
    setup_logging()
    logging.info("Starting AoE2 Auto-Spectator")
    
    # Create config object for SpectatorCore
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

    try:
        with sync_playwright() as playwright:
            while True:  # Continuous operation loop
                try:
                    # Find and spectate a game
                    spectated, match_info = find_and_spectate_game(
                        playwright, 
                        {'AOE2_COMPANION_URL': AOE2_COMPANION_URL, 'GAME_MODE_FILTER': GAME_MODE_FILTER}
                    )
                    
                    if not spectated:
                        logging.error("Failed to find a game to spectate. Retrying in 60 seconds...")
                        time.sleep(60)
                        continue

                    # Switch to game window
                    switch_to_window('Age of Empires II: Definitive Edition')
                    time.sleep(2)  # Wait for window focus

                    # Initialize and run spectator
                    spectator = SpectatorCore(config)
                    spectator.run_spectator()

                except Exception as e:
                    logging.error(f"Error in main loop: {e}")
                    time.sleep(10)  # Wait before retrying

    except KeyboardInterrupt:
        logging.info("Auto-Spectator stopped by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()