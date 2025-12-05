"""
DAQ Configuration Module

Handles loading and validation of the main DAQ configuration file (daq_config.json)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class DigitizerConfig:
    """Configuration for a single digitizer"""
    usb_link: int
    conet_node: int = 0
    config_file: str = ""
    enabled: bool = True


@dataclass
class MonitorConfig:
    """Configuration for real-time waveform display"""
    enabled: bool = True
    update_interval_ms: int = 500
    display_channels: List[int] = field(default_factory=lambda: [0, 1, 8, 9])
    display_digitizer: int = 0
    plot_samples: int = 1024
    backend: str = "matplotlib"


@dataclass
class LoggingConfig:
    """Configuration for logging"""
    level: str = "INFO"
    file: Optional[str] = "daq.log"
    console: bool = True


@dataclass
class DAQConfig:
    """
    Main DAQ configuration

    Loaded from daq_config.json file
    """
    # Digitizer configurations
    digitizers: List[DigitizerConfig] = field(default_factory=list)

    # Output settings
    output_directory: str = "./data/run_001"
    max_events: int = 0  # 0 = unlimited
    run_duration_seconds: int = 0  # 0 = unlimited
    sync_trigger: str = "external"  # external or software

    # Monitor settings
    monitor: MonitorConfig = field(default_factory=MonitorConfig)

    # Logging settings
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def load_from_json(cls, file_path: str) -> 'DAQConfig':
        """
        Load configuration from JSON file

        Args:
            file_path: Path to daq_config.json

        Returns:
            DAQConfig object

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file has invalid format
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        logger = logging.getLogger("DAQConfig")
        logger.info(f"Loading configuration from: {file_path}")

        with open(path, 'r') as f:
            data = json.load(f)

        # Parse DAQ section
        daq_section = data.get("daq", {})

        # Parse digitizers
        digitizers = []
        for digi_data in daq_section.get("digitizers", []):
            digitizers.append(DigitizerConfig(
                usb_link=digi_data.get("usb_link", 0),
                conet_node=digi_data.get("conet_node", 0),
                config_file=digi_data.get("config_file", ""),
                enabled=digi_data.get("enabled", True)
            ))

        # Parse monitor section
        monitor_section = data.get("monitor", {})
        monitor = MonitorConfig(
            enabled=monitor_section.get("enabled", True),
            update_interval_ms=monitor_section.get("update_interval_ms", 500),
            display_channels=monitor_section.get("display_channels", [0, 1, 8, 9]),
            display_digitizer=monitor_section.get("display_digitizer", 0),
            plot_samples=monitor_section.get("plot_samples", 1024),
            backend=monitor_section.get("backend", "matplotlib")
        )

        # Parse logging section
        logging_section = data.get("logging", {})
        logging_config = LoggingConfig(
            level=logging_section.get("level", "INFO"),
            file=logging_section.get("file", "daq.log"),
            console=logging_section.get("console", True)
        )

        # Create DAQConfig
        config = cls(
            digitizers=digitizers,
            output_directory=daq_section.get("output_directory", "./data/run_001"),
            max_events=daq_section.get("max_events", 0),
            run_duration_seconds=daq_section.get("run_duration_seconds", 0),
            sync_trigger=daq_section.get("sync_trigger", "external"),
            monitor=monitor,
            logging=logging_config
        )

        # Validate configuration
        config.validate()

        logger.info(f"Configuration loaded: {len(config.digitizers)} digitizer(s)")
        return config

    def validate(self):
        """Validate configuration values"""
        logger = logging.getLogger("DAQConfig")

        # Check that at least one digitizer is enabled
        enabled_digitizers = [d for d in self.digitizers if d.enabled]
        if not enabled_digitizers:
            raise ValueError("No digitizers enabled in configuration")

        # Check for duplicate USB links
        usb_links = [d.usb_link for d in enabled_digitizers]
        if len(usb_links) != len(set(usb_links)):
            raise ValueError("Duplicate USB link numbers detected in configuration")

        # Check that config files exist
        for digi in enabled_digitizers:
            if digi.config_file:
                config_path = Path(digi.config_file)
                if not config_path.exists():
                    logger.warning(
                        f"WaveDump config file not found: {digi.config_file} "
                        f"(USB link {digi.usb_link})"
                    )

        # Validate sync_trigger
        if self.sync_trigger not in ["external", "software"]:
            raise ValueError(
                f"Invalid sync_trigger: {self.sync_trigger}. "
                "Must be 'external' or 'software'"
            )

        # Validate monitor settings
        if self.monitor.update_interval_ms < 100:
            logger.warning(
                f"Monitor update interval ({self.monitor.update_interval_ms}ms) "
                "is very short, may impact performance"
            )

        if self.monitor.display_digitizer >= len(self.digitizers):
            raise ValueError(
                f"display_digitizer ({self.monitor.display_digitizer}) "
                f"exceeds number of digitizers ({len(self.digitizers)})"
            )

        logger.debug("Configuration validation passed")

    def save_to_json(self, file_path: str):
        """
        Save configuration to JSON file

        Args:
            file_path: Path to save daq_config.json
        """
        data = {
            "daq": {
                "digitizers": [
                    {
                        "usb_link": d.usb_link,
                        "conet_node": d.conet_node,
                        "config_file": d.config_file,
                        "enabled": d.enabled
                    }
                    for d in self.digitizers
                ],
                "output_directory": self.output_directory,
                "max_events": self.max_events,
                "run_duration_seconds": self.run_duration_seconds,
                "sync_trigger": self.sync_trigger
            },
            "monitor": {
                "enabled": self.monitor.enabled,
                "update_interval_ms": self.monitor.update_interval_ms,
                "display_channels": self.monitor.display_channels,
                "display_digitizer": self.monitor.display_digitizer,
                "plot_samples": self.monitor.plot_samples,
                "backend": self.monitor.backend
            },
            "logging": {
                "level": self.logging.level,
                "file": self.logging.file,
                "console": self.logging.console
            }
        }

        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger = logging.getLogger("DAQConfig")
        logger.info(f"Configuration saved to: {file_path}")


