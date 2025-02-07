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
    'archer': CivilizationBonus(
        name="Archer",
        description="+30% to !pound rewards",
        badge="🏹",
        pound_multiplier=1.30
    ),
    'infantry': CivilizationBonus(
        name="Infantry",
        description="!pound cooldown reduced by 40%",
        badge="⚔️",
        pound_cooldown_multiplier=0.60
    ),
    'cavalry': CivilizationBonus(
        name="Cavalry",
        description="Double !pound rewards but 50% longer cooldown",
        badge="🐎",
        pound_multiplier=2.0,
        pound_cooldown_multiplier=1.50
    ),
    'eagle': CivilizationBonus(
        name="Eagle",
        description="Technologies cost 30% less",
        badge="🦅",
        cost_reduction=0.70
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
        civ_name = civ_name.lower()  # Force lowercase
        if civ_name not in self.CIVILIZATIONS:
            return False, f"Invalid unit type. Use !units to see available options."

        self.user_civilizations[user_id] = civ_name  # Store as lowercase
        self.save_data()
        civ = self.CIVILIZATIONS[civ_name]
        return True, f"You are now specialized in {civ.name} {civ.badge}"

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