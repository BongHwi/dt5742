"""
Configuration Mapper

Maps parsed WaveDumpConfig settings to py-caen-libs Device API calls
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from caen_libs import caendigitizer as dgtz
    from .wavedump_parser import WaveDumpConfig


def apply_wavedump_config(device: 'dgtz.Device', config: 'WaveDumpConfig'):
    """
    Apply WaveDumpConfig settings to a CAEN digitizer device

    This function maps parsed configuration parameters to the appropriate
    py-caen-libs API calls for DT5742 digitizers.

    Args:
        device: Opened CAEN digitizer device (py-caen-libs Device object)
        config: Parsed WaveDumpConfig settings

    Raises:
        Exception: If configuration cannot be applied
    """
    logger = logging.getLogger("ConfigMapper")
    logger.info("Applying WaveDumpConfig to digitizer...")

    # Import here to avoid circular dependency
    from caen_libs import caendigitizer as dgtz

    # 1. DRS4 Sampling Frequency (CRITICAL for DT5742!)
    freq_map = {
        0: dgtz.DRS4Frequency._5GHz,
        1: dgtz.DRS4Frequency._2_5GHz,
        2: dgtz.DRS4Frequency._1GHz,
        3: dgtz.DRS4Frequency._750MHz
    }
    drs4_freq = freq_map.get(config.drs4_frequency, dgtz.DRS4Frequency._5GHz)
    device.set_drs4_sampling_frequency(drs4_freq)
    logger.debug(f"Set DRS4 frequency: {config.drs4_frequency} ({drs4_freq.name})")

    # 2. Load DRS4 Correction Data (ESSENTIAL for accurate measurements!)
    logger.info("Loading DRS4 correction data from EEPROM...")
    device.load_drs4_correction_data(drs4_freq)
    device.enable_drs4_correction()
    logger.debug("DRS4 correction enabled")

    # 3. Record Length
    device.set_record_length(config.record_length)
    logger.debug(f"Set record length: {config.record_length} samples")

    # 4. Post-Trigger Size (percentage)
    device.set_post_trigger_size(config.post_trigger)
    logger.debug(f"Set post-trigger: {config.post_trigger}%")

    # 5. Group Enable Mask (DT5742 has 4 groups)
    group_mask = 0
    for group_id in range(4):
        # Default to enabled if not specified
        if config.group_enabled.get(group_id, group_id < 2):  # Enable groups 0,1 by default
            group_mask |= (1 << group_id)
    device.set_group_enable_mask(group_mask)
    logger.debug(f"Set group enable mask: 0x{group_mask:X} (binary: {bin(group_mask)})")

    # 6. External Trigger Mode
    trigger_mode_map = {
        "DISABLED": dgtz.TriggerMode.DISABLED,
        "ACQUISITION_ONLY": dgtz.TriggerMode.ACQ_ONLY,
        "ACQUISITION_AND_TRGOUT": dgtz.TriggerMode.ACQ_AND_EXTOUT
    }
    ext_trigger_mode = trigger_mode_map.get(
        config.external_trigger,
        dgtz.TriggerMode.DISABLED
    )
    device.set_ext_trigger_input_mode(ext_trigger_mode)
    logger.debug(f"Set external trigger: {config.external_trigger}")

    # 7. Fast Trigger Mode (for TR0)
    fast_trigger_mode = trigger_mode_map.get(
        config.fast_trigger,
        dgtz.TriggerMode.DISABLED
    )
    device.set_fast_trigger_mode(fast_trigger_mode)
    logger.debug(f"Set fast trigger: {config.fast_trigger}")

    # 8. Software Trigger Mode
    sw_trigger_mode = trigger_mode_map.get(
        config.sw_trigger,
        dgtz.TriggerMode.DISABLED
    )
    device.set_sw_trigger_mode(sw_trigger_mode)
    logger.debug(f"Set software trigger: {config.sw_trigger}")

    # 9. Fast Trigger Settings (TR0)
    if config.tr0_enabled:
        # Set fast trigger threshold for group 0
        device.set_group_fast_trigger_threshold(0, config.tr0_trigger_threshold)
        logger.debug(f"Set TR0 threshold: {config.tr0_trigger_threshold} ADC counts")

        # Set fast trigger DC offset
        device.set_group_fast_trigger_dc_offset(0, config.tr0_dc_offset)
        logger.debug(f"Set TR0 DC offset: {config.tr0_dc_offset} ADC counts")

        # Enable fast trigger digitizing
        device.set_fast_trigger_digitizing(dgtz.EnaDis.ENABLE)
        logger.debug("Fast trigger digitizing enabled")

    # 10. Group DC Offsets
    for group_id, offset in config.group_dc_offset.items():
        # Convert percentage to ADC counts if needed
        if -100 <= offset <= 100:
            # Percentage: map -100..100 -> 0..65535
            adc_offset = int((offset + 100) / 200.0 * 65535)
            logger.debug(
                f"Group {group_id} DC offset: {offset}% -> {adc_offset} ADC counts"
            )
        else:
            # Already in ADC counts
            adc_offset = int(offset)
            logger.debug(f"Group {group_id} DC offset: {adc_offset} ADC counts")

        device.set_group_dc_offset(group_id, adc_offset)

    # 11. I/O Level
    io_level_map = {
        "NIM": dgtz.IOLevel.NIM,
        "TTL": dgtz.IOLevel.TTL
    }
    io_level = io_level_map.get(config.fpio_level, dgtz.IOLevel.NIM)
    device.set_io_level(io_level)
    logger.debug(f"Set I/O level: {config.fpio_level}")

    # 12. Max Number of Events per BLT
    if config.max_num_events_blt > 0:
        device.set_max_num_events_blt(config.max_num_events_blt)
        logger.debug(f"Set max events BLT: {config.max_num_events_blt}")

    # 13. Acquisition Mode
    acq_mode_map = {
        "SW_CONTROLLED": dgtz.AcqMode.SW_CONTROLLED,
        "S_IN_CONTROLLED": dgtz.AcqMode.S_IN_CONTROLLED,
        "FIRST_TRG_CONTROLLED": dgtz.AcqMode.FIRST_TRG_CONTROLLED
    }
    acq_mode = acq_mode_map.get(config.acquisition_mode, dgtz.AcqMode.SW_CONTROLLED)
    device.set_acquisition_mode(acq_mode)
    logger.debug(f"Set acquisition mode: {config.acquisition_mode}")

    # 14. Direct Register Writes (advanced)
    if config.register_writes:
        logger.info(f"Applying {len(config.register_writes)} register write(s)...")
        for addr, data, mask in config.register_writes:
            if mask == 0xFFFFFFFF:
                # Full write
                device.registers[addr] = data
                logger.debug(f"  Register 0x{addr:04X} = 0x{data:08X}")
            else:
                # Masked write: preserve bits outside mask
                old_value = device.registers[addr]
                new_value = (old_value & ~mask) | (data & mask)
                device.registers[addr] = new_value
                logger.debug(
                    f"  Register 0x{addr:04X} = 0x{new_value:08X} "
                    f"(mask: 0x{mask:08X})"
                )

    # 15. Allocate Buffers (required before acquisition)
    logger.info("Allocating readout buffers...")
    device.malloc_readout_buffer()
    device.allocate_event()

    logger.info("Configuration applied successfully")


def get_sampling_period_ns(drs4_frequency: int) -> float:
    """
    Get sampling period in nanoseconds for a given DRS4 frequency setting

    Args:
        drs4_frequency: DRS4 frequency index (0=5GHz, 1=2.5GHz, 2=1GHz, 3=750MHz)

    Returns:
        Sampling period in nanoseconds
    """
    period_map = {
        0: 0.2,    # 5 GHz -> 0.2 ns
        1: 0.4,    # 2.5 GHz -> 0.4 ns
        2: 1.0,    # 1 GHz -> 1.0 ns
        3: 1.333   # 750 MHz -> 1.333 ns
    }
    return period_map.get(drs4_frequency, 0.2)


def get_channel_count(group_mask: int) -> int:
    """
    Get total number of enabled channels based on group enable mask

    DT5742 has 4 groups, each with 9 channels (8 data + 1 fast trigger)

    Args:
        group_mask: Group enable mask (bit 0 = group 0, bit 1 = group 1, etc.)

    Returns:
        Total number of enabled channels
    """
    enabled_groups = bin(group_mask).count('1')
    return enabled_groups * 9  # 9 channels per group


def main():
    """Test configuration mapper"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from config.wavedump_parser import WaveDumpConfigParser
    from utils.logger import setup_logging

    setup_logging(level="DEBUG")

    logger = logging.getLogger("ConfigMapperTest")

    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        config_file = "../../WaveDumpConfig_USB0.txt"

    try:
        # Parse configuration
        config = WaveDumpConfigParser.parse(config_file)

        logger.info(f"\nParsed configuration from: {config_file}")
        logger.info(f"  DRS4 Frequency: {config.drs4_frequency}")
        logger.info(f"  Sampling Period: {get_sampling_period_ns(config.drs4_frequency)} ns")
        logger.info(f"  Record Length: {config.record_length} samples")
        logger.info(f"  External Trigger: {config.external_trigger}")

        # Calculate group mask
        group_mask = 0
        for group_id in range(4):
            if config.group_enabled.get(group_id, group_id < 2):
                group_mask |= (1 << group_id)

        logger.info(f"  Enabled Channels: {get_channel_count(group_mask)}")

        logger.info("\nNote: To actually apply configuration, a connected digitizer is required")
        logger.info("This test only demonstrates parsing and mapping logic")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    from pathlib import Path
    main()
