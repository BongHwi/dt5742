# CAEN DT5742 Real-Time Data Monitor

A C++ program for real-time monitoring of CAEN DT5742 digitizer data in both binary (`.dat`) and text (`.txt`) formats.

## Features

1. **Real-Time Event Number Tracking** - Continuously updates the latest event number
2. **Data Acquisition Rate Monitoring** - Displays events per second (evt/s) or events per minute (evt/min)
3. **Multiple File Format Support**
   - Binary files (`.dat`) - Header + waveform binary format
   - ASCII text files (`.txt`) - WaveDump text output format
   - Automatic detection based on file extension
4. **Waveform Quality Assurance (QA)**
   - Baseline stability check (target: 3500V)
   - Signal range validation
   - Noise level measurement

## Build Instructions

### Requirements

- C++17 compiler (g++ or clang++)
- simdjson library

Install simdjson on macOS:
```bash
brew install simdjson
```

### Compilation

```bash
cd /Users/blim/EIC/caen/dt5742/daq_monitor
make
```

This will create the `monitor_realtime` executable.

## Usage

### Basic Usage

```bash
# Use default configuration file (monitor_config.json)
./monitor_realtime

# Monitor binary file (.dat)
./monitor_realtime --file ../Data/AC_LGAD_TEST/wave_0.dat

# Monitor ASCII text file (.txt)
./monitor_realtime --file ../Data/AC_LGAD_TEST/wave_0.txt

# Fast monitoring without QA checks
./monitor_realtime --no-qa

# Use custom configuration file
./monitor_realtime --config my_config.json
```

**Automatic File Format Detection**:
- `.txt` or `.ascii` extension → ASCII mode
- `.dat` or other extensions → Binary mode

### Command-Line Options

- `--config FILE`: Configuration file path (default: monitor_config.json)
- `--file FILE`: Input binary file path (overrides config setting)
- `--no-qa`: Disable QA checks (faster monitoring)
- `--help`: Display help message

### Stopping

Press `Ctrl+C` during monitoring to stop the program and display final summary statistics.

## Configuration File (monitor_config.json)

```json
{
  "monitor": {
    "input_file": "../Data/AC_LGAD_TEST/wave_0.dat",
    "polling_interval_ms": 1000,
    "display_update_interval_ms": 1000,
    "rate_window_seconds": 10,

    "qa_enabled": true,
    "qa_sampling_interval": 10,
    "qa_pedestal_samples": 100,
    "qa_baseline_target": 3500.0,
    "qa_baseline_tolerance": 50.0,
    "qa_noise_threshold": 10.0,
    "qa_signal_min": -1000.0,
    "qa_signal_max": 5000.0,

    "log_warnings": true,
    "log_file": "monitor.log"
  }
}
```

### Configuration Parameters

#### File Monitoring Settings
- `input_file`: Path to the .dat file to monitor
- `polling_interval_ms`: File check interval (milliseconds, default 1000ms = 1 second)
- `display_update_interval_ms`: Screen update interval (milliseconds)
- `rate_window_seconds`: Rate calculation window size (seconds, default 10 seconds)

#### QA Settings
- `qa_enabled`: Enable/disable QA checks
- `qa_sampling_interval`: QA sampling interval (10 means check every 10th event)
- `qa_pedestal_samples`: Number of samples for baseline calculation
- `qa_baseline_target`: Target baseline value (Volts)
- `qa_baseline_tolerance`: Baseline tolerance (Volts)
- `qa_noise_threshold`: Noise threshold (Volts RMS)
- `qa_signal_min`: Signal minimum value (Volts)
- `qa_signal_max`: Signal maximum value (Volts)

#### Logging Settings
- `log_warnings`: Enable warning log file
- `log_file`: Log file path

## Output Examples

### Normal Monitoring

```
CAEN DT5742 Real-Time Monitor
Configuration: monitor_config.json
Input file: ../Data/AC_LGAD_TEST/wave_0.dat
QA enabled: yes

Monitoring started. Press Ctrl+C to stop.

[17:23:47] Event: 85 | Rate: 42.5 evt/s | Total: 85 | QA: OK=8 WARN=0 ERR=0 | Runtime: 00:00:03
```

### QA Warning

```
[17:24:12] Event: 1523 | Rate: 42.3 evt/s | Total: 1523 | QA: OK=152 WARN=1 ERR=0 | Runtime: 00:00:35
[WARNING] Event 1456: Baseline deviation = 75.2V (target: 3500V)
```

