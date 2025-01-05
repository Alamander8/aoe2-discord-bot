from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import pyautogui
from windows_management import switch_to_window

def find_and_spectate_game(playwright, config):
    """
    Navigates to AoE2 Companion and finds a suitable 1v1 game to spectate.
    """
    try:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(
            permissions=["clipboard-read", "clipboard-write"],
            base_url=config['AOE2_COMPANION_URL'],
            bypass_csp=True,
            ignore_https_errors=True
        )
        
        page = context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())
        page.goto(config['AOE2_COMPANION_URL'])
        print(f"Navigated to {config['AOE2_COMPANION_URL']}")
        
        # Wait for the table to load
        page.wait_for_selector("table tbody tr", timeout=20000)
        print("Matches table loaded.")

        while True:
            match_rows = page.query_selector_all("table tbody tr")
            print(f"Found {len(match_rows)} potential matches to check.")
            
            for row in match_rows:
                try:
                    expand_button = row.query_selector("td.py-4.pl-6 svg")
                    if not expand_button:
                        continue

                    match_text = row.inner_text()
                    print(f"Checking match: {match_text}")
                    
                    if "AUTOMATCH" not in match_text or "Random Map" not in match_text:
                        continue
                    
                    match_info = {
                        'map': match_text.split('\n')[0],
                        'mode': 'AUTOMATCH',
                        'game_type': 'Random Map',
                        'server': match_text.split()[-2] if '~' in match_text else None
                    }
                    
                    expand_button.click()
                    time.sleep(1)
                    
                    players = page.query_selector_all(
                        "tr > td:nth-child(2) > div > div > div > div"
                    )
                    player_count = len(players) if players else 0
                    
                    player_names = []
                    if players:
                        for player in players:
                            name_element = player.query_selector("a")
                            if name_element:
                                name = name_element.inner_text()
                                if name:
                                    player_names.append(name)
                    
                    if player_count == 2:
                        match_info['players'] = player_names
                        spectate_button = row.query_selector("button:has-text('Spectate')")
                        if spectate_button:
                            spectate_button.click()
                            # Wait for dialog to appear
                            time.sleep(1.5)
                            # Press Tab twice and Enter once
                            pyautogui.press('tab')
                            time.sleep(0.1)
                            pyautogui.press('tab')
                            time.sleep(0.1)
                            pyautogui.press('enter')
                            
                            # Wait a bit for AoE2 to launch
                            time.sleep(8)
                            
                            # Switch to AoE2 window
                            switch_to_window("Age of Empires II: Definitive Edition")
                            
                            browser.close()
                            return True, match_info
                    
                    expand_button.click()
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"Error checking match: {e}")
                    continue
            
            page.reload()
            time.sleep(5)
            
    except PlaywrightTimeoutError:
        print("Timed out waiting for the matches table to load.")
        return False, {}
    except Exception as e:
        print(f"Error during Playwright automation: {e}")
        return False, {}
    finally:
        try:
            browser.close()
        except:
            pass
        
    return False, {}