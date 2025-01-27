from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import logging
from typing import Tuple, Dict, Any, Optional
import pyautogui

def extract_player_info(player_element, row) -> Tuple[str, str]:
    """Extract player name and ELO rating.
    Args:
        player_element: The DOM element containing player info
        row: The parent row element containing the match info
    """
    try:
        name = player_element.query_selector("a").inner_text()
        
        # Try to get individual player ELO first
        elo_element = player_element.query_selector("div.w-9")
        if elo_element:
            elo = elo_element.inner_text()
        else:
            # Fallback to average ELO
            avg_elo = row.query_selector("td:nth-child(4)").inner_text()
            elo = avg_elo if avg_elo else ""
            
        return name, elo.strip()
    except Exception as e:
        logging.error(f"Error extracting player info: {e}")
        return "", ""

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
        page.goto(config['AOE2_COMPANION_URL'])

        page.wait_for_selector("table tbody tr", timeout=20000)
        logging.info("Matches table loaded.")

        while True:
            match_rows = page.query_selector_all("table tbody tr")
            logging.info(f"Found {len(match_rows)} potential matches to check.")
            
            for row in match_rows:
                try:
                    expand_button = row.query_selector("td.py-4.pl-6 svg")
                    if not expand_button:
                        continue

                    match_text = row.inner_text()
                    logging.info(f"Checking match: {match_text}")
                    
                    if "AUTOMATCH" not in match_text or "Random Map" not in match_text:
                        continue
                    
                    # Get average ELO from the row
                    avg_elo = row.query_selector("td:nth-child(4)").inner_text().strip()

                    match_info = {
                        'map': match_text.split('\n')[0],
                        'mode': 'AUTOMATCH',
                        'game_type': 'Random Map',
                        'server': match_text.split()[-2] if '~' in match_text else None,
                        'avg_elo': avg_elo
                    }

                    expand_button.click()
                    time.sleep(1)

                    players = page.query_selector_all(
                        "tr > td:nth-child(2) > div > div > div > div"
                    )
                    player_count = len(players) if players else 0

                    if player_count == 2:
                        player_names = []
                        player_elos = []

                        for player in players:
                            name, elo = extract_player_info(player, row)
                            if name:
                                player_names.append(name)
                                player_elos.append(elo)

                        match_info['players'] = player_names
                        match_info['elos'] = player_elos

                        spectate_button = row.query_selector("button:has-text('Spectate')")
                        if spectate_button:
                            spectate_button.click()
                            time.sleep(1.5)
                            pyautogui.press('tab')
                            time.sleep(0.1)
                            pyautogui.press('tab')
                            time.sleep(0.1)
                            pyautogui.press('enter')
                            time.sleep(4)
                            # Let calling code handle window switching
                            logging.info(f"Found match with info: {match_info}")
                            return True, match_info

                    expand_button.click()
                    time.sleep(0.5)

                except Exception as e:
                    logging.error(f"Error checking match: {e}")
                    continue

            page.reload()
            time.sleep(5)

    except PlaywrightTimeoutError:
        logging.error("Timed out waiting for matches table")
        return False, {}
    except Exception as e:
        logging.error(f"Error during automation: {e}")
        return False, {}
    finally:
        try:
            browser.close()
        except:
            pass

    return False, {}