def create_example_config(file_path: str = "daq_config.json"):
    """
    Create an example configuration file

    Args:
        file_path: Path to save example config
    """
    config = DAQConfig(
        digitizers=[
            DigitizerConfig(
                usb_link=0,
                conet_node=0,
                config_file="WaveDumpConfig_USB0.txt",
                enabled=True
            ),
            DigitizerConfig(
                usb_link=1,
                conet_node=0,
                config_file="WaveDumpConfig_USB1.txt",
                enabled=True
            )
        ],
        output_directory="./data/run_001",
        max_events=0,
        run_duration_seconds=0,
        sync_trigger="external",
        monitor=MonitorConfig(
            enabled=True,
            update_interval_ms=500,
            display_channels=[0, 1, 8, 9],
            display_digitizer=0,
            plot_samples=1024
        ),
        logging=LoggingConfig(
            level="INFO",
            file="daq.log",
            console=True
        )
    )

    config.save_to_json(file_path)
    print(f"Example configuration created: {file_path}")


def main():
    """Test DAQConfig"""
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) > 1:
        if sys.argv[1] == "--create-example":
            create_example_config()
            return
        else:
            config_file = sys.argv[1]
    else:
        config_file = "../daq_config.json"

    try:
        config = DAQConfig.load_from_json(config_file)

        print("\n" + "="*60)
        print("DAQ Configuration")
        print("="*60)
        print(f"Output Directory: {config.output_directory}")
        print(f"Sync Trigger: {config.sync_trigger}")
        print(f"Max Events: {config.max_events} (0 = unlimited)")
        print(f"Run Duration: {config.run_duration_seconds}s (0 = unlimited)")
        print(f"\nDigitizers ({len(config.digitizers)}):")
        for i, digi in enumerate(config.digitizers):
            status = "ENABLED" if digi.enabled else "disabled"
            print(f"  {i}. USB Link {digi.usb_link}, CONET {digi.conet_node} [{status}]")
            print(f"     Config: {digi.config_file}")
        print(f"\nMonitor:")
        print(f"  Enabled: {config.monitor.enabled}")
        print(f"  Update Interval: {config.monitor.update_interval_ms}ms")
        print(f"  Display Channels: {config.monitor.display_channels}")
        print(f"  Display Digitizer: {config.monitor.display_digitizer}")
        print(f"\nLogging:")
        print(f"  Level: {config.logging.level}")
        print(f"  File: {config.logging.file}")
        print(f"  Console: {config.logging.console}")
        print("="*60 + "\n")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
