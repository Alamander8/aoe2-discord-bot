from obswebsocket import obsws, requests
import time

class OBSManager:
    host = 'localhost'  # Class variable
    port = 4455        # Class variable
    password = None    # Class variable

    def __init__(self):
        self.ws = None
        self.scenes = {
            'GOING_LIVE': 'GoingLiveLoop',
            'GAME': 'Game',
            'GOING_OFFLINE': 'GoingOffline'
        }
        print("OBS Manager initialized")

    def connect(self):
        try:
            print(f"Attempting to connect to OBS on {self.host}:{self.port}")
            self.ws = obsws(self.host, self.port, self.password)
            print("WebSocket object created")

            self.ws.connect()
            print("Successfully connected to OBS")
            return True
        except Exception as e:
            print(f"Failed to connect to OBS. Error details: {str(e)}")
            return False

    def disconnect(self):
        if self.ws:
            try:
                self.ws.disconnect()
                print("Disconnected from OBS")
            except Exception as e:
                print(f"Error disconnecting from OBS: {e}")

    def switch_scene(self, scene_name):
        try:
            # Updated to use call() instead of send()
            self.ws.call(requests.SetCurrentScene(scene_name=scene_name))
            print(f"Switched to scene: {scene_name}")
            return True
        except Exception as e:
            print(f"Error switching scene: {e}")
            return False


def create_obs_manager():
    return OBSManager()