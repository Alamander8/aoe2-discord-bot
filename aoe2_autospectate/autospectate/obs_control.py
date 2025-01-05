from obswebsocket import obsws, requests
import time
import logging
import json
from pathlib import Path

class OBSManager:
    """Manages OBS scenes and transitions for AoE2 spectating."""
    
    def __init__(self, host='localhost', port=4455, password=None):
        """Initialize OBS connection and load scene configurations."""
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.scenes = {
            'GOING_LIVE': 'GoingLiveLoop',
            'GAME': 'Game',
            'GOING_OFFLINE': 'GoingOffline'
        }
        self.transitions = {
            'STINGER': 'SaltyEmpires'
        }
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for OBS operations."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('obs_manager.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('OBSManager')

    def connect(self):
        """Establish connection to OBS websocket."""
        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.logger.info("Successfully connected to OBS")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to OBS: {e}")
            return False

    def disconnect(self):
        """Safely disconnect from OBS websocket."""
        if self.ws:
            try:
                self.ws.disconnect()
                self.logger.info("Disconnected from OBS")
            except Exception as e:
                self.logger.error(f"Error disconnecting from OBS: {e}")

    def start_stream(self, match_info=None):
        """Start streaming with going live sequence."""
        try:
            # Switch to going live scene
            self.switch_scene(self.scenes['GOING_LIVE'])
            self.logger.info("Switched to Going Live scene")
            
            # Start streaming
            self.ws.call(requests.StartStreaming())
            self.logger.info("Started streaming")
            
            # Wait for going live animation
            time.sleep(5)  # Adjust based on animation length
            
            # Switch to game scene
            self.switch_scene(self.scenes['GAME'])
            self.logger.info("Switched to Game scene")
            
            return True
        except Exception as e:
            self.logger.error(f"Error starting stream: {e}")
            return False

    def stop_stream(self):
        """Stop streaming with going offline sequence."""
        try:
            # Switch to going offline scene
            self.switch_scene(self.scenes['GOING_OFFLINE'])
            self.logger.info("Switched to Going Offline scene")
            
            # Wait for offline animation
            time.sleep(5)  # Adjust based on animation length
            
            # Stop streaming
            self.ws.call(requests.StopStreaming())
            self.logger.info("Stopped streaming")
            
            return True
        except Exception as e:
            self.logger.error(f"Error stopping stream: {e}")
            return False

    def switch_scene(self, scene_name):
        """Switch to specified scene using stinger transition."""
        try:
            # Set transition
            self.ws.call(requests.SetCurrentSceneTransition(self.transitions['STINGER']))
            
            # Switch scene
            self.ws.call(requests.SetCurrentProgramScene(scene_name))
            self.logger.info(f"Switched to scene: {scene_name}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error switching scene: {e}")
            return False

    def update_game_source(self, window_title):
        """Update the game capture source with new window."""
        try:
            # Get current scene items
            scene_items = self.ws.call(requests.GetSceneItemList(sceneName=self.scenes['GAME']))
            
            # Find and update window capture source
            for item in scene_items.getSceneItems():
                if item['sourceName'] == 'Window Capture':
                    source_settings = {
                        'window': window_title
                    }
                    self.ws.call(requests.SetInputSettings(
                        inputName='Window Capture',
                        inputSettings=source_settings
                    ))
                    self.logger.info(f"Updated window capture to: {window_title}")
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"Error updating game source: {e}")
            return False

    def is_streaming(self):
        """Check if OBS is currently streaming."""
        try:
            status = self.ws.call(requests.GetStreamStatus())
            return status.getOutputActive()
        except Exception as e:
            self.logger.error(f"Error checking stream status: {e}")
            return False

def create_obs_manager(config_path=None):
    """Create and configure OBS manager instance."""
    # Default websocket connection settings
    settings = {
        'host': 'localhost',
        'port': 4455,
        'password': None  # Add password if configured in OBS
    }
    
    # Load custom settings if provided
    if config_path:
        try:
            with open(config_path, 'r') as f:
                custom_settings = json.load(f)
                settings.update(custom_settings)
        except Exception as e:
            logging.error(f"Error loading OBS config: {e}")
    
    return OBSManager(**settings)