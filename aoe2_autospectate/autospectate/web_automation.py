# autospectate/web_automation.py

import time
import re
import logging
import argparse
import subprocess
import sys
from typing import Dict, List, Optional, Tuple, Any
from playwright.sync_api import Page, ElementHandle, sync_playwright

logging.basicConfig(level=logging.INFO)



def get_rating_tier(rating):
    """Convert numeric rating to tier"""
    if not rating or rating == 0:
        return "?"
    
    if rating >= 1900:
        return "S"
    elif rating >= 1600:
        return "A"  
    elif rating >= 1300:
        return "B"
    elif rating >= 1000:
        return "C"
    elif rating >= 900:
        return "D"
    else:
        return "E"  # Below 900

def get_tier_description(tier):
    """Get a description for the tier - keeping it simple"""
    descriptions = {
        "S": "Pro",
        "A": "Elite", 
        "B": "Advanced",
        "C": "Average",
        "D": "Below Average",
        "E": "Beginner",
        "?": "Unknown"
    }
    return descriptions.get(tier, "Unknown")


def extract_player_info(player_element, row) -> Tuple[str, str, str]:
    """
    Extract player name, ELO, and civilization from a player element.
    Returns: (name, elo, civilization)
    """
    try:
        # Get player name from the link
        name_link = player_element.query_selector("a")
        if not name_link:
            return None, None, None
            
        name = name_link.inner_text().strip()
        
        # Get ELO from the following span
        elo = ""
        elo_span = player_element.query_selector("span.text-xs.text-gray-500")
        if elo_span:
            elo_text = elo_span.inner_text()
            elo_match = re.search(r'\((\d+)\)', elo_text)
            if elo_match:
                elo = elo_match.group(1)
        
        # Get civilization - look for flex container with civ info
        civilization = ""
        flex_container = player_element.query_selector("a.flex.flex-row.space-x-1.items-center")
        if flex_container:
            # Get all text content
            full_text = flex_container.inner_text().strip()
            # Remove the player name to get remaining text (civ name)
            remaining_text = full_text.replace(name, "").strip()
            civilization = remaining_text if remaining_text else ""
        
        return name, elo.strip(), civilization
        
    except Exception as e:
        logging.error(f"Error extracting player info: {e}")
        return None, None, None


