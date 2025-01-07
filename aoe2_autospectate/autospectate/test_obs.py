from obs_control import create_obs_manager
import time

def test_obs():
    print("\nStarting OBS test...")

# Create manager
    obs = create_obs_manager()

# Try to connect
    if obs.connect():
        print("Connected to OBS!")

# Test each scene
        for scene_key in obs.scenes:
            scene_name = obs.scenes[scene_key]
            print(f"\nTrying to switch to {scene_name}")
            obs.switch_scene(scene_name)
            time.sleep(2)

# Disconnect
        obs.disconnect()
        print("\nTest completed!")
    else:
        print("Failed to connect to OBS")

if __name__ == "__main__":
    test_obs()