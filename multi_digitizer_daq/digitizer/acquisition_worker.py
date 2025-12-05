"""
Acquisition Worker

Threaded worker that runs acquisition loop for a single digitizer
"""

import logging
import time
import threading
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .digitizer_controller import DigitizerController
    from monitor.statistics import Statistics
    from monitor.waveform_display import WaveformDisplay

try:
    from caen_libs import caendigitizer as dgtz
    CAEN_LIBS_AVAILABLE = True
except ImportError:
    CAEN_LIBS_AVAILABLE = False
    dgtz = None


class AcquisitionWorker:
    """
    Acquisition worker thread for a single digitizer

    Runs in a separate thread, continuously reading events from the digitizer,
    writing them to disk, and optionally sending them to the display.
    """

    def __init__(self, controller: 'DigitizerController',
                 start_event: threading.Event,
                 stop_event: threading.Event,
                 statistics: Optional['Statistics'] = None,
                 display: Optional['WaveformDisplay'] = None):
        """
        Initialize AcquisitionWorker

        Args:
            controller: DigitizerController for this digitizer
            start_event: Threading event to signal acquisition start
            stop_event: Threading event to signal acquisition stop
            statistics: Optional Statistics tracker
            display: Optional WaveformDisplay for real-time monitoring
        """
        self.controller = controller
        self.start_event = start_event
        self.stop_event = stop_event
        self.statistics = statistics
        self.display = display

        self.logger = logging.getLogger(
            f"AcquisitionWorker-{controller.digitizer_id}"
        )

        if not CAEN_LIBS_AVAILABLE:
            self.logger.error("caen-libs not available!")
            raise ImportError("caen-libs not installed")

    def run(self):
        """
        Main acquisition loop

        This method runs in a separate thread and continuously:
        1. Reads data from the digitizer
        2. Decodes events
        3. Writes waveforms to disk
        4. Sends events to display (if enabled)
        5. Updates statistics
        """
        self.logger.info("Acquisition worker started")

        try:
            # Start hardware acquisition
            self.controller.start_acquisition()

            event_count = 0
            timeout_count = 0
            consecutive_timeouts = 0
            max_consecutive_timeouts = 1000

            # Main acquisition loop
            while not self.stop_event.is_set():
                try:
                    # Read data from digitizer (blocking with timeout)
                    self.controller.device.read_data(
                        dgtz.ReadMode.SLAVE_TERMINATED_READOUT_MBLT
                    )

                    # Get number of events in buffer
                    n_events = self.controller.device.get_num_events()

                    # Handle no events (timeout)
                    if n_events == 0:
                        consecutive_timeouts += 1
                        timeout_count += 1

                        # Warn if too many consecutive timeouts
                        if consecutive_timeouts >= max_consecutive_timeouts:
                            self.logger.warning(
                                f"No trigger received after {consecutive_timeouts} attempts. "
                                "Check external trigger connection."
                            )
                            consecutive_timeouts = 0  # Reset counter

                        time.sleep(0.001)  # Brief sleep to avoid busy-waiting
                        continue

                    # Reset timeout counter on successful read
                    consecutive_timeouts = 0

                    # Warn if buffer is accumulating events
                    if n_events > 100:
                        self.logger.warning(
                            f"Buffer accumulation detected: {n_events} events in buffer. "
                            "Consider reducing trigger rate or increasing readout speed."
                        )

                    # Process each event in the buffer
                    for i in range(n_events):
                        # Get event info and buffer
                        evt_info, buffer = self.controller.device.get_event_info(i)

                        # Decode event (returns X742Event for DT5742)
                        evt = self.controller.device.decode_event(buffer)

                        # Verify it's an X742Event
                        if not isinstance(evt, dgtz.X742Event):
                            self.logger.error(
                                f"Unexpected event type: {type(evt)}. "
                                "Expected X742Event for DT5742."
                            )
                            continue

                        # Write event to disk
                        self._write_event(evt, event_count)

                        # Send to display (non-blocking)
                        if self.display and self.display.is_enabled():
                            try:
                                self.display.add_event(
                                    self.controller.digitizer_id,
                                    evt
                                )
                            except Exception as e:
                                self.logger.debug(f"Display error: {e}")

                        # Update statistics
                        if self.statistics:
                            self.statistics.record_event(
                                self.controller.digitizer_id
                            )

                        event_count += 1

                except dgtz.Error as e:
                    # CAEN digitizer error
                    error_str = str(e).lower()

                    if "timeout" in error_str:
                        # Timeout is normal for external trigger
                        timeout_count += 1
                        time.sleep(0.001)
                        continue
                    elif "overflow" in error_str:
                        self.logger.error(
                            "BUFFER OVERFLOW detected! Data loss may have occurred."
                        )
                        # Attempt recovery
                        try:
                            self.controller.stop_acquisition()
                            time.sleep(0.1)
                            self.controller.start_acquisition()
                            self.logger.info("Acquisition restarted after overflow")
                        except Exception as recovery_error:
                            self.logger.error(f"Recovery failed: {recovery_error}")
                            break
                    else:
                        self.logger.error(f"Digitizer error: {e}")
                        break

                except Exception as e:
                    self.logger.error(f"Unexpected error in acquisition loop: {e}")
                    break

        finally:
            # Stop hardware acquisition
            try:
                self.controller.stop_acquisition()
            except:
                pass

            # Log final statistics
            self.logger.info(
                f"Acquisition worker stopped. "
                f"Total events: {event_count}, "
                f"Timeouts: {timeout_count}"
            )

    def _write_event(self, evt: 'dgtz.X742Event', event_num: int):
        """
        Write X742Event to disk

        DT5742 structure:
        - 4 groups (each group represents a DRS4 chip)
        - 9 channels per group (8 data channels + 1 fast trigger)
        - Waveforms are already in Volts (float32) after DRS4 correction

        Args:
            evt: X742Event from digitizer
            event_num: Global event number
        """
        # Iterate over groups
        for group_id, group in enumerate(evt.data_group):
            if group is None:
                continue  # Group not enabled or no data

            # Iterate over channels in the group
            for ch_in_group, waveform in enumerate(group.data_channel):
                if waveform is None or len(waveform) == 0:
                    continue  # Channel has no data

                # Calculate global channel ID
                # DT5742: 4 groups × 9 channels = 36 total channels
                channel_id = group_id * 9 + ch_in_group

                # Write to binary file
                self.controller.file_writer.write_event(
                    channel_id=channel_id,
                    event_num=event_num,
                    waveform=waveform,
                    trigger_time_tag=group.trigger_time_tag
                )


