"""
WaveDump Configuration File Parser

Parses CAEN WaveDump configuration files (WaveDumpConfig_USBx.txt format)
into Python dataclasses for use with py-caen-libs.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging


@dataclass
class WaveDumpConfig:
    """
    Parsed WaveDump configuration

    Represents settings from WaveDumpConfig_USBx.txt files
    """
    # Connection settings
    connection_type: str = "USB"
    usb_link: int = 0
    conet_node: int = 0
    vme_base_address: int = 0

    # DRS4 settings (specific to X742 family)
    drs4_frequency: int = 0  # 0=5GHz, 1=2.5GHz, 2=1GHz, 3=750MHz
    record_length: int = 1024
    post_trigger: int = 50  # Percentage (0-100)

    # Trigger settings
    external_trigger: str = "DISABLED"  # DISABLED, ACQUISITION_ONLY, ACQUISITION_AND_TRGOUT
    fast_trigger: str = "DISABLED"
    sw_trigger: str = "DISABLED"

    # Acquisition settings
    max_num_events_blt: int = 1
    acquisition_mode: str = "SW_CONTROLLED"

    # Correction and calibration
    correction_level: str = "AUTO"
    skip_startup_calibration: bool = False

    # Group settings (DT5742 has 4 groups: 0, 1, 2, 3)
    # Each group can have settings like enable, DC offset, polarity
    group_enabled: Dict[int, bool] = field(default_factory=dict)
    group_pulse_polarity: Dict[int, str] = field(default_factory=dict)  # POSITIVE/NEGATIVE
    group_dc_offset: Dict[int, float] = field(default_factory=dict)  # Percentage or ADC counts

    # TR0 (Fast trigger) settings
    tr0_pulse_polarity: str = "POSITIVE"
    tr0_dc_offset: int = 32768  # ADC counts (0-65535)
    tr0_trigger_threshold: int = 20000  # ADC counts
    tr0_enabled: bool = False

    # Output file settings
    output_file_format: str = "BINARY"  # BINARY or ASCII
    output_file_header: bool = True

    # I/O settings
    fpio_level: str = "NIM"  # NIM or TTL

    # Advanced: Direct register writes (address, data, mask)
    register_writes: List[Tuple[int, int, int]] = field(default_factory=list)

    # Other settings
    test_pattern: bool = False


class WaveDumpConfigParser:
    """
    Parser for WaveDump configuration files

    Parses section-based text configuration files used by CAEN WaveDump software.

    Sections:
        [COMMON]: Global digitizer settings
        [0], [1], [2], [3]: Group-specific settings (DT5742 has 4 groups)
        [TR0]: Fast trigger settings

    Example:
        config = WaveDumpConfigParser.parse("WaveDumpConfig_USB0.txt")
        print(f"DRS4 Frequency: {config.drs4_frequency}")
        print(f"Record Length: {config.record_length}")
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def parse(file_path: str) -> WaveDumpConfig:
        """
        Parse a WaveDump configuration file

        Args:
            file_path: Path to WaveDumpConfig_USBx.txt file

        Returns:
            WaveDumpConfig object with all parsed settings

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file has invalid format or values
        """
        parser = WaveDumpConfigParser()
        return parser._parse_file(file_path)

    def _parse_file(self, file_path: str) -> WaveDumpConfig:
        """Internal method to parse configuration file"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        config = WaveDumpConfig()
        current_section = "COMMON"

        self.logger.info(f"Parsing configuration file: {file_path}")

        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                # Section headers: [COMMON], [0], [1], [TR0], etc.
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                    self.logger.debug(f"Entering section: {current_section}")
                    continue

                # Parse key-value pairs
                try:
                    self._parse_setting(config, current_section, line, line_num)
                except Exception as e:
                    self.logger.warning(
                        f"Error parsing line {line_num} in section [{current_section}]: {line}"
                        f"\n  Error: {e}"
                    )

        # Validate configuration
        self._validate_config(config)

        self.logger.info(f"Configuration parsed successfully: {path.name}")
        return config

    def _parse_setting(self, config: WaveDumpConfig, section: str, line: str, line_num: int):
        """Parse a single configuration line based on current section"""
        # Split on whitespace
        parts = line.split(None, 1)
        if len(parts) < 1:
            return

        key = parts[0]
        value = parts[1] if len(parts) > 1 else ""

        if section == "COMMON":
            self._parse_common_setting(config, key, value)
        elif section in ["0", "1", "2", "3"]:
            self._parse_group_setting(config, int(section), key, value)
        elif section == "TR0":
            self._parse_tr0_setting(config, key, value)
        else:
            self.logger.debug(f"Unknown section [{section}], ignoring: {key}")

    def _parse_common_setting(self, config: WaveDumpConfig, key: str, value: str):
        """Parse settings in [COMMON] section"""
        if key == "OPEN":
            # Format: OPEN USB <link> <conet_node> [vme_base_address]
            parts = value.split()
            if len(parts) >= 3:
                config.connection_type = parts[0]
                config.usb_link = int(parts[1])
                config.conet_node = int(parts[2])
                if len(parts) >= 4:
                    config.vme_base_address = int(parts[3], 16)  # Hex value

        elif key == "DRS4_FREQUENCY":
            config.drs4_frequency = int(value)

        elif key == "RECORD_LENGTH":
            config.record_length = int(value)

        elif key == "POST_TRIGGER":
            config.post_trigger = int(value)

        elif key == "EXTERNAL_TRIGGER":
            config.external_trigger = value

        elif key == "FAST_TRIGGER":
            config.fast_trigger = value

        elif key == "SW_TRIGGER":
            config.sw_trigger = value

        elif key == "MAX_NUM_EVENTS_BLT":
            config.max_num_events_blt = int(value)

        elif key == "ACQUISITION_MODE":
            config.acquisition_mode = value

        elif key == "CORRECTION_LEVEL":
            config.correction_level = value

        elif key == "SKIP_STARTUP_CALIBRATION":
            config.skip_startup_calibration = (value.upper() == "YES")

        elif key == "OUTPUT_FILE_FORMAT":
            config.output_file_format = value

        elif key == "OUTPUT_FILE_HEADER":
            config.output_file_header = (value.upper() == "YES")

        elif key == "FPIO_LEVEL":
            config.fpio_level = value

        elif key == "TEST_PATTERN":
            config.test_pattern = (value.upper() == "YES")

        elif key == "WRITE_REGISTER":
            # Format: WRITE_REGISTER <address> <data> [<mask>]
            parts = value.split()
            if len(parts) >= 2:
                addr = int(parts[0], 16)
                data = int(parts[1], 16)
                mask = int(parts[2], 16) if len(parts) >= 3 else 0xFFFFFFFF
                config.register_writes.append((addr, data, mask))

    def _parse_group_setting(self, config: WaveDumpConfig, group: int, key: str, value: str):
        """Parse settings in group sections [0], [1], [2], [3]"""
        if key == "ENABLE_INPUT":
            config.group_enabled[group] = (value.upper() == "YES")

        elif key == "PULSE_POLARITY":
            config.group_pulse_polarity[group] = value

        elif key == "DC_OFFSET":
            # Can be percentage (-100 to 100) or ADC counts
            config.group_dc_offset[group] = float(value)

    def _parse_tr0_setting(self, config: WaveDumpConfig, key: str, value: str):
        """Parse settings in [TR0] section (fast trigger)"""
        if key == "PULSE_POLARITY":
            config.tr0_pulse_polarity = value

        elif key == "DC_OFFSET":
            config.tr0_dc_offset = int(value)

        elif key == "TRIGGER_THRESHOLD":
            config.tr0_trigger_threshold = int(value)

        elif key == "ENABLED_FAST_TRIGGER_DIGITIZING":
            config.tr0_enabled = (value.upper() == "YES")

    def _validate_config(self, config: WaveDumpConfig):
        """Validate parsed configuration values"""
        # Validate DRS4 frequency
        if config.drs4_frequency not in [0, 1, 2, 3]:
            raise ValueError(
                f"Invalid DRS4_FREQUENCY: {config.drs4_frequency}. "
                "Valid values: 0 (5GHz), 1 (2.5GHz), 2 (1GHz), 3 (750MHz)"
            )

        # Validate record length (must be power of 2, typically)
        if config.record_length <= 0:
            raise ValueError(f"Invalid RECORD_LENGTH: {config.record_length}")

        # Validate post-trigger percentage
        if not (0 <= config.post_trigger <= 100):
            raise ValueError(
                f"Invalid POST_TRIGGER: {config.post_trigger}. "
                "Must be between 0 and 100 (percentage)"
            )

        # Validate trigger modes
        valid_trigger_modes = ["DISABLED", "ACQUISITION_ONLY", "ACQUISITION_AND_TRGOUT"]
        if config.external_trigger not in valid_trigger_modes:
            self.logger.warning(
                f"Unexpected EXTERNAL_TRIGGER value: {config.external_trigger}"
            )

        # Validate I/O level
        if config.fpio_level not in ["NIM", "TTL"]:
            self.logger.warning(
                f"Unexpected FPIO_LEVEL value: {config.fpio_level}"
            )

        self.logger.debug("Configuration validation passed")


def main():
    """Test WaveDumpConfigParser with example files"""
    import sys

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        # Default to USB0 config
        config_file = "../WaveDumpConfig_USB0.txt"

    try:
        config = WaveDumpConfigParser.parse(config_file)

        print("\n" + "="*60)
        print("Parsed WaveDump Configuration")
        print("="*60)
        print(f"Connection: {config.connection_type} Link {config.usb_link}, CONET {config.conet_node}")
        print(f"DRS4 Frequency: {config.drs4_frequency} (", end="")
        freq_map = {0: "5 GHz", 1: "2.5 GHz", 2: "1 GHz", 3: "750 MHz"}
        print(f"{freq_map.get(config.drs4_frequency, 'Unknown')})")
        print(f"Record Length: {config.record_length} samples")
        print(f"Post Trigger: {config.post_trigger}%")
        print(f"External Trigger: {config.external_trigger}")
        print(f"Fast Trigger: {config.fast_trigger}")
        print(f"FPIO Level: {config.fpio_level}")
        print(f"\nGroup Settings:")
        for group_id in range(4):
            enabled = config.group_enabled.get(group_id, False)
            polarity = config.group_pulse_polarity.get(group_id, "N/A")
            offset = config.group_dc_offset.get(group_id, "N/A")
            print(f"  Group {group_id}: Enabled={enabled}, Polarity={polarity}, Offset={offset}")
        print(f"\nTR0 (Fast Trigger):")
        print(f"  Enabled: {config.tr0_enabled}")
        print(f"  Polarity: {config.tr0_pulse_polarity}")
        print(f"  DC Offset: {config.tr0_dc_offset}")
        print(f"  Threshold: {config.tr0_trigger_threshold}")
        if config.register_writes:
            print(f"\nRegister Writes: {len(config.register_writes)}")
            for addr, data, mask in config.register_writes:
                print(f"  0x{addr:04X} = 0x{data:08X} (mask: 0x{mask:08X})")
        print("="*60 + "\n")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