def handle_spectate_with_modal(page, spectate_button, match_info):
    """
    Handle spectating with proper modal detection and interaction.
    Returns (success, spectate_url)
    """
    spectate_url = None
    
    # Method 1: Try to intercept the URL
    def handle_navigation(route):
        nonlocal spectate_url
        url = route.request.url
        logging.info(f"Navigation intercepted: {url}")
        
        if 'aoe2de://' in url:
            spectate_url = url
            logging.info(f"Found AoE2 URL: {spectate_url}")
            route.abort()  # Prevent navigation
        elif 'spectate' in url.lower() or 'game' in url.lower():
            # Log any spectate-related navigation
            logging.info(f"Spectate-related URL: {url}")
            route.continue_()
        else:
            route.continue_()
    
    # Set up interception
    page.route("**/*", handle_navigation)
    
    # Also listen for console messages that might contain the URL
    def handle_console(msg):
        nonlocal spectate_url
        text = msg.text
        if 'aoe2de://' in text:
            match = re.search(r'(aoe2de://[^\s"\']+)', text)
            if match:
                spectate_url = match.group(1)
                logging.info(f"Found URL in console: {spectate_url}")
    
    page.on("console", handle_console)
    
    # Click the spectate button
    logging.info("Clicking spectate button...")
    spectate_button.click()
    
    # Wait a bit for any URL interception
    time.sleep(1)
    
    # Remove route handler
    page.unroute("**/*")
    
    # If we got the URL, open it directly
    if spectate_url:
        logging.info(f"Opening URL directly: {spectate_url}")
        if sys.platform == "win32":
            # Use Windows start command
            subprocess.run(["cmd", "/c", "start", "", spectate_url], shell=False)
        return True, spectate_url
    
    # Method 2: Modal should be open now, try multiple approaches
    logging.info("No URL intercepted, trying to handle modal...")
    time.sleep(1)  # Ensure modal is fully rendered
    
    # Try different methods to find and click the button
    methods_tried = []
    
    # Method 2a: Check if there's an iframe with the modal
    try:
        frames = page.frames
        logging.info(f"Found {len(frames)} frames")
        for frame in frames:
            if frame != page.main_frame:
                # Check if this frame has the modal
                modal_text = frame.evaluate("() => document.body ? document.body.innerText : ''")
                if "Age of Empires" in modal_text:
                    logging.info("Found modal in iframe!")
                    # Try to click in the iframe
                    frame.get_by_text("Open Age of Empires URL Helper").click()
                    return True, None
    except Exception as e:
        methods_tried.append(f"iframe search: {e}")
    
    # Method 2b: Use JavaScript to find any element with the text
    try:
        result = page.evaluate("""
            () => {
                // Search all elements including shadow DOM
                function searchAllElements(root) {
                    const walker = document.createTreeWalker(
                        root,
                        NodeFilter.SHOW_ELEMENT,
                        null,
                        false
                    );
                    
                    let node;
                    const found = [];
                    while (node = walker.nextNode()) {
                        if (node.textContent && node.textContent.includes('Open Age of Empires URL Helper')) {
                            found.push({
                                tag: node.tagName,
                                class: node.className,
                                text: node.textContent.substring(0, 100),
                                clickable: node.onclick !== null || node.tagName === 'BUTTON'
                            });
                            
                            // Try to click it
                            if (node.click) {
                                node.click();
                                return {clicked: true, element: found[found.length - 1]};
                            }
                        }
                        
                        // Check shadow roots
                        if (node.shadowRoot) {
                            const shadowResults = searchAllElements(node.shadowRoot);
                            if (shadowResults.clicked) return shadowResults;
                        }
                    }
                    
                    return {clicked: false, elements: found};
                }
                
                return searchAllElements(document);
            }
        """)
        
        logging.info(f"JavaScript search result: {result}")
        if result.get('clicked'):
            return True, None
            
    except Exception as e:
        methods_tried.append(f"JavaScript search: {e}")
    
    # Method 2c: Try Playwright's text selector with wait
    try:
        # Wait for the element to appear
        open_button = page.wait_for_selector(
            "text=Open Age of Empires URL Helper", 
            timeout=3000,
            state="visible"
        )
        if open_button:
            logging.info("Found button with wait_for_selector")
            open_button.click()
            return True, None
    except Exception as e:
        methods_tried.append(f"wait_for_selector: {e}")
    
    # Method 2d: Screenshot and log what's visible
    try:
        # Take a screenshot for debugging
        screenshot_path = f"modal_debug_{int(time.time())}.png"
        page.screenshot(path=screenshot_path)
        logging.info(f"Screenshot saved to {screenshot_path}")
        
        # Get all visible text
        visible_text = page.evaluate("() => document.body.innerText")
        logging.info(f"Visible text length: {len(visible_text)}")
        if "Age of Empires" in visible_text:
            logging.info("'Age of Empires' found in page text")
            # Log a snippet around it
            idx = visible_text.find("Age of Empires")
            snippet = visible_text[max(0, idx-50):idx+100]
            logging.info(f"Context: ...{snippet}...")
    except Exception as e:
        methods_tried.append(f"screenshot/text dump: {e}")
    
    # Method 2e: Last resort - OS level automation
    try:
        import pyautogui
        logging.info("Trying pyautogui approach...")
        
        # The modal has focus on the checkbox by default
        # We need TWO tabs to get to the "Open" button:
        # First tab -> moves from checkbox to "Cancel" button
        # Second tab -> moves from "Cancel" to "Open Age of Empires URL Helper" button
        
        pyautogui.press('tab')
        time.sleep(0.3)
        pyautogui.press('tab')  # Second tab to reach the Open button
        time.sleep(0.3)
        pyautogui.press('enter')
        time.sleep(1)
        
        # Alternative: try with just Enter if we're already on the right button
        # pyautogui.press('enter')
        
        # Check if the game launched by looking for the game window
        try:
            import pygetwindow as gw
            aoe_windows = gw.getWindowsWithTitle("Age of Empires II")
            if aoe_windows:
                logging.info("Game window detected!")
                return True, None
        except:
            pass
            
    except Exception as e:
        methods_tried.append(f"pyautogui: {e}")
    
    logging.error(f"All methods failed. Tried: {methods_tried}")
    return False, None


