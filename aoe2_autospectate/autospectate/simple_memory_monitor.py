# Create new file: simple_memory_monitor.py
# This just logs memory usage - doesn't change anything else

import psutil
import time
import logging
import gc

class SimpleMemoryMonitor:
    def __init__(self, log_interval=60):
        self.log_interval = log_interval
        self.last_log = 0
        self.warning_threshold_mb = 2000  # 2GB warning
        self.critical_threshold_mb = 3000  # 3GB critical
        self.nuclear_threshold_mb = 4000   # 4GB nuclear restart
        self.critical_count = 0  # Track consecutive critical readings
            
    def check_and_log(self):
        current_time = time.time()
        
        if current_time - self.last_log < self.log_interval:
            return "OK"
            
        try:
            # Get memory usage
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            # Check all thresholds including nuclear
            if memory_mb > self.nuclear_threshold_mb:
                logging.critical(f"NUCLEAR MEMORY: {memory_mb:.1f}MB")
                return "NUCLEAR"
            elif memory_mb > self.critical_threshold_mb:
                logging.error(f"CRITICAL MEMORY: {memory_mb:.1f}MB")
                return "CRITICAL"
            elif memory_mb > self.warning_threshold_mb:
                logging.warning(f"HIGH MEMORY: {memory_mb:.1f}MB")
                return "WARNING"
            else:
                logging.info(f"Memory usage: {memory_mb:.1f}MB")
                return "OK"
                
        except Exception as e:
            logging.error(f"Error checking memory: {e}")
            return "ERROR"
        finally:
            self.last_log = current_time

    def force_cleanup_if_needed(self):
        """Only call this manually when you see critical memory"""
        try:
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            if memory_mb > self.critical_threshold_mb:
                logging.info(" Running emergency cleanup...")
                collected = gc.collect()
                logging.info(f"Collected {collected} objects")
                
                # Check after cleanup
                new_memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                logging.info(f"Memory after cleanup: {new_memory_mb:.1f}MB (was {memory_mb:.1f}MB)")
                return new_memory_mb
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
            return None


# How to use this in your existing main_flow.py:
# 
# 1. Add this to your MainFlow.__init__():
#    self.memory_monitor = SimpleMemoryMonitor()
#
# 2. Add this to your main_loop() (just once, anywhere in the while loop):
#    memory_status = self.memory_monitor.check_and_log()
#    if memory_status == "CRITICAL":
#        logging.error("Consider restarting soon!")
#        # You could set a flag here to restart after current game
#
# 3. If you see critical memory warnings, you can manually call:
#    self.memory_monitor.force_cleanup_if_needed()

# That's it! No other changes needed. Just start seeing what your memory usage looks like.