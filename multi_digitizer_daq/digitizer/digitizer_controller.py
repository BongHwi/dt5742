"""
Digitizer Controller

Manages a single CAEN DT5742 digitizer: connection, configuration, and file writing
"""

import logging
import time
from pathlib import Path
from typing import Optional

try:
    from caen_libs import caendigitizer as dgtz
    CAEN_LIBS_AVAILABLE = True
except ImportError:
    CAEN_LIBS_AVAILABLE = False
    dgtz = None

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.wavedump_parser import WaveDumpConfig, WaveDumpConfigParser
from config.config_mapper import apply_wavedump_config
from data.file_writer import FileWriter


class DigitizerController:
    """
    Controller for a single CAEN DT5742 digitizer

    Manages:
    - USB connection to digitizer
    - Configuration from WaveDumpConfig file
    - File writing for acquired data
    - Start/stop acquisition
    """

    def __init__(self, usb_link: int, conet_node: int, config_file: str,
                 output_dir: str, digitizer_id: int):
        """
        Initialize DigitizerController

        Args:
            usb_link: USB link number (0, 1, 2, ...)
            conet_node: CONET node number (usually 0)
            config_file: Path to WaveDumpConfig_USBx.txt file
            output_dir: Directory to write data files
            digitizer_id: Unique ID for this digitizer
        """
        self.usb_link = usb_link
        self.conet_node = conet_node
        self.config_file = config_file
        self.output_dir = output_dir
        self.digitizer_id = digitizer_id

        self.device: Optional['dgtz.Device'] = None
        self.config: Optional[WaveDumpConfig] = None
        self.file_writer: Optional[FileWriter] = None

        self.logger = logging.getLogger(f"DigitizerController-{digitizer_id}")
        self.connected = False
        self.initialized = False

        # Check if CAEN libraries are available
        if not CAEN_LIBS_AVAILABLE:
            self.logger.error("caen-libs not available! Install with: pip install caen-libs")
            raise ImportError("caen-libs not installed")

    def connect(self, max_retries: int = 3, retry_delay: float = 2.0) -> bool:
        """
        Open USB connection to digitizer

        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Delay between retries (seconds)

        Returns:
            True if connected successfully

        Raises:
            Exception: If connection fails after all retries
        """
        self.logger.info(f"Connecting to digitizer USB{self.usb_link}...")

        for attempt in range(max_retries):
            try:
                # Open device
                self.device = dgtz.Device.open(
                    dgtz.ConnectionType.USB,
                    str(self.usb_link),
                    self.conet_node,
                    0  # vme_base_address
                )

                # Get device info
                info = self.device.get_info()
                self.logger.info(
                    f"Connected to {info.model_name} "
                    f"(S/N: {info.serial_number}, "
                    f"Firmware: {info.firmware_code.name}, "
                    f"Channels: {info.channels})"
                )

                self.connected = True
                return True

            except Exception as e:
                self.logger.warning(
                    f"Connection attempt {attempt + 1}/{max_retries} failed: {e}"
                )
                if attempt < max_retries - 1:
                    self.logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    self.logger.error(
                        f"Failed to connect to digitizer USB{self.usb_link} "
                        f"after {max_retries} attempts"
                    )
                    raise

        return False

    def initialize(self) -> bool:
        """
        Initialize digitizer with configuration from WaveDumpConfig file

        Returns:
            True if initialized successfully

        Raises:
            Exception: If initialization fails
        """
        if not self.connected:
            raise RuntimeError("Digitizer not connected. Call connect() first.")

        self.logger.info(f"Initializing digitizer from: {self.config_file}")

        try:
            # Reset digitizer
            self.device.reset()
            self.logger.debug("Digitizer reset")

            # Parse WaveDumpConfig file
            self.config = WaveDumpConfigParser.parse(self.config_file)
            self.logger.info("Configuration file parsed successfully")

            # Apply configuration to device
            apply_wavedump_config(self.device, self.config)
            self.logger.info("Configuration applied to digitizer")

            # Create file writer
            self.file_writer = FileWriter(
                output_dir=self.output_dir,
                digitizer_id=self.digitizer_id,
                n_groups=4,  # DT5742 has 4 groups
                n_channels_per_group=9  # 8 data + 1 trigger
            )
            self.logger.info(f"File writer initialized: {self.output_dir}")

            self.initialized = True
            return True

        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            raise

    def reload_configuration(self):
        """
        Reload configuration from file and re-apply to digitizer

        Useful for dynamic reconfiguration without reconnecting
        """
        if not self.connected:
            raise RuntimeError("Digitizer not connected")

        self.logger.info("Reloading configuration...")

        # Parse configuration
        self.config = WaveDumpConfigParser.parse(self.config_file)

        # Reset device
        self.device.reset()

        # Apply new configuration
        apply_wavedump_config(self.device, self.config)

        self.logger.info("Configuration reloaded successfully")

    def start_acquisition(self):
        """Start hardware acquisition"""
        if not self.initialized:
            raise RuntimeError("Digitizer not initialized")

        self.device.sw_start_acquisition()
        self.logger.debug("Hardware acquisition started")

    def stop_acquisition(self):
        """Stop hardware acquisition"""
        if not self.initialized:
            return

        self.device.sw_stop_acquisition()
        self.logger.debug("Hardware acquisition stopped")

    def disconnect(self):
        """Close connection and clean up resources"""
        self.logger.info("Disconnecting...")

        # Stop acquisition if running
        try:
            self.stop_acquisition()
        except:
            pass

        # Close file writer
        if self.file_writer:
            self.file_writer.close_all()

        # Free device buffers
        if self.device:
            try:
                self.device.free_event()
                self.device.free_readout_buffer()
            except:
                pass

            # Close device
            try:
                self.device.close()
                self.logger.info("Disconnected from digitizer")
            except:
                pass

        self.connected = False
        self.initialized = False

    def get_device_info(self) -> dict:
        """
        Get information about connected digitizer

        Returns:
            Dictionary with device information
        """
        if not self.connected:
            return {}

        info = self.device.get_info()
        return {
            'model_name': info.model_name,
            'serial_number': info.serial_number,
            'firmware_code': info.firmware_code.name,
            'channels': info.channels,
            'adc_bits': info.adc_n_bits,
            'form_factor': info.form_factor.name if hasattr(info, 'form_factor') else 'Unknown'
        }

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect"""
        self.disconnect()


def main():
    """Test DigitizerController (requires actual hardware)"""
    import argparse
    from utils.logger import setup_logging

    parser = argparse.ArgumentParser(description="Test DigitizerController")
    parser.add_argument('--usb-link', type=int, default=0, help='USB link number')
    parser.add_argument('--config', type=str, default='../../WaveDumpConfig_USB0.txt',
                        help='WaveDumpConfig file')
    parser.add_argument('--output', type=str, default='./test_output',
                        help='Output directory')
    args = parser.parse_args()

    setup_logging(level="DEBUG")
    logger = logging.getLogger("DigitizerControllerTest")

    logger.info("Testing DigitizerController...")
    logger.info(f"  USB Link: {args.usb_link}")
    logger.info(f"  Config: {args.config}")
    logger.info(f"  Output: {args.output}")

    try:
        # Create controller
        controller = DigitizerController(
            usb_link=args.usb_link,
            conet_node=0,
            config_file=args.config,
            output_dir=args.output,
            digitizer_id=0
        )

        # Connect
        logger.info("\n1. Connecting to digitizer...")
        controller.connect()

        # Get device info
        info = controller.get_device_info()
        logger.info(f"\nDevice Info:")
        for key, value in info.items():
            logger.info(f"  {key}: {value}")

        # Initialize
        logger.info("\n2. Initializing digitizer...")
        controller.initialize()

        # Test acquisition start/stop
        logger.info("\n3. Testing acquisition start/stop...")
        controller.start_acquisition()
        time.sleep(1.0)
        controller.stop_acquisition()

        logger.info("\nDigitizerController test completed successfully!")

        # Disconnect
        controller.disconnect()

    except ImportError as e:
        logger.error(f"\nCAEN libraries not available: {e}")
        logger.error("This test requires actual hardware and installed CAEN libraries")
        logger.error("Install with: pip install caen-libs")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\nTest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
