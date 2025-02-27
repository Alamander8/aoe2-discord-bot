from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import logging
from typing import Tuple, Dict, Any, Optional
import pyautogui
from config import MIN_GAME_ELO

def extract_player_info(player_element, row) -> Tuple[str, str, str]:
    """Extract player name, ELO rating, and civilization.
    
    Args:
        player_element: The DOM element containing player info
        row: The parent row element containing the match info
        
    Returns:
        Tuple[str, str, str]: (player_name, elo, civilization)
    """
    try:
        # Extract name 
        name_element = player_element.query_selector("a")
        if not name_element:
            return "", "", ""
        name = name_element.inner_text()
        
        # Extract ELO
        elo_element = player_element.query_selector("div.w-9")
        if elo_element:
            elo = elo_element.inner_text()
        else:
            # Fallback to average ELO
            avg_elo = row.query_selector("td:nth-child(4)").inner_text()
            elo = avg_elo if avg_elo else ""
        
        # Extract civilization using the more reliable flex container method
        civilization = "Unknown"
        flex_container = player_element.query_selector("a.flex.flex-row.space-x-1.items-center")
        if flex_container:
            all_text = flex_container.inner_text()
            civ_text = all_text.replace(name, '').strip()
            if civ_text:
                civilization = civ_text
        
        logging.debug(f"Extracted info - Name: {name}, ELO: {elo}, Civ: {civilization}")    
        return name, elo.strip(), civilization
    except Exception as e:
        logging.error(f"Error extracting player info: {e}")
        return "", "", ""

def find_and_spectate_game(playwright, config) -> Tuple[bool, Dict[str, Any]]:
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
        
        min_elo = config.get('MIN_GAME_ELO', 1000)  # Get minimum ELO from config, default to 0
        logging.info(f"Looking for games with minimum average ELO of {min_elo}")

        while True:
            page.goto(config['AOE2_COMPANION_URL'])
            page.wait_for_selector("table tbody tr", timeout=20000)
            logging.info("Matches table loaded.")

            match_rows = page.query_selector_all("table tbody tr")
            logging.info(f"Found {len(match_rows)} potential matches to check.")
            
            for row in match_rows:
                try:
                    # Make sure row is attached and visible before proceeding
                    if not row.is_visible():
                        continue

                    # Get and validate match text before proceeding
                    match_text = row.inner_text()
                    if not match_text:
                        continue

                    logging.info(f"Checking match: {match_text}")
                    
                    # Validate it's an AUTOMATCH Random Map game
                    if "AUTOMATCH" not in match_text or "Random Map" not in match_text:
                        continue
                    
                    # Find and validate expand button
                    expand_button = row.query_selector("td.py-4.pl-6 svg")
                    if not expand_button or not expand_button.is_visible():
                        continue

                    # Get average ELO first
                    elo_cell = row.query_selector("td:nth-child(4)")
                    if not elo_cell:
                        continue
                    avg_elo = elo_cell.inner_text().strip()
                    
                    # Check if game meets minimum ELO requirement
                    try:
                        avg_elo_num = int(''.join(filter(str.isdigit, avg_elo)))
                        if avg_elo_num < min_elo:
                            logging.info(f"Skipping game with average ELO {avg_elo_num} (minimum: {min_elo})")
                            continue
                    except ValueError:
                        logging.warning(f"Could not parse average ELO: {avg_elo}")
                        continue

                    # Collect basic match info
                    match_info = {
                        'map': match_text.split('\n')[0],
                        'mode': 'AUTOMATCH',
                        'game_type': 'Random Map',
                        'server': match_text.split()[-2] if '~' in match_text else None,
                        'avg_elo': avg_elo
                    }

                    # Click expand with retry
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            expand_button.click()
                            time.sleep(1)
                            break
                        except Exception as e:
                            if attempt == max_retries - 1:
                                raise
                            time.sleep(0.5)
                            continue

                    # Wait for player info to be visible
                    player_rows = page.query_selector_all(
                        "tr > td:nth-child(2) > div > div > div > div"
                    )

                    if len(player_rows) == 2:  # Ensure it's a 1v1
                        player_names = []
                        player_elos = []
                        civilizations = []

                        # Extract player info
                        for player in player_rows:
                            try:
                                name, elo, civ = extract_player_info(player, row)
                                if name:
                                    player_names.append(name)
                                    player_elos.append(elo)
                                    civilizations.append(civ if civ else "Unknown")
                            except ValueError:
                                logging.warning(f"Skipping player due to data extraction error")
                                continue

                        if len(player_names) == 2:  # Only proceed if we got both players
                            match_info['players'] = player_names
                            match_info['elos'] = player_elos
                            match_info['civilizations'] = civilizations

                            spectate_button = row.query_selector("button:has-text('Spectate')")
                            if spectate_button and spectate_button.is_visible():
                                spectate_button.click()
                                time.sleep(1.5)
                                pyautogui.press('tab')
                                time.sleep(0.1)
                                pyautogui.press('tab')
                                time.sleep(0.1)
                                pyautogui.press('enter')
                                time.sleep(4)
                                logging.info(f"Found match with info: {match_info}")
                                return True, match_info

                    # Close expanded row if we didn't spectate
                    expand_button.click()
                    time.sleep(0.5)

                except Exception as e:
                    logging.error(f"Error checking match: {e}")
                    continue

            logging.info("No suitable matches found, refreshing page...")
            time.sleep(5)

    except Exception as e:
        logging.error(f"Error during automation: {e}")
        return False, {}
    finally:
        try:
            browser.close()
        except:
            pass

    return False, {}


def test_extract_player_info():
    """
    Test the player info extraction independently of the main spectate flow.
    Run this with a known match page to verify extraction.
    """
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            
            # Navigate to a specific match page
            page.goto("https://www.aoe2companion.com/ongoing")
            page.wait_for_selector("table tbody tr", timeout=20000)
            
            # Get first match row
            row = page.query_selector("table tbody tr")
            if not row:
                print("No matches found to test")
                return
                
            # Expand the row
            expand_button = row.query_selector("td.py-4.pl-6 svg")
            if expand_button:
                expand_button.click()
                time.sleep(1)
                
                # Get player elements
                players = page.query_selector_all(
                    "tr > td:nth-child(2) > div > div > div > div"
                )
                
                print("\nExtracted player information:")
                print("-" * 50)
                
                for i, player in enumerate(players, 1):
                    name, elo, civ = extract_player_info(player, row)
                    print(f"Player {i}:")
                    print(f"  Name: {name}")
                    print(f"  ELO: {elo}")
                    print(f"  Civilization: {civ}")
                    print()
                    
            browser.close()
            
    except Exception as e:
        print(f"Test error: {e}")

if __name__ == "__main__":
    test_extract_player_info()