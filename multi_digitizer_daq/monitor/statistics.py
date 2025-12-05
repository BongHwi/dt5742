"""
Statistics Module

Tracks and calculates acquisition statistics (event rates, counts, etc.)
"""

import time
import logging
from collections import deque
from typing import Dict, List
from dataclasses import dataclass, field


@dataclass
class DigitizerStats:
    """Statistics for a single digitizer"""
    digitizer_id: int
    event_count: int = 0
    start_time: float = field(default_factory=time.time)
    last_update_time: float = field(default_factory=time.time)

    def get_total_rate(self) -> float:
        """Get average rate since start (events/second)"""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.event_count / elapsed
        return 0.0

    def get_elapsed_time(self) -> float:
        """Get elapsed time since start (seconds)"""
        return time.time() - self.start_time


class RateCalculator:
    """
    Calculate event rate using a moving window

    Uses a deque to maintain timestamps of recent events and calculates
    rate over a sliding time window.
    """

    def __init__(self, window_seconds: float = 10.0):
        """
        Initialize RateCalculator

        Args:
            window_seconds: Time window for rate calculation (seconds)
        """
        self.window_seconds = window_seconds
        self.event_times: deque = deque()  # Timestamps of recent events

    def record_event(self):
        """Record an event occurrence"""
        current_time = time.time()
        self.event_times.append(current_time)

        # Remove events outside the window
        cutoff_time = current_time - self.window_seconds
        while self.event_times and self.event_times[0] < cutoff_time:
            self.event_times.popleft()

    def get_rate(self) -> float:
        """
        Get current event rate (events/second)

        Returns:
            Event rate in events per second
        """
        if len(self.event_times) < 2:
            return 0.0

        # Calculate rate over the actual time span of events in window
        time_span = self.event_times[-1] - self.event_times[0]
        if time_span > 0:
            return len(self.event_times) / time_span
        return 0.0

    def reset(self):
        """Reset rate calculator"""
        self.event_times.clear()


class Statistics:
    """
    Track and display acquisition statistics for multiple digitizers

    Maintains event counts, rates, and timing information for each digitizer
    in the DAQ system.
    """

    def __init__(self, n_digitizers: int, rate_window_seconds: float = 10.0):
        """
        Initialize Statistics

        Args:
            n_digitizers: Number of digitizers to track
            rate_window_seconds: Time window for rate calculation
        """
        self.n_digitizers = n_digitizers
        self.rate_window_seconds = rate_window_seconds

        # Per-digitizer statistics
        self.digitizer_stats: List[DigitizerStats] = [
            DigitizerStats(digitizer_id=i)
            for i in range(n_digitizers)
        ]

        # Per-digitizer rate calculators
        self.rate_calculators: List[RateCalculator] = [
            RateCalculator(window_seconds=rate_window_seconds)
            for _ in range(n_digitizers)
        ]

        self.logger = logging.getLogger("Statistics")
        self.last_print_time = time.time()
        self.print_interval = 5.0  # Print stats every 5 seconds

    def record_event(self, digitizer_id: int):
        """
        Record an event for a specific digitizer

        Args:
            digitizer_id: ID of digitizer that acquired the event
        """
        if 0 <= digitizer_id < self.n_digitizers:
            self.digitizer_stats[digitizer_id].event_count += 1
            self.digitizer_stats[digitizer_id].last_update_time = time.time()
            self.rate_calculators[digitizer_id].record_event()

    def get_total_events(self) -> int:
        """Get total event count across all digitizers"""
        return sum(stats.event_count for stats in self.digitizer_stats)

    def get_rate(self, digitizer_id: int) -> float:
        """
        Get current event rate for a digitizer

        Args:
            digitizer_id: ID of digitizer

        Returns:
            Event rate in events/second
        """
        if 0 <= digitizer_id < self.n_digitizers:
            return self.rate_calculators[digitizer_id].get_rate()
        return 0.0

    def get_average_rate(self, digitizer_id: int) -> float:
        """
        Get average event rate since start for a digitizer

        Args:
            digitizer_id: ID of digitizer

        Returns:
            Average rate in events/second
        """
        if 0 <= digitizer_id < self.n_digitizers:
            return self.digitizer_stats[digitizer_id].get_total_rate()
        return 0.0

    def print_status(self, force: bool = False):
        """
        Print current statistics to logger

        Args:
            force: Force print even if interval hasn't elapsed
        """
        current_time = time.time()

        if not force and (current_time - self.last_print_time) < self.print_interval:
            return  # Too soon to print again

        self.last_print_time = current_time

        total_events = self.get_total_events()
        status_lines = ["\n" + "="*60]
        status_lines.append("DAQ Statistics")
        status_lines.append("="*60)

        for i, stats in enumerate(self.digitizer_stats):
            elapsed = stats.get_elapsed_time()
            avg_rate = stats.get_total_rate()
            current_rate = self.rate_calculators[i].get_rate()

            status_lines.append(
                f"Digitizer {i}: "
                f"{stats.event_count} events | "
                f"Rate: {current_rate:.1f} evt/s ({avg_rate:.1f} avg) | "
                f"Runtime: {self._format_duration(elapsed)}"
            )

        status_lines.append(f"Total Events: {total_events}")
        status_lines.append("="*60)

        for line in status_lines:
            self.logger.info(line)

    def get_summary(self) -> Dict:
        """
        Get summary of all statistics

        Returns:
            Dictionary with statistics for all digitizers
        """
        summary = {
            'total_events': self.get_total_events(),
            'digitizers': []
        }

        for i, stats in enumerate(self.digitizer_stats):
            digi_summary = {
                'digitizer_id': i,
                'event_count': stats.event_count,
                'current_rate': self.rate_calculators[i].get_rate(),
                'average_rate': stats.get_total_rate(),
                'elapsed_time': stats.get_elapsed_time()
            }
            summary['digitizers'].append(digi_summary)

        return summary

    def reset(self):
        """Reset all statistics"""
        self.logger.info("Resetting statistics...")

        for stats in self.digitizer_stats:
            stats.event_count = 0
            stats.start_time = time.time()
            stats.last_update_time = time.time()

        for calc in self.rate_calculators:
            calc.reset()

    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in human-readable form

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted string (e.g., "1h 23m 45s")
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.0f}s"


def main():
    """Test Statistics"""
    import random
    from utils.logger import setup_logging

    setup_logging(level="INFO")

    logger = logging.getLogger("StatisticsTest")
    logger.info("Testing Statistics module...")

    # Create statistics tracker for 2 digitizers
    stats = Statistics(n_digitizers=2, rate_window_seconds=5.0)

    # Simulate events
    logger.info("Simulating events for 10 seconds...")

    start_time = time.time()
    while time.time() - start_time < 10.0:
        # Random events for both digitizers
        digitizer_id = random.randint(0, 1)
        stats.record_event(digitizer_id)

        # Print status every few seconds
        stats.print_status()

        # Sleep a bit to simulate realistic event rate
        time.sleep(0.01)  # ~100 Hz total

    # Final status
    stats.print_status(force=True)

    # Get summary
    summary = stats.get_summary()
    logger.info(f"\nFinal Summary: {summary['total_events']} total events")

    logger.info("Statistics test completed")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pathlib import Path
    main()
