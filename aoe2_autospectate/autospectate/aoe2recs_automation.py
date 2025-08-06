# Create new file: aoe2recs_automation.py

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import logging
import random

def find_and_spectate_aoe2recs(playwright, config):
    """
    Navigate to AoE2 Recs Dashboard and find a good match to spectate.
    This supports your "crowd favorites" feature better than AoE2 Companion.
    """
    try:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Go to the dashboard
        dashboard_url = "https://aoe2recs.com/dashboard/"
        page.goto(dashboard_url)
        print(f"Navigated to {dashboard_url}")
        
        # Wait for content to load
        time.sleep(5)
        
        # Look for ongoing matches - the exact selectors will need to be determined
        # by inspecting the page, but here's the general approach:
        
        # Option 1: Look for direct spectate links/buttons
        spectate_elements = page.query_selector_all("a[href*='spectate'], button:has-text('Spectate'), .spectate-button")
        
        if not spectate_elements:
            # Option 2: Look for match rows that might contain player names
            match_rows = page.query_selector_all(".match-row, .game-row, tr")
            
            if not match_rows:
                # Option 3: Look for any clickable elements that might represent matches
                potential_matches = page.query_selector_all("div[class*='match'], div[class*='game']")
                spectate_elements = potential_matches
        
        print(f"Found {len(spectate_elements)} potential matches")
        
        if not spectate_elements:
            print("No matches found on aoe2recs dashboard")
            browser.close()
            return False, {}
        
        # Find the best match based on your criteria
        best_match = find_best_match_aoe2recs(page, spectate_elements, config)
        
        if not best_match:
            print("No suitable matches found")
            browser.close()
            return False, {}
        
        # Extract match info before clicking
        match_info = extract_match_info_aoe2recs(page, best_match)
        
        # Take screenshot
        screenshot_path = "aoe2recs_page_screenshot.png"
        page.screenshot(path=screenshot_path)
        print(f"Screenshot saved as {screenshot_path}")
        
        # Click the match/spectate button
        best_match.click()
        print("Clicked spectate for best match")
        
        # Wait for game to load
        time.sleep(5)
        browser.close()
        
        return True, match_info
        
    except PlaywrightTimeoutError:
        print("Timeout waiting for aoe2recs dashboard to load")
        return False, {}
    except Exception as e:
        print(f"Error during aoe2recs automation: {e}")
        return False, {}

def find_best_match_aoe2recs(page, spectate_elements, config):
    """
    Find the best match based on your preferences.
    This is where you can implement "crowd favorites" logic.
    """
    
    # Define your favorite players (you can expand this list)
    crowd_favorites = [
        "hera", "viper", "liereyy", "tatoh", "daut", "jordan23", "villese",
        "hearttt", "modri", "slam", "capoch", "f1re", "miguelito", "barles"
    ]
    
    # Define minimum rating threshold
    min_rating = config.get('min_rating', 2000)
    
    best_match = None
    best_score = 0
    
    for element in spectate_elements:
        try:
            # Get the text content around this element to analyze
            # This will need adjustment based on actual page structure
            parent = element.locator("xpath=../..")  # Get parent container
            match_text = parent.text_content().lower()
            
            score = 0
            
            # Check for favorite players
            for favorite in crowd_favorites:
                if favorite.lower() in match_text:
                    score += 100  # High bonus for favorites
                    print(f"Found favorite player: {favorite}")
            
            # Check for high ratings (this logic will need refinement)
            # Look for numbers that might be ratings
            import re
            ratings = re.findall(r'\b([2-3]\d{3})\b', match_text)  # Find 2000-3999 range
            if ratings:
                avg_rating = sum(int(r) for r in ratings) / len(ratings)
                if avg_rating >= min_rating:
                    score += int((avg_rating - min_rating) / 10)  # Bonus for higher rating
                    print(f"Found high-rated match: {avg_rating}")
            
            # Prefer 1v1 matches (adjust based on your preference)
            if "1v1" in match_text or "1 v 1" in match_text:
                score += 20
                print("Found 1v1 match")
            
            # Avoid certain maps if you want (example)
            bad_maps = ["arena", "fortress"]  # Adjust based on your preferences
            for bad_map in bad_maps:
                if bad_map in match_text:
                    score -= 30
                    print(f"Penalized for map: {bad_map}")
            
            if score > best_score:
                best_score = score
                best_match = element
                print(f"New best match found with score: {score}")
        
        except Exception as e:
            print(f"Error analyzing match element: {e}")
            continue
    
    if best_match:
        print(f"Selected match with score: {best_score}")
    else:
        # Fallback: just pick the first match
        print("No scored matches found, using first available")
        best_match = spectate_elements[0] if spectate_elements else None
    
    return best_match

def extract_match_info_aoe2recs(page, match_element):
    """
    Extract player names, ratings, civilizations, etc. from the match.
    This will need adjustment based on the actual page structure.
    """
    try:
        # Get the container around the match
        parent = match_element.locator("xpath=../..")
        match_text = parent.text_content()
        
        # Try to extract player info - this will need refinement
        # based on actual HTML structure
        match_info = {
            'players': [],
            'elos': [],
            'map': 'Unknown',
            'server': 'Unknown',
            'civilizations': []
        }
        
        # Basic text parsing - you'll want to improve this
        # based on the actual structure of aoe2recs
        lines = match_text.split('\n')
        for line in lines:
            line = line.strip()
            if line:
                # Look for patterns that might be player names or ratings
                import re
                
                # Look for ratings (numbers in 1000-4000 range)
                ratings = re.findall(r'\b([1-4]\d{3})\b', line)
                match_info['elos'].extend(ratings)
                
                # This is very basic - you'll want to improve based on actual structure
                if len(match_info['players']) < 2 and line and not line.isdigit():
                    # Might be a player name
                    match_info['players'].append(line)
        
        # Ensure we have at least some basic info
        if not match_info['players']:
            match_info['players'] = ['Player 1', 'Player 2']
        if not match_info['elos']:
            match_info['elos'] = ['Unknown', 'Unknown']
        
        return match_info
        
    except Exception as e:
        print(f"Error extracting match info: {e}")
        return {
            'players': ['Player 1', 'Player 2'],
            'elos': ['Unknown', 'Unknown'],
            'map': 'Unknown',
            'server': 'Unknown',
            'civilizations': []
        }

# Enhanced configuration for crowd favorites
def create_aoe2recs_config():
    """Create configuration for aoe2recs matching"""
    return {
        'min_rating': 1300,  # Minimum average rating
        'crowd_favorites': [
            "hera", "viper", "liereyy", "tatoh", "daut", "jordan23", 
            "villese", "hearttt", "modri", "slam", "capoch", "f1re"
        ],
        'preferred_maps': ["arabia", "arena", "black forest"],
        'avoid_maps': ["nomad", "migration"],
        'prefer_1v1': True,
        'max_game_time': 5  # Don't spectate games longer than 20 minutes
    }