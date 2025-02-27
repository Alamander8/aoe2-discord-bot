import psutil
import subprocess
import time
import logging
import winreg
import os
from pathlib import Path

class AoE2Manager:
    """Manages the AoE2:DE process through Steam"""
    
    STEAM_APP_ID = "813780"  # AoE2:DE Steam App ID
    
    def __init__(self):
        self.steam_path = self._get_steam_path()
        self.process = None
        
    def _get_steam_path(self):
        """Get Steam installation path from registry"""
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Wow6432Node\\Valve\\Steam")
            steam_path = winreg.QueryValueEx(hkey, "InstallPath")[0]
            winreg.CloseKey(hkey)
            return Path(steam_path)
        except Exception as e:
            logging.error(f"Failed to get Steam path: {e}")
            return None
            
    def kill_game(self):
        """Force kill AoE2:DE process"""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] == "AoE2DE_s.exe":
                    proc.kill()
                    logging.info("Successfully killed AoE2:DE process")
                    time.sleep(2)  # Wait for cleanup
                    return True
            return False
        except Exception as e:
            logging.error(f"Error killing AoE2:DE: {e}")
            return False
            
    def launch_game(self):
        """Launch AoE2:DE through Steam"""
        if not self.steam_path:
            logging.error("Steam path not found")
            return False
            
        try:
            steam_exe = self.steam_path / "Steam.exe"
            launch_args = [
                str(steam_exe),
                "-applaunch",
                self.STEAM_APP_ID,
                "-nominidumps",  # Prevent crash dumps
                "-novid"         # Skip intro videos
            ]
            
            self.process = subprocess.Popen(launch_args)
            logging.info("Launched AoE2:DE through Steam")
            return True
            
        except Exception as e:
            logging.error(f"Error launching AoE2:DE: {e}")
            return False
            
    def restart_game(self):
        """Kill and relaunch AoE2:DE"""
        if self.kill_game():
            time.sleep(5)  # Give Steam time to register the game closed
            return self.launch_game()
        return False
        
    def is_game_running(self):
        """Check if AoE2:DE is running"""
        try:
            return any(proc.name() == "AoE2DE_s.exe" for proc in psutil.process_iter(['name']))
        except Exception as e:
            logging.error(f"Error checking game status: {e}")
            return False
            
    def wait_for_game_ready(self, timeout=120):
        """Wait for game to be fully launched and ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_game_running():
                time.sleep(10)  # Give the game additional time to fully initialize
                return True
            time.sleep(2)
        return False