import requests
import time

# Define the base URL for the AoE2.net API
BASE_URL = "https://aoe2.net/api/player/matches"

# Function to fetch match history
def fetch_match_history(profile_id, count=10):
    params = {
        "game": "aoe2de",
        "profile_id": profile_id,
        "count": count
    }
    try:
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching match history: {e}")
        return None

# Function to display match history
def display_match_history(history):
    if not history:
        print("No match history found.")
        return

    for match in history:
        print(f"Match ID: {match.get('match_id', 'N/A')}")
        print(f"Players: {[player.get('name', 'N/A') for player in match.get('players', [])]}")
        print(f"ELOs: {[player.get('rating', 'N/A') for player in match.get('players', [])]}")
        print(f"Civilizations: {[player.get('civ', 'N/A') for player in match.get('players', [])]}")
        print(f"Map Type: {match.get('map_type', 'N/A')}")
        print(f"Started at: {match.get('started', 'N/A')} (timestamp)")
        print("-" * 40)

# Main function to run the script
def main():
    profile_id = 11539183  # Replace with the desired profile ID
    while True:
        print("Polling for match history...")
        history = fetch_match_history(profile_id)
        display_match_history(history)
        print("Sleeping for 60 seconds...\n")
        time.sleep(60)

if __name__ == "__main__":
    main()
