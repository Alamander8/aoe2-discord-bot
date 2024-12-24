# Screen Coordinates
MINIMAP_X = 760       # Base X position
MINIMAP_Y = 840       # Base Y position
MINIMAP_WIDTH = 350   # Width of capture area
MINIMAP_HEIGHT = 300  # Height of capture area
MINIMAP_PADDING = 50  # Padding around minimap

# Game Area
GAME_AREA_X = 0
GAME_AREA_Y = 0
GAME_AREA_WIDTH = 1920   # Adjust based on your screen resolution
GAME_AREA_HEIGHT = 1080  # Adjust based on your screen resolution


# Game Ages and their time thresholds (in seconds)
GAME_AGES = [
    ('Dark Age', 0),
    ('Feudal Age', 600),    # 10 minutes
    ('Castle Age', 1200),   # 20 minutes
    ('Imperial Age', 1800)  # 30 minutes
]

# URLs (if needed)
AOE2_COMPANION_URL = 'https://www.aoe2companion.com/ongoing'

# Spectate Criteria
GAME_MODE_FILTER = 'Random Map'


# Player Colors with specific building icon detection
PLAYER_HSV_RANGES = {
    'Blue': {
        'normal': {
            'lower': (100, 150, 0),
            'upper': (140, 255, 255)
        },
        'icon': {  # For TC/Castle icons - more saturated/distinct
            'lower': (100, 200, 200),
            'upper': (140, 255, 255)
        }
    },
    'Red': {
        'normal': {
            'lower': (0, 150, 70),
            'upper': (10, 255, 255)
        },
        'icon': {
            'lower': (0, 200, 200),
            'upper': (10, 255, 255)
        }
    },
    'Green': {
        'normal': {
            'lower': (40, 70, 70),
            'upper': (80, 255, 255)
        },
        'icon': {
            'lower': (40, 200, 200),
            'upper': (80, 255, 255)
        }
    },
    'Yellow': {
        'normal': {
            'lower': (25, 150, 150),
            'upper': (35, 255, 255)
        },
        'icon': {
            'lower': (25, 200, 200),
            'upper': (35, 255, 255)
        }
    },
    'Cyan': {
        'normal': {
            'lower': (85, 150, 150),
            'upper': (95, 255, 255)
        },
        'icon': {
            'lower': (85, 200, 200),
            'upper': (95, 255, 255)
        }
    },
    'Purple': {
        'normal': {
            'lower': (130, 100, 100),
            'upper': (160, 255, 255)
        },
        'icon': {
            'lower': (130, 200, 200),
            'upper': (160, 255, 255)
        }
    },
    'Gray': {
        'normal': {
            'lower': (82, 82, 82),
            'upper': (82, 82, 82)
        },
        'icon': {
            'lower': (47, 47, 47),
            'upper': (47, 47, 47)
        }
    },
    'Orange': {
        'normal': {
            'lower': (15, 150, 150),
            'upper': (25, 255, 255)
        },
        'icon': {
            'lower': (15, 200, 200),
            'upper': (25, 255, 255)
        }
    }
}

# Important building icon characteristics
BUILDING_ICON_MIN_AREA = 15  # Minimum pixel area for TC/Castle icons
BUILDING_ICON_MAX_AREA = 50  # Maximum pixel area
BUILDING_ICON_MIN_CIRCULARITY = 0.6  # How circular the icon should be (1.0 is perfect circle)



# Game settings
MAX_PLAYERS = 8
EXPECTED_PLAYERS_1V1 = 2

# Initial buildings
STARTING_TC_COUNT = 1  # Players start with 1 TC