def main():
    """Test AcquisitionWorker (requires hardware)"""
    import sys
    import argparse
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from digitizer.digitizer_controller import DigitizerController
    from monitor.statistics import Statistics
    from utils.logger import setup_logging

    parser = argparse.ArgumentParser(description="Test AcquisitionWorker")
    parser.add_argument('--usb-link', type=int, default=0, help='USB link number')
    parser.add_argument('--config', type=str, default='../../WaveDumpConfig_USB0.txt',
                        help='WaveDumpConfig file')
    parser.add_argument('--output', type=str, default='./test_acq_output',
                        help='Output directory')
    parser.add_argument('--duration', type=int, default=10,
                        help='Acquisition duration (seconds)')
    args = parser.parse_args()

    setup_logging(level="INFO")
    logger = logging.getLogger("AcquisitionWorkerTest")

    logger.info("Testing AcquisitionWorker...")
    logger.info(f"  USB Link: {args.usb_link}")
    logger.info(f"  Duration: {args.duration} seconds")

    try:
        # Create controller
        controller = DigitizerController(
            usb_link=args.usb_link,
            conet_node=0,
            config_file=args.config,
            output_dir=args.output,
            digitizer_id=0
        )

        # Connect and initialize
        controller.connect()
        controller.initialize()

        # Create statistics tracker
        statistics = Statistics(n_digitizers=1)

        # Create thread events
        start_event = threading.Event()
        stop_event = threading.Event()

        # Create and start worker
        worker = AcquisitionWorker(
            controller=controller,
            start_event=start_event,
            stop_event=stop_event,
            statistics=statistics,
            display=None
        )

        # Start acquisition in a separate thread
        start_event.set()
        worker_thread = threading.Thread(target=worker.run)
        worker_thread.daemon = True
        worker_thread.start()

        logger.info(f"\nAcquisition running for {args.duration} seconds...")
        logger.info("Waiting for external trigger events...")

        # Run for specified duration
        start_time = time.time()
        while time.time() - start_time < args.duration:
            time.sleep(2.0)
            statistics.print_status(force=True)

        # Stop acquisition
        logger.info("\nStopping acquisition...")
        stop_event.set()
        worker_thread.join(timeout=5.0)

        # Final statistics
        statistics.print_status(force=True)

        # Disconnect
        controller.disconnect()

        logger.info("\nAcquisitionWorker test completed!")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
