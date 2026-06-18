"""
VU Meter — Real-time audio level metering.

Calculates RMS (dBFS) and peak levels per audio frame.
Used to drive the GUI VU Meter widget.

dBFS scale:
  0 dBFS  = full scale (clipping)
 -6 dBFS  = very loud (red zone)
 -18 dBFS = normal speech level (yellow zone)
 -60 dBFS = near silence (green zone)
 -∞ dBFS  = digital silence
"""
import numpy as np

# VU Meter zone thresholds (dBFS)
VU_RED_THRESHOLD = -6.0      # Above this: RED
VU_YELLOW_THRESHOLD = -18.0  # Above this: YELLOW, below: GREEN
VU_FLOOR_DB = -80.0          # Minimum displayable level


class VUMeter:
    """
    Stateless per-frame audio level calculator.
    
    Also maintains a peak-hold value with decay for the GUI needle.
    """

    def __init__(self, sample_rate: int = 48000, peak_hold_ms: float = 1500):
        self._sample_rate = sample_rate
        self._peak_hold_ms = peak_hold_ms
        self._peak_db: float = VU_FLOOR_DB
        self._peak_hold_counter: int = 0
        self._peak_hold_samples: int = int(sample_rate * peak_hold_ms / 1000)

    def process(self, frame: np.ndarray) -> tuple[float, float]:
        """
        Process one audio frame and return (rms_db, peak_db).

        Args:
            frame: float32 array, values in [-1.0, 1.0]

        Returns:
            (rms_db, peak_db): both in dBFS, floored at VU_FLOOR_DB
        """
        # RMS level
        rms = float(np.sqrt(np.mean(frame ** 2)))
        rms_db = self._linear_to_db(rms)

        # Instantaneous peak
        instant_peak = float(np.max(np.abs(frame)))
        instant_peak_db = self._linear_to_db(instant_peak)

        # Peak hold with decay
        if instant_peak_db >= self._peak_db:
            self._peak_db = instant_peak_db
            self._peak_hold_counter = self._peak_hold_samples
        else:
            if self._peak_hold_counter > 0:
                self._peak_hold_counter -= len(frame)
            else:
                # Decay peak at 10dB/second
                decay_per_frame = 10.0 * len(frame) / self._sample_rate
                self._peak_db = max(VU_FLOOR_DB, self._peak_db - decay_per_frame)

        return rms_db, self._peak_db

    def reset(self):
        """Reset peak hold state."""
        self._peak_db = VU_FLOOR_DB
        self._peak_hold_counter = 0

    @staticmethod
    def _linear_to_db(linear: float) -> float:
        """Convert linear amplitude to dBFS."""
        if linear <= 0.0:
            return VU_FLOOR_DB
        db = 20.0 * np.log10(max(linear, 1e-10))
        return max(db, VU_FLOOR_DB)

    @staticmethod
    def db_to_color(db: float) -> str:
        """Return color name for a given dBFS level."""
        if db >= VU_RED_THRESHOLD:
            return "red"
        elif db >= VU_YELLOW_THRESHOLD:
            return "yellow"
        else:
            return "green"

    @staticmethod
    def db_to_fraction(db: float, floor_db: float = VU_FLOOR_DB) -> float:
        """Convert dBFS to 0.0–1.0 fraction for progress bar display."""
        clamped = max(floor_db, min(0.0, db))
        return (clamped - floor_db) / (0.0 - floor_db)