def test_match(page, rows, row_index):
    """
    Test a single match to see if it's a valid 1v1.
    Note: rows is the list of all rows, row_index is the index to test
    """
    MAX_RETRIES = 3
    
    for attempt in range(MAX_RETRIES):
        try:
            # Re-query rows to avoid stale elements
            current_rows = page.query_selector_all('tbody tr')
            if row_index >= len(current_rows):
                logging.error(f"Row index {row_index} out of bounds")
                return {'error': 'Row not found', 'index': row_index}
            
            row = current_rows[row_index]
            
            # Get basic info from row
            match_info = extract_row_info(row, row_index)
            
            # Skip non-AUTOMATCH games immediately
            if match_info.get('mode') != 'AUTOMATCH':
                logging.info(f"Skipping non-AUTOMATCH game at index {row_index}")
                return match_info
            
            # Click expand button (the chevron icon cell)
            expand_cell = row.query_selector('td:first-child')
            if not expand_cell:
                logging.warning("No expand cell found")
                return match_info
            
            # Check if expand button is visible and clickable
            if not expand_cell.is_visible():
                logging.warning(f"Expand cell not visible for row {row_index}")
                continue
                
            # Click to expand with retry logic
            logging.info("Clicking to expand match...")
            try:
                expand_cell.click()
                time.sleep(1.5)  # Wait for expansion
            except Exception as e:
                if "Element is not attached to the DOM" in str(e) and attempt < MAX_RETRIES - 1:
                    logging.warning(f"DOM error on attempt {attempt + 1}, retrying...")
                    time.sleep(0.5)
                    continue
                elif "Element is not attached to the DOM" in str(e):
                    logging.error("DOM error persisted, refreshing page...")
                    page.reload()
                    page.wait_for_selector('tbody tr', timeout=10000)
                    return {'error': 'DOM refresh needed', 'index': row_index}
                else:
                    raise
            
            # Extract expanded data
            expanded_data = extract_expanded_data(page, row_index)
            match_info.update(expanded_data)
            
            # Determine if it's a 1v1
            match_info['is_1v1'] = check_if_1v1_expanded(expanded_data)
            
            logging.info(f"Match: {match_info.get('map')} - "
                       f"Players found: {len(match_info.get('players', []))} - "
                       f"Is 1v1: {match_info.get('is_1v1')}")
            
            # Click again to collapse
            try:
                expand_cell.click()
                time.sleep(0.5)
            except:
                pass
            
            return match_info
            
        except Exception as e:
            logging.error(f"Error testing match {row_index} (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return {'error': str(e), 'index': row_index}
            time.sleep(0.5)
    
    return {'error': 'Max retries exceeded', 'index': row_index}


def extract_row_info(row, index):
    """
    Extract basic info from table row.
    """
    info = {'row_index': index}
    
    try:
        # Map cell (column 2)
        map_cell = row.query_selector('td:nth-child(2)')
        if map_cell:
            # Map name from bold element
            map_elem = map_cell.query_selector('.font-bold')
            if map_elem:
                info['map'] = map_elem.inner_text().strip()
                logging.info(f"Map: {info['map']}")
            
            # Check for AUTOMATCH
            cell_text = map_cell.inner_text()
            info['mode'] = 'AUTOMATCH' if 'AUTOMATCH' in cell_text else 'Other'
            logging.info(f"Mode: {info['mode']}")
            
            # Game time
            time_match = re.search(r'(\d+)\s*min', cell_text)
            if time_match:
                info['minutes'] = int(time_match.group(1))
                logging.info(f"Game time: {info['minutes']} minutes")
        
        # Rating (column 4)
        rating_cell = row.query_selector('td:nth-child(4)')
        if rating_cell:
            rating_text = rating_cell.inner_text().strip()
            rating_match = re.search(r'~?(\d+)', rating_text)
            if rating_match:
                info['rating'] = int(rating_match.group(1))
                logging.info(f"Average rating: {info['rating']}")
        
        # Get spectate button reference
        info['spectate_button'] = row.query_selector('td:nth-child(6) button')
        
    except Exception as e:
        logging.error(f"Error extracting row info: {e}")
    
    return info


def extract_expanded_data(page, row_index):
    """
    Extract data from the expanded row content.
    """
    data = {
        'players': [],
        'elos': [],
        'civilizations': [],
        'player_count': 0
    }
    
    # List of all AoE2 civilizations to filter out when parsing player names
    CIVILIZATIONS = {
        'armenians', 'aztecs', 'berbers', 'bohemians', 'britons', 'bulgarians', 'burgundians',
        'burmese', 'byzantines', 'celts', 'chinese', 'cumans', 'dravidians',
        'ethiopians', 'franks', 'goths', 'gurjaras', 'hindustanis', 'huns',
        'incas', 'italians', 'japanese', 'jurchens', 'khmer', 'koreans',
        'lithuanians', 'magyars', 'malay', 'malians', 'mayans', 'mongols',
        'persians', 'poles', 'portuguese', 'romans', 'saracens', 'sicilians',
        'slavs', 'spanish', 'tatars', 'teutons', 'turks', 'vietnamese',
        'vikings', 'bengalis', 'georgians', 'khitans'
    }
    
    try:
        # Look for player elements in the expanded content
        # Target specific player containers to avoid confusion with civs
        player_containers = page.query_selector_all('div.flex.items-center.space-x-2')
        
        for container in player_containers:
            player_info = extract_player_info(container, None)
            if player_info and player_info[0]:  # If we got a valid name
                name, elo, civ = player_info
                
                # Double-check it's not a civilization name
                if name.lower() not in CIVILIZATIONS:
                    data['players'].append(name)
                    data['elos'].append(elo if elo else '?')
                    if civ:
                        data['civilizations'].append(civ)
                    logging.info(f"Found player: {name} (ELO: {elo})")
                    if civ:
                        logging.info(f"Found civilization: {civ}")
        
        # If no players found via containers, try profile links as fallback
        if not data['players']:
            profile_links = page.query_selector_all('a[href*="/profile/"]')
            
            for link in profile_links:
                try:
                    player_name = link.inner_text().strip()
                    
                    # Skip if it's a civilization name
                    if player_name.lower() in CIVILIZATIONS:
                        continue
                    
                    # Skip invalid names
                    if not player_name or len(player_name) > 30:
                        continue
                    
                    # Avoid duplicates
                    if player_name not in data['players']:
                        data['players'].append(player_name)
                        
                        # Try to find ELO
                        parent = link.evaluate_handle("el => el.parentElement").as_element()
                        if parent:
                            parent_text = parent.inner_text()
                            elo_match = re.search(r'\((\d+)\)', parent_text)
                            if elo_match:
                                data['elos'].append(elo_match.group(1))
                                logging.info(f"Found player: {player_name} (ELO: {elo_match.group(1)})")
                            else:
                                data['elos'].append('?')
                                logging.info(f"Found player: {player_name} (ELO: ?)")
                        
                except Exception as e:
                    continue
        
        # Look for civilization images separately if needed
        if len(data['civilizations']) < len(data['players']):
            civ_images = page.query_selector_all('img[src*="/civilizations/"]')
            for img in civ_images[:2]:  # Only first 2 for 1v1
                try:
                    src = img.get_attribute('src')
                    civ_match = re.search(r'/civilizations/([^/]+)\.', src)
                    if civ_match:
                        civ_name = civ_match.group(1).replace('_', ' ').title()
                        if civ_name not in data['civilizations']:
                            data['civilizations'].append(civ_name)
                            logging.info(f"Found civilization: {civ_name}")
                except:
                    continue
        
        data['player_count'] = len(data['players'])
        logging.info(f"Final extraction: {data['player_count']} players, {len(data['civilizations'])} civs")
        logging.info(f"Players: {data['players']}")
        logging.info(f"Civilizations: {data['civilizations']}")
        
    except Exception as e:
        logging.error(f"Error extracting expanded data: {e}")
    
    return data


def check_if_1v1_expanded(expanded_data):
    """
    Determine if match is 1v1 based on expanded data.
    """
    # Check by player count
    player_count = expanded_data.get('player_count', 0)
    
    if player_count == 2:
        logging.info("✓ Confirmed 1v1 by player count (2 players)")
        return True
    elif player_count > 2:
        logging.info(f"✗ Not a 1v1 - found {player_count} players")
        return False
    else:
        logging.info(f"? Could not determine - found {player_count} players")
        return False


def find_and_spectate_game(playwright, config, test_mode=False):
    """
    Main function to find and spectate a 1v1 game.
    """
    MIN_RATING = config.get('MIN_RATING', 1100)  # Configurable minimum rating
    MATCHES_BEFORE_REFRESH = 10
    
    browser = None
    try:
        # Launch browser with specific args to handle protocol handlers
        browser = playwright.chromium.launch(
            headless=False,
            args=[
                '--disable-features=PromptOnMultipleDownload',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        # Create context with permissions
        context = browser.new_context(
            permissions=['clipboard-read', 'clipboard-write'],
            bypass_csp=True,
        )
        
        # Register protocol handler if possible
        page = context.new_page()
        
        # Try to pre-register the protocol handler
        try:
            page.add_init_script("""
                if (navigator.registerProtocolHandler) {
                    navigator.registerProtocolHandler('aoe2de', 'https://www.aoe2companion.com/handle/%s', 'Age of Empires');
                }
            """)
        except:
            pass
        
        # Navigate to the page
        url = config.get('AOE2_COMPANION_URL', 'https://www.aoe2companion.com/ongoing')
        page.goto(url, wait_until='networkidle')
        time.sleep(2)
        
        # Wait for matches to load
        page.wait_for_selector('tbody tr', timeout=10000)
        
        # Find all match rows
        rows = page.query_selector_all('tbody tr')
        logging.info(f"Found {len(rows)} matches")
        
        matches_checked = 0
        
        # Check each match
        for i in range(len(rows)):
            matches_checked += 1
            
            # Refresh page if we've checked too many
            if matches_checked >= MATCHES_BEFORE_REFRESH:
                logging.info("Refreshing page to get new matches...")
                page.reload()
                page.wait_for_selector('tbody tr', timeout=10000)
                rows = page.query_selector_all('tbody tr')
                matches_checked = 0
                i = 0  # Reset to start
                continue
            
            try:
                match = test_match(page, rows, i)
                
                # Skip if error or DOM refresh needed
                if match.get('error'):
                    if match['error'] == 'DOM refresh needed':
                        # Page was refreshed, restart from beginning
                        rows = page.query_selector_all('tbody tr')
                        i = 0
                        matches_checked = 0
                    continue
                
                # Skip non-automatch
                if match.get('mode') != 'AUTOMATCH':
                    continue
                
                # Skip if below minimum rating
                if match.get('rating', 0) < MIN_RATING:
                    logging.info(f"Skipping low-rated match: {match.get('rating')}")
                    continue
                
                # If it's a valid 1v1, spectate it immediately
                if match.get('is_1v1'):
                    logging.info(f"Found valid 1v1: {match.get('map')} - Rating: {match.get('rating')}")
                    
                    # Re-query and find the spectate button
                    rows = page.query_selector_all('tbody tr')
                    if match['row_index'] < len(rows):
                        spectate_button = rows[match['row_index']].query_selector('td:nth-child(6) button')
                        if spectate_button:
                            logging.info(f"Spectating match: {match.get('map')} - Rating: {match.get('rating')}")
                            
                            # Use the modal handler
                            success, url = handle_spectate_with_modal(page, spectate_button, match)
                            if success:
                                time.sleep(3)  # Wait for game to launch
                                context.close()
                                browser.close()
                                return True, format_match_for_obs(match)
                            else:
                                logging.error("Failed to handle spectate modal")
                
            except Exception as e:
                logging.error(f"Error checking match {i}: {e}")
                continue
        
        context.close()
        browser.close()
        return False, {"reason": "No suitable 1v1 matches found"}
        
    except Exception as e:
        logging.error(f"Error: {e}")
        if browser:
            browser.close()
        return False, {"reason": str(e)}

def format_match_for_obs(match):
    """
    Format match data for OBS display.
    """
    # Ensure we have exactly 2 values for everything
    players = match.get('players', [])
    elos = match.get('elos', [])
    civilizations = match.get('civilizations', [])
    
    # Pad with defaults if needed
    while len(players) < 2:
        players.append(f'Player {len(players) + 1}')
    while len(elos) < 2:
        elos.append('1000')
    while len(civilizations) < 2:
        civilizations.append('Unknown')
    
    # Get tier based on average rating
    rating = match.get('rating', 0)
    tier = get_rating_tier(rating)
    tier_desc = get_tier_description(tier)
    
    return {
        'players': players[:2],
        'elos': elos[:2],
        'map': match.get('map', 'Unknown'),
        'civilizations': civilizations[:2],
        'game_time': f"{match.get('minutes', 0)} min",
        'rating': rating,
        'tier': tier,
        'tier_description': tier_desc,
        'likely_1v1': True
    }


# Test function for debugging
def test_automation(config):
    """Test the automation without spectating."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        
        url = config.get('AOE2_COMPANION_URL', 'https://www.aoe2companion.com/ongoing')
        page.goto(url, wait_until='networkidle')
        time.sleep(2)
        
        rows = page.query_selector_all('tbody tr')
        logging.info(f"Found {len(rows)} matches")
        
        # Test first few matches
        for i in range(min(5, len(rows))):
            match = test_match(page, rows, i)
            print(f"\nMatch {i}: {match}")
        
        browser.close()


# Allow running in test mode from command line
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Run in test mode')
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s:%(name)s:%(message)s'
    )
    
    config = {
        'AOE2_COMPANION_URL': 'https://www.aoe2companion.com/ongoing',
        'MIN_RATING': 1200  # Minimum rating to consider
    }
    
    if args.test:
        test_automation(config)
    else:
        with sync_playwright() as p:
            success, result = find_and_spectate_game(p, config)
            print(f"Success: {success}")
            print(f"Result: {result}")