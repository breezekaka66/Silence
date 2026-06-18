"""
VB-Cable Detection — Check if VB-Cable virtual audio driver is installed.

VB-Cable creates audio devices named:
  Input:  "CABLE Input (VB-Audio Virtual Cable)"
  Output: "CABLE Output (VB-Audio Virtual Cable)"

We detect these by querying sounddevice's device list.
"""
import logging

logger = logging.getLogger(__name__)

VBCABLE_INPUT_NAME = "CABLE Input"    # Partial match
VBCABLE_OUTPUT_NAME = "CABLE Output"  # Partial match
VBCABLE_DOWNLOAD_URL = "https://vb-audio.com/Cable/"


def check_vbcable() -> bool:
    """
    Check if VB-Cable is installed by scanning audio devices.

    Returns:
        True if both CABLE Input and CABLE Output are found.
    """
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        names = [d["name"] for d in devices]

        has_input = any(VBCABLE_INPUT_NAME in name for name in names)
        has_output = any(VBCABLE_OUTPUT_NAME in name for name in names)

        if has_input and has_output:
            logger.info("VB-Cable detected.")
            return True
        else:
            logger.warning(
                f"VB-Cable not found. "
                f"Input: {has_input}, Output: {has_output}. "
                f"Download from: {VBCABLE_DOWNLOAD_URL}"
            )
            return False

    except Exception as e:
        logger.error(f"Failed to check VB-Cable: {e}")
        return False


def find_vbcable_input_index() -> int | None:
    """Return the device index for CABLE Input, or None if not found."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if VBCABLE_INPUT_NAME in dev["name"] and dev["max_output_channels"] > 0:
                return i
        return None
    except Exception:
        return None


def find_vbcable_output_index() -> int | None:
    """Return the device index for CABLE Output, or None if not found."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if VBCABLE_OUTPUT_NAME in dev["name"] and dev["max_input_channels"] > 0:
                return i
        return None
    except Exception:
        return None
