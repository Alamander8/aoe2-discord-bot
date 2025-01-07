from playwright.sync_api import sync_playwright
from web_automation import find_and_spectate_game

def test_spectate_finder():
    config = {
        'AOE2_COMPANION_URL': 'https://www.aoe2companion.com/ongoing'
    }
    
    with sync_playwright() as playwright:
        success, details = find_and_spectate_game(playwright, config)
        print(f"Success: {success}")
        print(f"Details: {details}")

if __name__ == "__main__":
    test_spectate_finder()