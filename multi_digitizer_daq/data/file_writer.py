"""
Binary File Writer

Writes waveform data to binary files in CAEN format, compatible with
existing data_converter pipeline.
"""

import struct
import logging
from pathlib import Path
from typing import BinaryIO, Dict, Optional
import numpy as np


class FileWriter:
    """
    Write waveforms to binary files in CAEN format

    File format (compatible with data_converter/convert_to_root.cpp):
        Header (32 bytes):
            - eventSize (uint64): Total bytes including header
            - boardId (uint64): Digitizer ID
            - channelId (uint64): Global channel ID
            - eventCounter (uint64): Event number

        Payload:
            - N × float32: Waveform samples in Volts

    File naming: wave_<channel_id>.dat (one file per channel)
    """

    def __init__(self, output_dir: str, digitizer_id: int,
                 n_groups: int = 4, n_channels_per_group: int = 9):
        """
        Initialize FileWriter

        Args:
            output_dir: Directory to write data files
            digitizer_id: ID of this digitizer (for multi-digitizer setups)
            n_groups: Number of groups (4 for DT5742)
            n_channels_per_group: Channels per group (9 for DT5742: 8 data + 1 trigger)
        """
        self.output_dir = Path(output_dir)
        self.digitizer_id = digitizer_id
        self.n_groups = n_groups
        self.n_channels_per_group = n_channels_per_group

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # File handles (one per channel)
        self.file_handles: Dict[int, BinaryIO] = {}

        # Event counters (one per channel, for verification)
        self.event_counters: Dict[int, int] = {}

        # Bytes written (one per channel, for statistics)
        self.bytes_written: Dict[int, int] = {}

        self.logger = logging.getLogger(f"FileWriter-{digitizer_id}")
        self.logger.info(f"FileWriter initialized: output_dir={output_dir}, digitizer_id={digitizer_id}")

    def write_event(self, channel_id: int, event_num: int,
                    waveform: np.ndarray, trigger_time_tag: Optional[int] = None):
        """
        Write a single event to the appropriate channel file

        Args:
            channel_id: Global channel ID (0-35 for 4 groups × 9 channels)
            event_num: Global event number
            waveform: Waveform data (numpy array of float32)
            trigger_time_tag: Optional trigger time tag from digitizer

        Raises:
            IOError: If file write fails
        """
        # Open file if not already open
        if channel_id not in self.file_handles:
            self._open_file(channel_id)

        fh = self.file_handles[channel_id]

        # Ensure waveform is float32
        if waveform.dtype != np.float32:
            waveform = waveform.astype(np.float32)

        # Calculate event size
        n_samples = len(waveform)
        event_size = 32 + n_samples * 4  # 32-byte header + N × 4-byte floats

        # Write header (32 bytes = 4 × uint64)
        header = struct.pack(
            'QQQQ',  # 4 × uint64 (little-endian)
            event_size,      # Total size including header
            self.digitizer_id,  # Board ID
            channel_id,      # Channel ID
            event_num        # Event counter
        )
        fh.write(header)

        # Write waveform data (N × float32)
        waveform_bytes = waveform.tobytes()
        fh.write(waveform_bytes)

        # Update statistics
        self.event_counters[channel_id] = self.event_counters.get(channel_id, 0) + 1
        self.bytes_written[channel_id] = self.bytes_written.get(channel_id, 0) + event_size

        # Periodic flush (every 100 events)
        if self.event_counters[channel_id] % 100 == 0:
            fh.flush()
            if self.event_counters[channel_id] % 1000 == 0:
                self.logger.debug(
                    f"Channel {channel_id}: {self.event_counters[channel_id]} events, "
                    f"{self.bytes_written[channel_id] / 1024 / 1024:.2f} MB"
                )

    def _open_file(self, channel_id: int):
        """
        Open a binary file for a specific channel

        Args:
            channel_id: Channel ID
        """
        file_path = self.output_dir / f"wave_{channel_id}.dat"

        # Check if file already exists
        if file_path.exists():
            self.logger.warning(
                f"File already exists, will append: {file_path}"
            )
            mode = 'ab'  # Append binary
        else:
            mode = 'wb'  # Write binary

        self.file_handles[channel_id] = open(file_path, mode)
        self.event_counters[channel_id] = 0
        self.bytes_written[channel_id] = 0

        self.logger.info(f"Opened file: {file_path} (mode: {mode})")

    def flush_all(self):
        """Flush all open file handles"""
        for fh in self.file_handles.values():
            fh.flush()

    def close_all(self):
        """Close all open file handles"""
        self.logger.info("Closing all files...")

        for channel_id, fh in self.file_handles.items():
            fh.close()
            self.logger.info(
                f"  Channel {channel_id}: {self.event_counters[channel_id]} events, "
                f"{self.bytes_written[channel_id] / 1024 / 1024:.2f} MB"
            )

        self.file_handles.clear()
        self.logger.info("All files closed")

    def get_statistics(self) -> Dict[int, Dict[str, int]]:
        """
        Get statistics for all channels

        Returns:
            Dictionary mapping channel_id to statistics
        """
        stats = {}
        for channel_id in self.event_counters.keys():
            stats[channel_id] = {
                'events': self.event_counters.get(channel_id, 0),
                'bytes': self.bytes_written.get(channel_id, 0)
            }
        return stats

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close all files"""
        self.close_all()


def main():
    """Test FileWriter"""
    import numpy as np
    from utils.logger import setup_logging

    setup_logging(level="DEBUG")

    logger = logging.getLogger("FileWriterTest")

    # Create test data directory
    test_dir = Path("./test_data")
    test_dir.mkdir(exist_ok=True)

    logger.info("Testing FileWriter...")

    # Create FileWriter
    with FileWriter(output_dir=str(test_dir), digitizer_id=0) as writer:
        # Write test events
        n_events = 10
        n_samples = 1024

        for event_num in range(n_events):
            for channel_id in [0, 1, 8, 9]:  # Test a few channels
                # Generate fake waveform data
                waveform = np.sin(
                    2 * np.pi * np.arange(n_samples) / n_samples
                ).astype(np.float32)
                waveform += np.random.normal(0, 0.1, n_samples).astype(np.float32)

                # Write event
                writer.write_event(channel_id, event_num, waveform)

            if (event_num + 1) % 5 == 0:
                logger.info(f"Wrote {event_num + 1} events...")

    # Show statistics
    logger.info("\nStatistics:")
    stats = writer.get_statistics()
    for channel_id, channel_stats in stats.items():
        logger.info(
            f"  Channel {channel_id}: {channel_stats['events']} events, "
            f"{channel_stats['bytes'] / 1024:.2f} KB"
        )

    # Verify files exist
    logger.info("\nCreated files:")
    for file_path in sorted(test_dir.glob("wave_*.dat")):
        size_kb = file_path.stat().st_size / 1024
        logger.info(f"  {file_path.name}: {size_kb:.2f} KB")

    logger.info("\nFileWriter test completed")


if __name__ == "__main__":
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    main()
