# Age of Empires II Discord Bot

This is a Discord bot that provides detailed information about Age of Empires II civilizations, matchup insights, and player winrate profiles. The bot uses data from a JSON file for civilizations and can integrate with external APIs to fetch player profiles.

## Features

- Get information about any Age of Empires II civilization.
- Get matchup insights between two civilizations.
- Fetch player winrate profiles (placeholder function, replace with real API calls).

## Commands

- `!civ <civilization>`: Get information about a specific civilization.
- `!matchup <civ1> vs <civ2>`: Get matchup insights between two civilizations.
- `!profile <player_name>`: Get player profile information (placeholder, needs real API).

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/yourusername/aoe2-discord-bot.git
    cd aoe2-discord-bot
    ```

2. Install the required packages:

    ```bash
    pip install -r requirements.txt
    ```

3. Create a `aoe2_data.json` file in the same directory as `main.py` with civilization data. Here is an example:

    ```json
    {
        "khmer": {
            "bonuses": [
                "Farmers do not require Mills or Town Centers to drop off food.",
                "Battle Elephants move 15% faster."
            ],
            "unique_units": [
                "Ballista Elephant"
            ],
            "hidden_stats": [
                "Ballista Elephants deal trample damage."
            ]
        },
        "roman": {
            "bonuses": [
                "Buildings are 10% cheaper in the Feudal Age, 15% cheaper in the Castle Age, and 20% cheaper in the Imperial Age."
            ],
            "unique_units": [
                "Legionary"
            ],
            "hidden_stats": [
                "Legionaries have increased armor against ranged attacks."
            ]
        }
    }
    ```

4. Replace `your_discord_bot_token` in `main.py` with your actual Discord bot token.

5. Run the bot:

    ```bash
    python main.py
    ```
