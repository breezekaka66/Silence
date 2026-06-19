"""
Denoiser — DeepFilterNet 3 streaming inference wrapper.

Key design decisions:
  1. atten_lim_db mapping is CORRECT here:
       strength=0   -> atten_lim_db=0    -> mask clamped >= 1.0 -> NO noise reduction (bypass)
       strength=0.5 -> atten_lim_db=50   -> up to -50 dB attenuation allowed
       strength=1.0 -> atten_lim_db=None -> unlimited attenuation (full model power)
     Previous code had this INVERTED, which caused noise reduction to do nothing at strength=100.

  2. Model runs on CPU by default.
     DeepFilterNet 3 RTF on modern CPU is ~0.03-0.05, meaning each 10 ms frame
     takes only ~0.3-0.5 ms — well within budget. CUDA can be enabled but the
     df_state STFT analysis stage (Rust/CPU) is often the bottleneck anyway.

  3. torch.inference_mode() is used instead of torch.no_grad():
       - Disables autograd engine entirely (lower overhead, no accidental leaks)
       - Cannot use .requires_grad_() inside, which we don't need

  4. Intermediate tensors are explicitly deleted each frame to prevent PyTorch's
     CPU allocator from accumulating reference-counted blocks. Combined with
     AudioPipeline's periodic gc.collect(), this keeps RSS stable over time.

  5. pad=False in df_enhance avoids zero-padding that adds algorithmic latency
     and produces a longer output than the input frame.

  6. Output gain compensation (+3 dB default) corrects DeepFilterNet's tendency
     to lower the overall level when aggressively attenuating noise.
"""
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Post-processing gain ───────────────────────────────────────────────────────
# Increase OUTPUT_GAIN_DB if the denoised output sounds too quiet.
# Decrease it if it clips (values > 1.0 are clamped).
OUTPUT_GAIN_DB     = 3.0
OUTPUT_GAIN_LINEAR = 10 ** (OUTPUT_GAIN_DB / 20.0)   # ≈ 1.413


class Denoiser:
    """
    Wraps DeepFilterNet 3 for real-time, stateful, frame-by-frame inference.

    The df_state object (DfState, backed by Rust) maintains all STFT/LSTM
    state between frames, giving temporal continuity across 10 ms chunks.
    """

    def __init__(self, config) -> None:
        self.config    = config
        self._model    = None
        self._df_state = None
        self._loaded   = False
        self._device   = "cpu"

    # ══════════════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════════════

    def load(self) -> None:
        """
        Load DeepFilterNet model weights. Safe to call once; idempotent.
        First call downloads ~30 MB weights to ~/.cache/DeepFilterNet/.
        """
        if self._loaded:
            return
        try:
            import torch
            from df.enhance import init_df

            logger.info("Loading DeepFilterNet 3…")
            model, df_state, _ = init_df(config_allow_defaults=True)
            model.eval()

            # Attempt GPU; gracefully fall back to CPU
            if torch.cuda.is_available():
                try:
                    model = model.cuda()
                    self._device = "cuda"
                    logger.info("DeepFilterNet running on CUDA (GPU).")
                except RuntimeError as exc:
                    logger.warning("CUDA init failed (%s) — falling back to CPU.", exc)
                    self._device = "cpu"
            else:
                logger.info("DeepFilterNet running on CPU.")

            self._model    = model
            self._df_state = df_state
            self._loaded   = True

            logger.info(
                "DeepFilterNet 3 ready | SR=%d Hz | hop=%d samples | device=%s",
                df_state.sr(),
                df_state.hop_size(),
                self._device,
            )

        except ImportError:
            logger.error("deepfilternet not installed. Run: uv pip install deepfilternet")
            raise
        except Exception as exc:
            logger.error("Model load failed: %s", exc, exc_info=True)
            raise

    def process_frame(self, frame: np.ndarray, strength: float = 1.0) -> np.ndarray:
        """
        Denoise one audio frame in-place of the pipeline.

        Args:
            frame:    float32 ndarray of shape (480,), values in [-1, 1].
            strength: 0.0 = bypass, 1.0 = maximum noise reduction.

        Returns:
            Denoised float32 ndarray, same shape as input.
        """
        if not self._loaded or self._model is None:
            return frame

        if strength < 0.005:
            return frame  # True bypass — no processing at all

        try:
            import torch
            from df.enhance import enhance as df_enhance

            # ── atten_lim_db mapping ───────────────────────────────────────────
            # atten_lim_db sets a LOWER BOUND on DeepFilterNet's spectral mask:
            #   low  atten_lim_db -> mask clamped high  -> little attenuation (quiet NR)
            #   high atten_lim_db -> mask clamped low   -> lots of attenuation (strong NR)
            #   None              -> no clamping at all -> full model-determined NR
            #
            # CORRECT mapping (strength 0→1 maps to NR none→max):
            if strength >= 0.99:
                atten_lim_db = None          # Full DeepFilterNet, no limiter
            else:
                atten_lim_db = strength * 100.0   # e.g. strength=0.5 -> 50 dB

            # Build input tensor on the correct device
            audio_t = torch.from_numpy(frame).unsqueeze(0)  # [1, 480]
            if self._device == "cuda":
                audio_t = audio_t.cuda()

            # inference_mode: faster than no_grad, zero autograd overhead
            with torch.inference_mode():
                enhanced_t = df_enhance(
                    self._model,
                    self._df_state,
                    audio_t,
                    atten_lim_db = atten_lim_db,
                    pad          = False,   # no zero-pad → no added latency
                )

            # Move back to CPU numpy
            result = enhanced_t.squeeze().cpu().numpy().astype(np.float32)

            # Explicitly delete tensors so Python's ref-count drops to zero
            # and the memory is returned to PyTorch's allocator promptly.
            del audio_t, enhanced_t

            # Apply post-processing gain and hard-clip to [-1, 1]
            np.multiply(result, OUTPUT_GAIN_LINEAR, out=result)
            np.clip(result, -1.0, 1.0, out=result)

            return result

        except Exception as exc:
            # Never crash the audio thread; silently pass through original frame
            logger.debug("Inference error (frame passed through): %s", exc)
            return frame

    def unload(self) -> None:
        """Release model and free memory."""
        self._model    = None
        self._df_state = None
        self._loaded   = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        import gc
        gc.collect()
        logger.info("Denoiser unloaded.")

    @property
    def is_loaded(self) -> bool:
        return self._loaded
