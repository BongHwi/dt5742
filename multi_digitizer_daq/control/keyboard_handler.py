"""
Keyboard Handler

Non-blocking keyboard input handler for DAQ control
"""

import logging
from typing import Optional, TYPE_CHECKING

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    keyboard = None

if TYPE_CHECKING:
    from .daq_orchestrator import DAQOrchestrator


class KeyboardHandler:
    """
    Non-blocking keyboard input handler using pynput

    Listens for keyboard input in a separate thread and triggers
    appropriate DAQ actions.

    Key bindings:
        's' - Start/stop acquisition
        'm' - Toggle monitor display
        'r' - Reload configuration
        'q' - Quit program
    """

    def __init__(self, orchestrator: 'DAQOrchestrator'):
        """
        Initialize KeyboardHandler

        Args:
            orchestrator: DAQOrchestrator instance to control
        """
        self.orchestrator = orchestrator
        self.listener: Optional[keyboard.Listener] = None
        self.logger = logging.getLogger("KeyboardHandler")

        if not PYNPUT_AVAILABLE:
            self.logger.error(
                "pynput not available! Install with: pip install pynput"
            )
            raise ImportError("pynput not installed")

        self.enabled = True

    def start(self):
        """Start keyboard listener thread"""
        if self.listener is not None:
            self.logger.warning("Keyboard listener already started")
            return

        self.listener = keyboard.Listener(on_press=self._on_key_press)
        self.listener.start()
        self.logger.info("Keyboard handler started")
        self._print_help()

    def stop(self):
        """Stop keyboard listener thread"""
        if self.listener:
            self.listener.stop()
            self.listener = None
            self.logger.info("Keyboard handler stopped")

    def _on_key_press(self, key):
        """
        Handle keyboard press events

        Args:
            key: Key object from pynput
        """
        if not self.enabled:
            return

        try:
            # Get character if it's a character key
            if hasattr(key, 'char') and key.char:
                char = key.char.lower()

                if char == 's':
                    self._toggle_acquisition()
                elif char == 'm':
                    self._toggle_monitor()
                elif char == 'r':
                    self._reload_config()
                elif char == 'q':
                    self._quit()
                elif char == 'h':
                    self._print_help()

        except AttributeError:
            # Special key (not a character), ignore
            pass

        except Exception as e:
            self.logger.error(f"Error handling key press: {e}")

    def _toggle_acquisition(self):
        """Toggle acquisition on/off"""
        if self.orchestrator.is_acquiring():
            self.logger.info("User pressed 's' - STOPPING acquisition")
            self.orchestrator.stop_acquisition()
        else:
            self.logger.info("User pressed 's' - STARTING acquisition")
            self.orchestrator.start_acquisition()

    def _toggle_monitor(self):
        """Toggle monitor display on/off"""
        if self.orchestrator.display:
            self.orchestrator.display.toggle()
            state = "ON" if self.orchestrator.display.is_enabled() else "OFF"
            self.logger.info(f"User pressed 'm' - Monitor display {state}")
        else:
            self.logger.warning("Monitor display not available")

    def _reload_config(self):
        """Reload configuration files"""
        self.logger.info("User pressed 'r' - Reloading configuration")
        try:
            self.orchestrator.reload_configuration()
            self.logger.info("Configuration reloaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to reload configuration: {e}")

    def _quit(self):
        """Quit program"""
        self.logger.info("User pressed 'q' - Quitting DAQ system")
        self.orchestrator.request_stop()

    def _print_help(self):
        """Print keyboard commands"""
        help_text = """
╔════════════════════════════════════════════════════════════╗
║              DAQ Keyboard Commands                         ║
╠════════════════════════════════════════════════════════════╣
║  s  - Start/Stop acquisition                               ║
║  m  - Toggle monitor display (on/off)                      ║
║  r  - Reload configuration files                           ║
║  h  - Show this help                                       ║
║  q  - Quit program                                         ║
╚════════════════════════════════════════════════════════════╝
        """
        print(help_text)


def main():
    """Test KeyboardHandler"""
    import time
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from utils.logger import setup_logging

    setup_logging(level="INFO")
    logger = logging.getLogger("KeyboardHandlerTest")

    # Create a mock orchestrator for testing
    class MockOrchestrator:
        def __init__(self):
            self.acquiring = False
            self.display = None
            self.stop_requested = False
            self.logger = logging.getLogger("MockOrchestrator")

        def is_acquiring(self):
            return self.acquiring

        def start_acquisition(self):
            self.logger.info(">>> MOCK: Starting acquisition")
            self.acquiring = True

        def stop_acquisition(self):
            self.logger.info(">>> MOCK: Stopping acquisition")
            self.acquiring = False

        def reload_configuration(self):
            self.logger.info(">>> MOCK: Reloading configuration")

        def request_stop(self):
            self.logger.info(">>> MOCK: Stop requested")
            self.stop_requested = True

    # Create mock orchestrator
    orchestrator = MockOrchestrator()

    # Create and start keyboard handler
    try:
        keyboard_handler = KeyboardHandler(orchestrator)
        keyboard_handler.start()

        logger.info("\nKeyboard handler test running...")
        logger.info("Try pressing keys: s, m, r, h, q")
        logger.info("Press 'q' to quit\n")

        # Run until quit is requested
        while not orchestrator.stop_requested:
            time.sleep(0.5)

        logger.info("\nKeyboard handler test completed")
        keyboard_handler.stop()

    except ImportError as e:
        logger.error(f"pynput not available: {e}")
        logger.error("Install with: pip install pynput")
        sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        if 'keyboard_handler' in locals():
            keyboard_handler.stop()


if __name__ == "__main__":
    main()
