"""
Waveform Display

Real-time waveform visualization using matplotlib
"""

import logging
import queue
import numpy as np
from typing import Dict, Optional, TYPE_CHECKING
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('TkAgg')  # Use TkAgg backend for non-blocking display
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    import matplotlib.gridspec as gridspec
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

if TYPE_CHECKING:
    from caen_libs import caendigitizer as dgtz
    from config.daq_config import MonitorConfig


class WaveformDisplay:
    """
    Real-time waveform display using matplotlib

    Displays selected channels from one digitizer in real-time,
    updated periodically via FuncAnimation.
    """

    def __init__(self, config: 'MonitorConfig', n_digitizers: int):
        """
        Initialize WaveformDisplay

        Args:
            config: MonitorConfig with display settings
            n_digitizers: Total number of digitizers

        Raises:
            ImportError: If matplotlib is not available
        """
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("matplotlib not installed. Install with: pip install matplotlib")

        self.config = config
        self.n_digitizers = n_digitizers
        self.enabled = config.enabled
        self.update_interval_ms = config.update_interval_ms
        self.display_channels = config.display_channels
        self.display_digitizer = config.display_digitizer

        # Event queue (thread-safe)
        self.event_queue = queue.Queue(maxsize=100)

        # Latest waveforms to display
        self.latest_waveforms: Dict[int, np.ndarray] = {}
        self.latest_event_num: int = 0

        # Matplotlib objects
        self.fig = None
        self.axes = []
        self.lines: Dict[int, plt.Line2D] = {}
        self.animation = None

        self.logger = logging.getLogger("WaveformDisplay")

        if self.enabled:
            self._setup_plot()

    def _setup_plot(self):
        """Create matplotlib figure with subplots"""
        n_channels = len(self.display_channels)
        if n_channels == 0:
            self.logger.warning("No channels selected for display")
            return

        # Calculate grid layout
        n_cols = 2
        n_rows = (n_channels + 1) // 2

        # Create figure
        self.fig = plt.figure(figsize=(12, 3 * n_rows))
        self.fig.suptitle(
            f"Digitizer USB{self.display_digitizer} - Real-time Waveforms"
        )

        # Create grid
        gs = gridspec.GridSpec(n_rows, n_cols, figure=self.fig)
        self.axes = []
        self.lines = {}

        # Create subplot for each channel
        for i, ch_id in enumerate(self.display_channels):
            row = i // n_cols
            col = i % n_cols
            ax = self.fig.add_subplot(gs[row, col])

            # Configure axis
            group_id = ch_id // 9
            ch_in_group = ch_id % 9
            ax.set_title(f"Group {group_id}, Channel {ch_in_group}")
            ax.set_xlabel("Sample")
            ax.set_ylabel("Amplitude (V)")
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.set_xlim(0, self.config.plot_samples)
            ax.set_ylim(-1, 1)  # Will auto-scale later

            # Create empty line
            line, = ax.plot([], [], 'b-', linewidth=0.8)
            self.lines[ch_id] = line
            self.axes.append(ax)

        plt.tight_layout()

        # Start animation
        self.animation = FuncAnimation(
            self.fig,
            self._update_plot,
            interval=self.update_interval_ms,
            blit=False,
            cache_frame_data=False
        )

        # Show in non-blocking mode
        plt.ion()
        plt.show(block=False)

        self.logger.info(
            f"Display initialized: {n_channels} channels, "
            f"{self.update_interval_ms}ms update interval"
        )

    def add_event(self, digitizer_id: int, evt: 'dgtz.X742Event'):
        """
        Add event to display queue (called from acquisition thread)

        Args:
            digitizer_id: Which digitizer this event came from
            evt: X742Event containing waveform data
        """
        if not self.enabled:
            return

        # Only display events from the selected digitizer
        if digitizer_id != self.display_digitizer:
            return

        try:
            # Add to queue (non-blocking, drop if full)
            self.event_queue.put_nowait((digitizer_id, evt))
        except queue.Full:
            # Queue full, drop old event
            pass

    def _update_plot(self, frame):
        """
        Update plot with latest waveforms (called by FuncAnimation)

        Args:
            frame: Frame number (not used)
        """
        if not self.enabled:
            return

        # Drain event queue
        events_processed = 0
        while not self.event_queue.empty() and events_processed < 10:
            try:
                digitizer_id, evt = self.event_queue.get_nowait()
                self._process_event(evt)
                events_processed += 1
            except queue.Empty:
                break

        # Update lines with latest waveforms
        for ch_id in self.display_channels:
            if ch_id in self.latest_waveforms:
                waveform = self.latest_waveforms[ch_id]
                samples = np.arange(len(waveform))

                # Update line data
                self.lines[ch_id].set_data(samples, waveform)

                # Auto-scale y-axis
                ax_idx = self.display_channels.index(ch_id)
                if ax_idx < len(self.axes):
                    ax = self.axes[ax_idx]
                    ax.relim()
                    ax.autoscale_view(scalex=False, scaley=True)

        # Update title with event number
        if self.latest_event_num > 0:
            self.fig.suptitle(
                f"Digitizer USB{self.display_digitizer} - "
                f"Event {self.latest_event_num}"
            )

        # Draw canvas
        try:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
        except:
            pass

    def _process_event(self, evt: 'dgtz.X742Event'):
        """
        Extract waveforms from X742Event

        Args:
            evt: X742Event from digitizer
        """
        for ch_id in self.display_channels:
            group_id = ch_id // 9
            ch_in_group = ch_id % 9

            # Check if group exists
            if group_id >= len(evt.data_group):
                continue

            group = evt.data_group[group_id]
            if group is None:
                continue

            # Check if channel exists in group
            if ch_in_group >= len(group.data_channel):
                continue

            waveform = group.data_channel[ch_in_group]
            if waveform is not None and len(waveform) > 0:
                self.latest_waveforms[ch_id] = waveform

        self.latest_event_num += 1

    def toggle(self):
        """Toggle display on/off"""
        self.enabled = not self.enabled

        if self.enabled:
            if self.fig is None:
                self._setup_plot()
            else:
                try:
                    plt.show(block=False)
                except:
                    pass
            self.logger.info("Display enabled")
        else:
            if self.fig:
                try:
                    plt.close(self.fig)
                except:
                    pass
            self.logger.info("Display disabled")

    def is_enabled(self) -> bool:
        """Check if display is enabled"""
        return self.enabled

    def close(self):
        """Close display and clean up"""
        self.logger.info("Closing display...")

        if self.animation:
            try:
                self.animation.event_source.stop()
            except:
                pass

        if self.fig:
            try:
                plt.close(self.fig)
            except:
                pass

        self.enabled = False


