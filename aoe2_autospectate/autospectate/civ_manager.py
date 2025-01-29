import json
from dataclasses import dataclass
from typing import Dict, Optional
import logging

@dataclass
class CivilizationBonus:
    name: str
    description: str
    badge: str
    pound_multiplier: float = 1.0
    passive_income: int = 0
    cost_reduction: float = 1.0
    pound_cooldown_multiplier: float = 1.0

class CivilizationManager:
    CIVILIZATIONS = {
    'incan': CivilizationBonus(
        name="Incan",
        description="!pound rewards increased by 15%, 5% tech cost reduction",
        badge="🏔️",
        pound_multiplier=1.15,
        cost_reduction=0.95
    ),
    'briton': CivilizationBonus(
        name="Briton",
        description="+25% to all !pound rewards",
        badge="🏹",
        pound_multiplier=1.25
    ),
    'persian': CivilizationBonus(
        name="Persian",
        description="10% to all !pound rewards, 10% shorter pound CD ",
        badge="🐘",
        pound_multiplier=2.0,
        pound_cooldown_multiplier=0.90
    ),
    'chinese': CivilizationBonus(
        name="Chinese",
        description="Technologies cost 30% less",
        badge="🐉",
        cost_reduction=0.70
    ),
    'japanese': CivilizationBonus(
        name="Japanese",
        description="!pound cooldown reduced by 30%",
        badge="⛩️",
        pound_cooldown_multiplier=0.70
    ),
    'malay': CivilizationBonus(
        name="Malay",
        description="Age ups cost 40% less",
        badge="⛵",
        cost_reduction=0.60  # For age ups only
    ),
    'teuton': CivilizationBonus(
        name="Teuton",
        description="+10% to !pound rewards and technologies cost 15% less",
        badge="🏰",
        pound_multiplier=1.10,
        cost_reduction=0.85
    )
}

    def __init__(self, data_file='user_civilizations.json'):
        self.data_file = data_file
        self.user_civilizations: Dict[str, str] = self.load_data()
        self.passive_income_times: Dict[str, float] = {}

    def load_data(self) -> Dict[str, str]:
        """Load civilization data from file"""
        try:
            with open(self.data_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_data(self):
        """Save civilization data to file"""
        with open(self.data_file, 'w') as f:
            json.dump(self.user_civilizations, f)

    def select_civilization(self, user_id: str, civ_name: str) -> tuple[bool, str]:
        """Select a civilization for a user"""
        civ_name = civ_name.lower()
        if civ_name not in self.CIVILIZATIONS:
            return False, f"Invalid civilization. Use !civs to see available options."

        self.user_civilizations[user_id] = civ_name
        self.save_data()
        civ = self.CIVILIZATIONS[civ_name]
        return True, f"You are now playing as {civ.name} {civ.badge}"

    def get_user_civ(self, user_id: str) -> Optional[CivilizationBonus]:
        """Get a user's civilization bonus"""
        if user_id in self.user_civilizations:
            return self.CIVILIZATIONS[self.user_civilizations[user_id]]
        return None

    def format_civ_list(self) -> str:
        """Format the civilization list for display"""
        civ_text = "🏰 Available Civilizations 🏰\n"
        for civ_id, civ in self.CIVILIZATIONS.items():
            civ_text += f"{civ.badge} {civ.name}: {civ.description}\n"
        return civ_text

    def get_display_name(self, username: str, user_id: str) -> str:
        """Get display name with civilization badge"""
        civ = self.get_user_civ(user_id)
        if civ:
            return f"{civ.badge} {username}"
        return username

    def apply_pound_bonus(self, user_id: str, amount: int) -> int:
        """Apply civilization bonus to pound command"""
        civ = self.get_user_civ(user_id)
        if civ:
            return int(amount * civ.pound_multiplier)
        return amount

    def get_pound_cooldown(self, user_id: str, base_cooldown: float) -> float:
        """Get modified pound cooldown for civilization"""
        civ = self.get_user_civ(user_id)
        if civ:
            return base_cooldown * civ.pound_cooldown_multiplier
        return base_cooldown

    def get_cost_modifier(self, user_id: str, is_age_up: bool = False) -> float:
        """Get cost modifier for technologies and age ups"""
        civ = self.get_user_civ(user_id)
        if not civ:
            return 1.0
        
        # Special case for Franks
        if civ.name == "Frank" and is_age_up:
            return 0.75
            
        return civ.cost_reduction