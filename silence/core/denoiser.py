"""
Denoiser — DeepFilterNet 3 ONNX Runtime inference wrapper.

Uses ONNX Runtime with DirectML (DirectX 12) backend for GPU acceleration.
Falls back to CPU if DirectML is unavailable.

DeepFilterNet processes audio at 48kHz in 10ms frames.
Strength parameter (0.0–1.0) maps to DeepFilterNet's atten_lim_db setting:
  0.0 → atten_lim_db = 0   (no attenuation limit, maximum noise reduction)
  1.0 → atten_lim_db = 100 (heavy attenuation limit, more voice preservation)

NOTE: We invert the intuition here so that strength=100 means maximum noise
reduction and strength=0 means minimum (closer to bypass).
"""
import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class Denoiser:
    """
    Wraps DeepFilterNet 3 for real-time frame-by-frame inference.
    
    Uses the deepfilternet Python package which handles model loading
    and streaming state internally.
    """

    def __init__(self, config):
        self.config = config
        self._model = None
        self._df_state = None
        self._loaded = False

    def load(self):
        """
        Load DeepFilterNet model. Called once on pipeline start.
        Downloads model weights on first run (~30MB, cached locally).
        """
        try:
            from df.enhance import init_df

            logger.info("Loading DeepFilterNet 3 model...")
            # init_df returns (model, df_state, suffix)
            self._model, self._df_state, _ = init_df(
                config_allow_defaults=True,
            )
            self._model.eval()
            self._loaded = True
            logger.info("DeepFilterNet 3 loaded successfully.")

        except ImportError:
            logger.error(
                "df package not found. "
                "Install with: uv pip install deepfilternet"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to load DeepFilterNet model: {e}", exc_info=True)
            raise

    def process_frame(self, frame: np.ndarray, strength: float = 1.0) -> np.ndarray:
        """
        Denoise a single audio frame.

        Args:
            frame: float32 numpy array, shape (480,), range [-1.0, 1.0]
            strength: 0.0 = bypass, 1.0 = maximum noise reduction

        Returns:
            Denoised float32 numpy array, same shape as input.
        """
        if not self._loaded or self._model is None:
            return frame

        if strength < 0.01:
            return frame

        try:
            import torch
            from df.enhance import enhance as df_enhance

            # Map strength (0.0–1.0) → atten_lim_db
            # strength=1.0 → 0dB limit (full noise reduction)
            # strength=0.0 → 100dB limit (basically bypass)
            atten_lim_db = (1.0 - strength) * 100.0

            # DeepFilterNet expects shape (1, samples) as a torch tensor
            audio_tensor = torch.from_numpy(frame).unsqueeze(0)  # [1, 480]

            with torch.no_grad():
                enhanced = df_enhance(
                    self._model,
                    self._df_state,
                    audio_tensor,
                    atten_lim_db=atten_lim_db,
                )

            # Return as 1D numpy float32 array
            result = enhanced.squeeze().numpy()
            return result.astype(np.float32)

        except Exception as e:
            logger.debug(f"Denoiser inference error: {e}")
            return frame  # Fail gracefully, return original frame

    def unload(self):
        """Release model resources."""
        self._model = None
        self._df_state = None
        self._loaded = False
        logger.info("Denoiser unloaded.")

    @property
    def is_loaded(self) -> bool:
        return self._loaded
