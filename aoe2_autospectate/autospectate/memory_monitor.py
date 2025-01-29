import psutil
import logging
import time
import os
import gc
from threading import Thread
from typing import Dict, List, Optional
import numpy as np

class MemoryMonitor:
    def __init__(self, warning_threshold_mb: float = 1000, 
                 critical_threshold_mb: float = 2000,
                 check_interval: float = 30.0):
        self.warning_threshold = warning_threshold_mb * 1024 * 1024  # Convert to bytes
        self.critical_threshold = critical_threshold_mb * 1024 * 1024
        self.check_interval = check_interval
        self.monitoring = False
        self.monitor_thread = None
        self.process = psutil.Process(os.getpid())
        self.memory_history: List[Dict] = []
        self.cv2_cache_count = 0
        self.np_array_count = 0
        
        # Set up logging
        self.setup_logging()

    def setup_logging(self):
        """Set up memory-specific logging"""
        memory_logger = logging.getLogger('memory_monitor')
        memory_logger.setLevel(logging.INFO)
        handler = logging.FileHandler('logs/memory_usage.log')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        memory_logger.addHandler(handler)
        self.logger = memory_logger

    def start_monitoring(self):
        """Start memory monitoring in a separate thread"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            self.logger.info("Memory monitoring started")

    def stop_monitoring(self):
        """Stop memory monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
            self.logger.info("Memory monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                # Get memory usage
                memory_info = self.process.memory_info()
                current_usage = memory_info.rss

                # Log memory status
                self.log_memory_status(current_usage)

                # Count numpy arrays and update history
                self.count_numpy_arrays()
                self.memory_history.append({
                    'timestamp': time.time(),
                    'usage': current_usage,
                    'np_arrays': self.np_array_count
                })

                # Keep only last hour of history
                cutoff_time = time.time() - 3600
                self.memory_history = [
                    entry for entry in self.memory_history 
                    if entry['timestamp'] > cutoff_time
                ]

                # Check for memory growth pattern
                if len(self.memory_history) > 10:
                    self.check_memory_growth()

                # Force garbage collection if above warning threshold
                if current_usage > self.warning_threshold:
                    self.force_cleanup()

                time.sleep(self.check_interval)

            except Exception as e:
                self.logger.error(f"Error in memory monitoring: {e}")
                time.sleep(self.check_interval)

    def count_numpy_arrays(self):
        """Count active numpy arrays in memory"""
        self.np_array_count = sum(
            1 for obj in gc.get_objects()
            if isinstance(obj, np.ndarray)
        )
        self.logger.debug(f"Active numpy arrays: {self.np_array_count}")

    def check_memory_growth(self):
        """Check for consistent memory growth pattern"""
        recent_usage = [entry['usage'] for entry in self.memory_history[-10:]]
        if all(recent_usage[i] < recent_usage[i+1] for i in range(len(recent_usage)-1)):
            self.logger.warning("Detected consistent memory growth pattern")
            self.log_memory_analysis()

    def force_cleanup(self):
        """Force garbage collection and memory cleanup"""
        self.logger.info("Forcing memory cleanup")
        gc.collect()
        
        # Log detailed memory info after cleanup
        memory_info = self.process.memory_info()
        self.logger.info(
            f"After cleanup - RSS: {memory_info.rss / 1024 / 1024:.2f}MB, "
            f"VMS: {memory_info.vms / 1024 / 1024:.2f}MB"
        )

    def log_memory_status(self, current_usage: int):
        """Log current memory status with appropriate warning levels"""
        memory_mb = current_usage / 1024 / 1024
        
        if current_usage > self.critical_threshold:
            self.logger.critical(
                f"CRITICAL: Memory usage at {memory_mb:.2f}MB"
            )
        elif current_usage > self.warning_threshold:
            self.logger.warning(
                f"WARNING: Memory usage at {memory_mb:.2f}MB"
            )
        else:
            self.logger.info(f"Memory usage: {memory_mb:.2f}MB")

    def log_memory_analysis(self):
        """Log detailed memory analysis"""
        # Get memory info by type
        types_count = {}
        for obj in gc.get_objects():
            obj_type = type(obj).__name__
            types_count[obj_type] = types_count.get(obj_type, 0) + 1

        # Log top memory consumers
        self.logger.info("Memory Analysis:")
        for obj_type, count in sorted(
            types_count.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]:
            self.logger.info(f"{obj_type}: {count} instances")

    def get_memory_stats(self) -> Dict:
        """Get current memory statistics"""
        memory_info = self.process.memory_info()
        return {
            'rss': memory_info.rss / 1024 / 1024,  # MB
            'vms': memory_info.vms / 1024 / 1024,  # MB
            'numpy_arrays': self.np_array_count,
            'history_length': len(self.memory_history)
        }

    def cleanup_resources(self):
        """Cleanup memory monitor resources"""
        self.stop_monitoring()
        self.memory_history.clear()
        gc.collect()