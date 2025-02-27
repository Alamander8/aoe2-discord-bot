# Screen Coordinates
MINIMAP_X = 730       # Base X position
MINIMAP_Y = 840       # Base Y position
MINIMAP_WIDTH = 460   # Width of capture area
MINIMAP_HEIGHT = 280  # Height of capture area
MINIMAP_PADDING = 10  # Padding around minimap

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
# Improved HSV ranges focusing on vibrant unit colors
PLAYER_HSV_RANGES = {
    'Blue': {
        'normal': {
            'lower': (115, 200, 150),  # Higher saturation minimum, narrower hue range
            'upper': (125, 255, 255)   # Keeping full upper ranges for bright units
        },
        'icon': {  # Keep existing icon detection for TC/Castle icons
            'lower': (115, 200, 200),
            'upper': (125, 255, 255)
        }
    },
    'Red': {
        'normal': {
            'lower': (0, 200, 150),    # Higher saturation minimum
            'upper': (5, 255, 255)     # Narrower hue range
        },
        'icon': {  # Keep existing icon detection
            'lower': (0, 200, 200),
            'upper': (5, 255, 255)
        }
    },
    'Green': {
        'normal': {
            'lower': (45, 200, 150),
            'upper': (75, 255, 255)
        },
        'icon': {
            'lower': (45, 200, 200),
            'upper': (75, 255, 255)
        }
    },
    'Yellow': {
        'normal': {
            'lower': (25, 200, 150),
            'upper': (35, 255, 255)
        },
        'icon': {
            'lower': (25, 200, 200),
            'upper': (35, 255, 255)
        }
    },
    'Cyan': {
        'normal': {
            'lower': (85, 200, 150),
            'upper': (95, 255, 255)
        },
        'icon': {
            'lower': (85, 200, 200),
            'upper': (95, 255, 255)
        }
    },
    'Purple': {
        'normal': {
            'lower': (135, 200, 150),
            'upper': (150, 255, 255)
        },
        'icon': {
            'lower': (135, 200, 200),
            'upper': (150, 255, 255)
        }
    },
    'Gray': {
        'normal': {
            'lower': (0, 0, 60),
            'upper': (180, 30, 200)
        },
        'icon': {
            'lower': (0, 0, 150),
            'upper': (180, 30, 255)
        }
    },
    'Orange': {
        'normal': {
            'lower': (15, 200, 150),
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

MIN_GAME_ELO=1050

# Game settings
MAX_PLAYERS = 8
EXPECTED_PLAYERS_1V1 = 2

# Initial buildings
STARTING_TC_COUNT = 1  # Players start with 1 TC