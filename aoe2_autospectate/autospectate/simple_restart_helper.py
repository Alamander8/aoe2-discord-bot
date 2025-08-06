# Create new file: simple_restart_helper.py
# This gives you a "restart button" you can call manually

import subprocess
import time
import logging
import psutil
import os

class SimpleRestartHelper:
    def __init__(self):
        # Update these paths for your system
        self.capture_age_path = r"C:\Program Files\CaptureAge\CaptureAge.exe"  # UPDATE THIS
        self.aoe2_process_name = "AoE2DE_s.exe"
        self.capture_age_process_name = "CaptureAge.exe"
        
    def restart_everything(self):
        """Call this manually when you want to restart"""
        logging.info("Manual restart requested...")
        
        try:
            # Step 1: Kill processes nicely
            self.kill_processes(graceful=True)
            time.sleep(3)
            
            # Step 2: Force kill if still running
            self.kill_processes(graceful=False)
            time.sleep(2)
            
            # Step 3: Start CaptureAge
            if os.path.exists(self.capture_age_path):
                subprocess.Popen([self.capture_age_path])
                logging.info(" Started CaptureAge")
                time.sleep(10)  # Wait for it to load
                return True
            else:
                logging.error(f" CaptureAge not found at {self.capture_age_path}")
                return False
                
        except Exception as e:
            logging.error(f"Error during restart: {e}")
            return False
    
    def kill_processes(self, graceful=True):
        """Kill game processes"""
        processes_to_kill = [self.aoe2_process_name, self.capture_age_process_name]
        
        for proc_name in processes_to_kill:
            try:
                killed_any = False
                for proc in psutil.process_iter(['name', 'pid']):
                    if proc.info['name'] == proc_name:
                        if graceful:
                            proc.terminate()
                            logging.info(f" Terminated {proc_name}")
                        else:
                            proc.kill()
                            logging.info(f" Force killed {proc_name}")
                        killed_any = True
                        
                if not killed_any:
                    logging.info(f"  {proc_name} was not running")
                    
            except Exception as e:
                logging.error(f"Error killing {proc_name}: {e}")
    
    def check_processes(self):
        """Check what's currently running"""
        running = []
        for proc in psutil.process_iter(['name', 'pid']):
            if proc.info['name'] in [self.aoe2_process_name, self.capture_age_process_name]:
                running.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
        
        if running:
            logging.info(f"🎮 Running processes: {', '.join(running)}")
        else:
            logging.info("🎮 No game processes running")
        
        return running



    def restart_python_script(self):
        """Nuclear option - restart the entire Python script"""
        logging.info(" NUCLEAR RESTART: Restarting entire Python script...")
        
        try:
            # Kill game processes first
            self.kill_processes(graceful=True)
            time.sleep(3)
            self.kill_processes(graceful=False)
            time.sleep(2)
            
            # Start CaptureAge back up before exiting Python
            if os.path.exists(self.capture_age_path):
                subprocess.Popen([self.capture_age_path])
                logging.info(" Started CaptureAge for nuclear restart")
                time.sleep(10)  # Wait for it to load
            else:
                logging.error(f" CaptureAge not found at {self.capture_age_path}")
            
            # Exit with special code that a batch file can detect
            logging.info(" Exiting Python script for restart...")
            import sys
            sys.exit(42)  # Special exit code meaning "please restart me"
            
        except Exception as e:
            logging.error(f"Error during nuclear restart: {e}")
            import sys
            sys.exit(1)

# How to use this:
#
# 1. Add to your MainFlow.__init__():
#    self.restart_helper = SimpleRestartHelper()
#    self.games_since_restart = 0  # Track games
#
# 2. In your handle_game_end() method, add:
#    self.games_since_restart += 1
#    logging.info(f"Games completed: {self.games_since_restart}")
#    
#    if self.games_since_restart >= 5:  # Restart every 5 games
#        logging.info("🔄 Time for scheduled restart...")
#        if self.restart_helper.restart_everything():
#            self.games_since_restart = 0
#            time.sleep(15)  # Wait for things to settle
#
# 3. For manual restart (add this method to MainFlow):
#    def manual_restart(self):
#        return self.restart_helper.restart_everything()
#
# That's it! Now you get automatic restarts every 5 games,
# and you can manually restart anytime.