### Final Summary (Ctrl+C exit)

```
Received Ctrl+C, stopping monitor...

═════════════════════════════════════════════════════
         Monitoring Session Summary
═════════════════════════════════════════════════════
  Total Events:       1523
  Latest Event:       1523
  Event Gaps:         0
  Runtime:            00:00:35
  Average Rate:       43.5 evt/s

  QA Checks:          152
    OK:               151 (99.3%)
    Warnings:         1
    Errors:           0
    Avg Baseline:     3498.2 V
    Avg Noise:        4.3 V RMS
═════════════════════════════════════════════════════
```

## How It Works

### File Monitoring

The program uses **polling** to monitor files:

1. Check file size every second
2. If file has grown, read only the newly added portion
3. Store the last read position to avoid duplicate reads

### File Format Processing

#### Binary Mode (.dat)
- **Incremental Reading**: Saves file pointer to read only new data
- **Event Extraction**: Extracts event number from 32-byte header

```
Offset  Size    Field
0x00    4       Event size (bytes)
0x04    4       Board ID
0x08    4       Pattern
0x0C    4       Channel ID
0x10    4       Event counter  ★ Event number
0x14    4       Trigger time tag
0x18    4       Reserved
0x1C    4       Reserved
```

#### ASCII Mode (.txt)
- **Full Reload**: Reparses entire file when file size increases
- **Event Extraction**: Extracts event number from "Event Number: N" header
- **Caching**: Skips previously read events and processes only new events

ASCII file format example:
```
Record Length: 1024
BoardID: 0
Channel: 0
Event Number: 123
3500.2
3498.5
...
```

### Rate Calculation

Uses a **moving average window** (default 10 seconds) for stable rate calculation:
- Maintains event history for the last 10 seconds
- Divides event count by time span to calculate evt/s

### QA Checks

Uses **sampling** for performance (default: 1 in every 10 events):

1. **Baseline Check**: Calculate average of first 100 samples
2. **Noise Estimation**: Calculate RMS of baseline region
3. **Signal Range**: Check waveform min/max values

## File Structure

```
daq_monitor/
├── include/
│   ├── config/
│   │   └── monitor_config.h
│   ├── monitor/
│   │   └── realtime_monitor.h
│   └── utils/
│       ├── file_io.h
│       └── json_utils.h
├── src/
│   ├── config/
│   │   └── monitor_config.cpp
│   ├── monitor/
│   │   └── realtime_monitor.cpp
│   ├── utils/
│   │   └── file_io.cpp
│   └── monitor_realtime.cpp (main)
├── Makefile
├── monitor_config.json
└── README.md
```

## Troubleshooting

### File Not Found

```
Error: Cannot open file ../Data/AC_LGAD_TEST/wave_0.dat
```

**Solution**:
- Check the `input_file` path in `monitor_config.json`
- Or specify the correct path with `--file` option

### simdjson Library Error

```
dyld: Library not loaded: /opt/homebrew/lib/libsimdjson.dylib
```

**Solution**:
```bash
brew install simdjson
```

### Compilation Error

```
fatal error: 'simdjson.h' file not found
```

**Solution**: Check the `INCLUDES` path in Makefile
```makefile
INCLUDES = -Iinclude -I. -I/opt/homebrew/include
```

## Performance

### Binary Mode
- **CPU Usage**: Very low (sleeps during polling wait)
- **Memory**: Waveform vectors created/destroyed per event, no leaks
- **I/O**: Incremental reading prevents duplicate reads (very efficient)

### ASCII Mode
- **CPU Usage**: Slightly higher than binary (parsing overhead)
- **Memory**: Caches full event list in memory
- **I/O**: Full reload on each file update (can be slow for large files)

**Recommended Settings**:
- `polling_interval_ms`: 1000 (1 second) - Balance between real-time feel and load
- `qa_sampling_interval`: 10 - 10% QA overhead, sufficient coverage
- **Large ASCII files**: Binary mode recommended

## Future Improvements

1. **Multi-Channel Monitoring**: Simultaneous monitoring of all 16 channels
2. **Dashboard UI**: Multi-line dashboard using ncurses
3. **Real-Time Plotting**: Waveform display with ROOT TCanvas
4. **Web Interface**: HTTP server for remote monitoring
5. **Alert System**: Email/Slack notifications on QA failures

## License

This project is part of the CAEN DT5742 digitizer data analysis pipeline.

## Contact

Please file an issue if you encounter problems or have suggestions for improvement.
