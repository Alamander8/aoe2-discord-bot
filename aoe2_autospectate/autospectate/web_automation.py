# autospectate/web_automation.py

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time

def find_and_spectate_game(playwright, config):
    """
    Navigates to AoE2 Companion, finds the first Spectate button,
    takes a screenshot, and clicks the button.
    """
    try:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(config['AOE2_COMPANION_URL'])  # Changed from config.AOE2_COMPANION_URL
        print(f"Navigated to {config['AOE2_COMPANION_URL']}")  # Changed accordingly
        
        time.sleep(5)
        # Wait for the table to load
        page.wait_for_selector("table", timeout=20000)
        print("Matches table loaded.")
        
        # Find all Spectate buttons containing text 'Spectate'
        spectate_buttons = page.query_selector_all("button:has-text('Spectate')")
        print(f"Found {len(spectate_buttons)} Spectate buttons.")
        
        if not spectate_buttons:
            print("No Spectate buttons found.")
            browser.close()
            return False, {}
        
        # Take a screenshot before clicking
        screenshot_path = "spectate_page_screenshot.png"
        page.screenshot(path=screenshot_path)
        print(f"Screenshot taken and saved as {screenshot_path}")
        
        # Click the first Spectate button
        first_button = spectate_buttons[0]
        first_button.click()
        print("Clicked the first Spectate button.")
        
        # Wait for the game to load
        time.sleep(5)  # Adjust as necessary
        browser.close()
        return True, {"status": "Game spectated successfully"}
    
    except PlaywrightTimeoutError:
        print("Timed out waiting for the matches table to load.")
        return False, {}
    
    except Exception as e:
        print(f"Error during Playwright automation: {e}")
        return False, {}
