#!/usr/bin/env python3
"""
Multi-Digitizer DAQ System - Main Entry Point

CAEN DT5742 Multi-Digitizer Data Acquisition System
"""

import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from control.daq_orchestrator import DAQOrchestrator


def print_banner():
    """Print startup banner"""
    banner = """
╔════════════════════════════════════════════════════════════╗
║     Multi-Digitizer DAQ System for CAEN DT5742             ║
║                                                            ║
║     Data Acquisition with Real-Time Monitoring             ║
╚════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    """Main entry point"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Multi-Digitizer DAQ System for CAEN DT5742",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config
  python main.py

  # Run with custom config
  python main.py --config my_daq_config.json

  # Create example configuration
  python main.py --create-config

Keyboard Controls:
  s - Start/Stop acquisition
  m - Toggle monitor display
  r - Reload configuration
  h - Show help
  q - Quit program
        """
    )

    parser.add_argument(
        '--config',
        type=str,
        default='daq_config.json',
        help='Configuration file (default: daq_config.json)'
    )

    parser.add_argument(
        '--create-config',
        action='store_true',
        help='Create example daq_config.json and exit'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default=None,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Override logging level from config'
    )

    args = parser.parse_args()

    # Create example configuration if requested
    if args.create_config:
        from config.daq_config import create_example_config
        create_example_config(args.config)
        print(f"\nExample configuration created: {args.config}")
        print("Edit this file to configure your digitizers and settings.")
        return 0

    # Print banner
    print_banner()

    try:
        # Create orchestrator
        orchestrator = DAQOrchestrator(config_file=args.config)

        # Override log level if specified
        if args.log_level:
            logging.getLogger().setLevel(getattr(logging, args.log_level))

        # Initialize
        print("Initializing DAQ system...")
        if not orchestrator.initialize():
            print("\n❌ Initialization failed. Check log for details.")
            return 1

        print("\n✅ Initialization successful!")
        print("\nDAQ system ready. Press 'h' for help.\n")

        # Run main event loop
        orchestrator.run()

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user (Ctrl+C)")
        return 0

    except FileNotFoundError as e:
        print(f"\n❌ Configuration file not found: {e}")
        print(f"\nCreate a configuration file with:")
        print(f"  python main.py --create-config")
        return 1

    except ImportError as e:
        print(f"\n❌ Missing required library: {e}")
        print("\nInstall required libraries:")
        print("  pip install -r requirements.txt")
        print("\nNote: CAEN libraries must be installed separately from:")
        print("  https://www.caen.it/subfamilies/software-libraries/")
        return 1

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logging.error("Fatal error", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
