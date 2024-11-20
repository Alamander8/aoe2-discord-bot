# autospectate/config.py

import os

# URLs
AOE2_COMPANION_URL = 'https://www.aoe2companion.com/ongoing'

# Spectate Criteria
GAME_MODE_FILTER = 'Random Map'

# Player Colors (BGR)
# Define HSV color ranges for players
PLAYER_HSV_RANGES = {
    'Blue': {
        'lower': (100, 150, 0),
        'upper': (140, 255, 255)
    },
    'Red': {
        'lower': (0, 150, 70),
        'upper': (10, 255, 255)
    },
    'Green': {
        'lower': (40, 70, 70),
        'upper': (80, 255, 255)
    },
    'Yellow': {
        'lower': (25, 150, 150),
        'upper': (35, 255, 255)
    },
    'Cyan': {
        'lower': (85, 150, 150),
        'upper': (95, 255, 255)
    },
    'Purple': {
        'lower': (130, 100, 100),
        'upper': (160, 255, 255)
    },
    'Gray': {
        'lower': (0, 0, 50),
        'upper': (180, 50, 200)
    },
    'Orange': {
        'lower': (15, 150, 150),
        'upper': (25, 255, 255)
    }
}


# Game Ages and Thresholds
GAME_AGES = [
    ('Dark Age', 0),
    ('Feudal Age', 600),
    ('Castle Age', 1200),
    ('Imperial Age', 1800)
]

# Screen Coordinates (Adjust according to your screen resolution)
MINIMAP_X = 860
MINIMAP_Y = 860
MINIMAP_WIDTH = 200
MINIMAP_HEIGHT = 200

GAME_AREA_X = 0
GAME_AREA_Y = 0
GAME_AREA_WIDTH = 1920  # Example resolution width
GAME_AREA_HEIGHT = 1080  # Example resolution height

# Building Templates Paths
# autospectate/config.py


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BUILDING_TEMPLATES = {
    'Town Center': os.path.join(BASE_DIR, 'templates', 'town_center.png'),
    'Castle': os.path.join(BASE_DIR, 'templates', 'castle.png')
}
