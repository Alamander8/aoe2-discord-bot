from obswebsocket import obsws, requests
import time
import logging

class OBSManager:
    host = 'localhost'
    port = 4455
    password = None

    def __init__(self):
        self.ws = None
        self.scenes = {
            'GOING_LIVE': 'GoingLiveLoop',
            'GAME': 'Game',
            'GOING_OFFLINE': 'GoingOffline',
            'FINDING_GAME': 'FindingGame'
        }
        self.current_scene = None
        self.last_scene_switch = 0
        self.min_scene_duration = 1.0
        logging.info("OBS Manager initialized")

    def connect(self):
        try:
            logging.info(f"Attempting to connect to OBS on {self.host}:{self.port}")
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            
            # Verify connection by getting scenes
            scenes_response = self.ws.call(requests.GetSceneList())
            if scenes_response.status:
                self.available_scenes = [scene['sceneName'] for scene in scenes_response.datain['scenes']]
                logging.info(f"Available scenes: {self.available_scenes}")
                
                # Get available sources
                sources_response = self.ws.call(requests.GetSourcesList())
                if sources_response.status:
                    self.available_sources = [source['sourceName'] for source in sources_response.datain['sources']]
                    logging.info(f"Available sources: {self.available_sources}")
                
                logging.info("Successfully connected to OBS")
                return True
            return False
            
        except Exception as e:
            logging.error(f"Failed to connect to OBS. Error details: {str(e)}")
            return False

    def ensure_obs_connected(self):
        try:
            if not self.ws or not self.ws.ws:
                logging.info("OBS connection lost, attempting to reconnect...")
                return self.connect()
            
            # Test connection with a simple request
            try:
                self.ws.call(requests.GetVersion())
                return True
            except:
                logging.info("OBS connection test failed, reconnecting...")
                return self.connect()
                
        except Exception as e:
            logging.error(f"Error checking OBS connection: {e}")
            return False

    def switch_scene(self, scene_name):
        try:
            if not self.ensure_obs_connected():
                return False

            # Verify scene exists
            if scene_name not in self.available_scenes:
                logging.error(f"Scene '{scene_name}' not found. Available scenes: {self.available_scenes}")
                return False

            # Rate limiting
            current_time = time.time()
            if current_time - self.last_scene_switch < self.min_scene_duration:
                time.sleep(self.min_scene_duration - (current_time - self.last_scene_switch))

            response = self.ws.call(requests.SetCurrentProgramScene(sceneName=scene_name))
            if response.status:
                self.current_scene = scene_name
                self.last_scene_switch = time.time()
                logging.info(f"Successfully switched to scene: {scene_name}")
                return True
            else:
                logging.error(f"Failed to switch scene. Response: {response}")
                return False

        except Exception as e:
            logging.error(f"Error switching scene: {e}")
            return False

    def update_match_text(self, match_info):
        try:
            if not self.ensure_obs_connected():
                return False

            map_name = match_info.get('map', '').strip()
            map_name = "Random Map" if not map_name or map_name.isspace() or map_name == '\t' else map_name
            
            players = match_info.get('players', [])
            elo_info = match_info.get('elos', ['', ''])  # Add ELO support
            
            player1 = f"{players[0]} ({elo_info[0]})" if len(players) > 0 else "Player 1"
            player2 = f"{players[1]} ({elo_info[1]})" if len(players) > 1 else "Player 2"
            server = match_info.get('server', 'Unknown Server')

            match_text = f"{player1} vs {player2}\n{map_name} | {server}"

            response = self.ws.call(requests.SetInputSettings(
                inputName="MatchInfo",
                inputSettings={"text": match_text}
            ))
            
            if not response.status:
                logging.error(f"Failed to update text: {response.datain}")
                return False
                
            return True

        except Exception as e:
            logging.error(f"Error updating match text: {e}")
            return False

    def clear_match_text(self):
        try:
            if not self.ensure_obs_connected():
                return False

            response = self.ws.call(requests.SetTextGDIPlusProperties(
                source="MatchInfo",
                text=""
            ))
            if response.status:
                logging.info("Successfully cleared match text")
                return True
            logging.error(f"Failed to clear match text. Response: {response}")
            return False

        except Exception as e:
            logging.error(f"Error clearing match text: {e}")
            return False

    def disconnect(self):
        if self.ws:
            try:
                self.ws.disconnect()
                logging.info("Disconnected from OBS")
            except Exception as e:
                logging.error(f"Error disconnecting from OBS: {e}")

def create_obs_manager():
    return OBSManager()