def main():
    """Test WaveformDisplay"""
    import time
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from config.daq_config import MonitorConfig
    from utils.logger import setup_logging

    setup_logging(level="INFO")
    logger = logging.getLogger("WaveformDisplayTest")

    # Create test configuration
    config = MonitorConfig(
        enabled=True,
        update_interval_ms=500,
        display_channels=[0, 1, 8, 9],
        display_digitizer=0
    )

    try:
        # Create display
        display = WaveformDisplay(config=config, n_digitizers=1)

        logger.info("Display test running...")
        logger.info("Generating fake waveforms...")
        logger.info("Press Ctrl+C to stop\n")

        # Generate fake events
        from caen_libs import caendigitizer as dgtz
        from dataclasses import dataclass
        import numpy as np

        # Create mock X742Event structure
        @dataclass
        class MockX742Group:
            data_channel: list
            trigger_time_tag: int = 0
            start_index_cell: int = 0

        @dataclass
        class MockX742Event:
            data_group: list

        # Simulate events
        event_num = 0
        while True:
            # Create fake waveforms
            groups = []
            for group_id in range(4):
                channels = []
                for ch_id in range(9):
                    # Generate sine wave with noise
                    samples = np.arange(1024)
                    waveform = (
                        np.sin(2 * np.pi * samples / 100 + event_num * 0.1) * 0.5 +
                        np.random.normal(0, 0.05, 1024)
                    ).astype(np.float32)
                    channels.append(waveform)

                groups.append(MockX742Group(data_channel=channels))

            evt = MockX742Event(data_group=groups)

            # Add to display
            display.add_event(0, evt)

            event_num += 1
            time.sleep(0.05)  # ~20 Hz

    except ImportError as e:
        logger.error(f"matplotlib or caen-libs not available: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\n\nTest stopped by user")
        display.close()


if __name__ == "__main__":
    main()
