"""
DAQ Orchestrator

Main coordinator for multi-digitizer DAQ system
"""

import logging
import time
import threading
from pathlib import Path
from typing import List, Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.daq_config import DAQConfig
from digitizer.digitizer_controller import DigitizerController
from digitizer.acquisition_worker import AcquisitionWorker
from monitor.statistics import Statistics
from utils.logger import setup_logging


class DAQOrchestrator:
    """
    Main orchestrator for multi-digitizer DAQ system

    Coordinates:
    - Multiple digitizers
    - Acquisition threads
    - Keyboard input
    - Real-time display
    - Statistics
    """

    def __init__(self, config_file: str = "daq_config.json"):
        """
        Initialize DAQOrchestrator

        Args:
            config_file: Path to daq_config.json
        """
        self.config_file = config_file
        self.config: Optional[DAQConfig] = None

        # Digitizers and threads
        self.digitizers: List[DigitizerController] = []
        self.acquisition_threads: List[threading.Thread] = []
        self.acquisition_workers: List[AcquisitionWorker] = []

        # Synchronization events
        self.start_event = threading.Event()
        self.stop_event = threading.Event()
        self.quit_event = threading.Event()

        # Components
        self.statistics: Optional[Statistics] = None
        self.keyboard_handler: Optional['KeyboardHandler'] = None
        self.display: Optional['WaveformDisplay'] = None

        self.logger = logging.getLogger("DAQOrchestrator")

    def initialize(self) -> bool:
        """
        Initialize all digitizers and components

        Returns:
            True if all digitizers initialized successfully
        """
        # Load configuration
        try:
            self.config = DAQConfig.load_from_json(self.config_file)
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False

        # Setup logging from config
        setup_logging(
            level=self.config.logging.level,
            log_file=self.config.logging.file,
            console=self.config.logging.console
        )

        self.logger.info("="*60)
        self.logger.info("Multi-Digitizer DAQ System")
        self.logger.info("="*60)
        self.logger.info(f"Configuration: {self.config_file}")
        self.logger.info(f"Output Directory: {self.config.output_directory}")
        self.logger.info(f"Sync Trigger: {self.config.sync_trigger}")
        self.logger.info("="*60)

        # Initialize digitizers
        enabled_digitizers = [d for d in self.config.digitizers if d.enabled]
        self.logger.info(
            f"\nInitializing {len(enabled_digitizers)} digitizer(s)..."
        )

        for digi_config in enabled_digitizers:
            try:
                self.logger.info(
                    f"\n  Digitizer {len(self.digitizers)}: "
                    f"USB{digi_config.usb_link}"
                )

                # Create controller
                controller = DigitizerController(
                    usb_link=digi_config.usb_link,
                    conet_node=digi_config.conet_node,
                    config_file=digi_config.config_file,
                    output_dir=self.config.output_directory,
                    digitizer_id=len(self.digitizers)
                )

                # Connect
                controller.connect()

                # Initialize
                controller.initialize()

                self.digitizers.append(controller)

                # Log device info
                info = controller.get_device_info()
                self.logger.info(f"    Model: {info.get('model_name', 'Unknown')}")
                self.logger.info(f"    S/N: {info.get('serial_number', 'Unknown')}")

            except Exception as e:
                self.logger.error(
                    f"  Failed to initialize digitizer USB{digi_config.usb_link}: {e}"
                )
                # Continue with other digitizers
                continue

        if not self.digitizers:
            self.logger.error("No digitizers initialized successfully!")
            return False

        # Create statistics tracker
        self.statistics = Statistics(
            n_digitizers=len(self.digitizers),
            rate_window_seconds=10.0
        )
        self.logger.info(f"\n  Statistics tracker initialized")

        # Create display (if enabled)
        if self.config.monitor.enabled:
            try:
                from monitor.waveform_display import WaveformDisplay
                self.display = WaveformDisplay(
                    config=self.config.monitor,
                    n_digitizers=len(self.digitizers)
                )
                self.logger.info(f"  Real-time display initialized")
            except ImportError as e:
                self.logger.warning(
                    f"  Display not available (matplotlib not installed): {e}"
                )
                self.display = None
            except Exception as e:
                self.logger.error(f"  Failed to initialize display: {e}")
                self.display = None

        # Create keyboard handler
        try:
            from control.keyboard_handler import KeyboardHandler
            self.keyboard_handler = KeyboardHandler(self)
            self.logger.info(f"  Keyboard handler initialized")
        except ImportError as e:
            self.logger.warning(
                f"  Keyboard handler not available (pynput not installed): {e}"
            )
            self.keyboard_handler = None

        self.logger.info("\n" + "="*60)
        self.logger.info("Initialization complete!")
        self.logger.info("="*60)

        return True

    def start_acquisition(self):
        """Start acquisition on all digitizers simultaneously"""
        if self.start_event.is_set():
            self.logger.warning("Acquisition already running")
            return

        self.logger.info("\n" + "="*60)
        self.logger.info("STARTING ACQUISITION")
        self.logger.info("="*60)

        # Reset statistics
        if self.statistics:
            self.statistics.reset()

        # Clear stop event, set start event
        self.stop_event.clear()
        self.start_event.set()

        # Create and start acquisition threads
        for controller in self.digitizers:
            # Create worker
            worker = AcquisitionWorker(
                controller=controller,
                start_event=self.start_event,
                stop_event=self.stop_event,
                statistics=self.statistics,
                display=self.display
            )
            self.acquisition_workers.append(worker)

            # Create thread
            thread = threading.Thread(
                target=worker.run,
                name=f"Acq-USB{controller.usb_link}"
            )
            thread.daemon = True
            thread.start()
            self.acquisition_threads.append(thread)

        self.logger.info(
            f"Acquisition started on {len(self.acquisition_threads)} digitizer(s)"
        )
        self.logger.info("Waiting for external trigger events...")
        self.logger.info("="*60 + "\n")

    def stop_acquisition(self):
        """Stop acquisition on all digitizers simultaneously"""
        if not self.start_event.is_set():
            self.logger.warning("Acquisition not running")
            return

        self.logger.info("\n" + "="*60)
        self.logger.info("STOPPING ACQUISITION")
        self.logger.info("="*60)

        # Signal threads to stop
        self.stop_event.set()

        # Wait for threads to finish
        self.logger.info("Waiting for acquisition threads to stop...")
        for thread in self.acquisition_threads:
            thread.join(timeout=5.0)
            if thread.is_alive():
                self.logger.warning(f"Thread {thread.name} did not stop cleanly")

        # Clear thread lists
        self.acquisition_threads.clear()
        self.acquisition_workers.clear()
        self.start_event.clear()

        # Print final statistics
        if self.statistics:
            self.statistics.print_status(force=True)

        self.logger.info("Acquisition stopped")
        self.logger.info("="*60 + "\n")

    def is_acquiring(self) -> bool:
        """Check if acquisition is currently running"""
        return self.start_event.is_set()

    def reload_configuration(self):
        """Reload configuration files (hot-reload)"""
        was_running = self.is_acquiring()

        if was_running:
            self.logger.info("Stopping acquisition for configuration reload...")
            self.stop_acquisition()

        self.logger.info("Reloading configuration from files...")

        try:
            # Reload main config
            self.config = DAQConfig.load_from_json(self.config_file)

            # Reload each digitizer's WaveDumpConfig
            for controller in self.digitizers:
                controller.reload_configuration()

            self.logger.info("Configuration reloaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to reload configuration: {e}")

        if was_running:
            self.logger.info("Restarting acquisition...")
            self.start_acquisition()

    def request_stop(self):
        """Request program to stop (called by keyboard handler)"""
        self.quit_event.set()

    def run(self):
        """
        Main event loop

        Runs until quit is requested
        """
        if not self.digitizers:
            self.logger.error("No digitizers initialized. Cannot run.")
            return

        # Start keyboard handler
        if self.keyboard_handler:
            self.keyboard_handler.start()
        else:
            self.logger.warning(
                "No keyboard handler available. "
                "Use Ctrl+C to stop or send SIGINT."
            )

        self.logger.info("\nDAQ system ready")
        if self.keyboard_handler:
            self.logger.info("Press 'h' for help, 's' to start/stop, 'q' to quit\n")

        try:
            # Main loop
            last_status_time = time.time()
            status_interval = 5.0  # Print status every 5 seconds

            while not self.quit_event.is_set():
                time.sleep(0.1)

                # Print statistics periodically if acquiring
                if self.is_acquiring() and self.statistics:
                    current_time = time.time()
                    if current_time - last_status_time >= status_interval:
                        self.statistics.print_status()
                        last_status_time = current_time

        except KeyboardInterrupt:
            self.logger.info("\n\nInterrupted by user (Ctrl+C)")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        self.logger.info("\n" + "="*60)
        self.logger.info("SHUTTING DOWN")
        self.logger.info("="*60)

        # Stop acquisition if running
        if self.is_acquiring():
            self.stop_acquisition()

        # Stop keyboard handler
        if self.keyboard_handler:
            self.keyboard_handler.stop()

        # Close display
        if self.display:
            try:
                self.display.close()
            except:
                pass

        # Disconnect all digitizers
        self.logger.info("Disconnecting digitizers...")
        for controller in self.digitizers:
            try:
                controller.disconnect()
            except Exception as e:
                self.logger.error(f"Error disconnecting digitizer: {e}")

        self.logger.info("Shutdown complete")
        self.logger.info("="*60)


def main():
    """Test DAQOrchestrator"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Multi-Digitizer DAQ System"
    )
    parser.add_argument(
        '--config',
        type=str,
        default='daq_config.json',
        help='Configuration file (default: daq_config.json)'
    )
    args = parser.parse_args()

    try:
        # Create orchestrator
        orchestrator = DAQOrchestrator(config_file=args.config)

        # Initialize
        if not orchestrator.initialize():
            sys.exit(1)

        # Run
        orchestrator.run()

    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
