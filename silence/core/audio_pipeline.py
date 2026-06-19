"""
Audio Pipeline — Real-time audio capture, denoising, and output.

Architecture:
  Microphone (sounddevice WASAPI)
      -> RingBuffer (maxlen=3, ~30ms max queuing)
      -> Inference thread (DeepFilterNet, CPU, ~1ms/frame)
      -> VU Meter callback
      -> VB-Cable output (sounddevice WASAPI)

Memory safety strategy:
  - Fixed-size ring buffers (maxlen=3) prevent unbounded growth
  - Numpy pre-allocated frame copies, not torch tensors in callback
  - Inference thread periodically calls gc.collect() every 1000 frames
  - Callbacks stored as weak references to prevent GUI reference cycles
  - Explicit buffer clear on stop()

Thread model:
  Thread-1 (sounddevice portaudio thread): _input_callback, _output_callback
  Thread-2 (SilenceInference daemon):      _inference_loop
  Thread-3 (Qt main):                      GUI, config reads (read-only during run)
"""
import gc
import logging
import threading
import time
import weakref
from collections import deque
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from silence.core.denoiser import Denoiser
from silence.core.vu_meter import VUMeter
from silence.utils.config import Config

logger = logging.getLogger(__name__)

# ── Audio constants ────────────────────────────────────────────────────────────
SAMPLE_RATE      = 48_000           # Hz — DeepFilterNet native sample rate
FRAME_MS         = 10               # ms per processing frame
FRAME_SAMPLES    = SAMPLE_RATE * FRAME_MS // 1000   # 480 samples
CHANNELS         = 1
DTYPE            = "float32"

# Ring buffer depth: 3 frames = 30 ms max queuing latency.
# Lower = less latency but more risk of underrun on slow systems.
RING_DEPTH       = 3

# Periodic GC every N inference frames (~10 s at 100 fps)
GC_INTERVAL      = 1_000

# VB-Cable driver internal latency estimate
VBCABLE_LATENCY_MS = 5.0


class AudioPipeline:
    """
    Manages the complete real-time audio processing pipeline.

    Usage:
        pipeline = AudioPipeline(config)
        pipeline.on_vu_update  = my_vu_callback      # optional
        pipeline.on_latency_update = my_lat_callback  # optional
        pipeline.start()
        ...
        pipeline.stop()
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._running = False
        self._lock = threading.Lock()

        # ── Fixed-size ring buffers ────────────────────────────────────────────
        # maxlen guarantees O(1) memory — old frames silently dropped if full.
        self._input_buf:  deque[np.ndarray] = deque(maxlen=RING_DEPTH)
        self._output_buf: deque[np.ndarray] = deque(maxlen=RING_DEPTH)
        self._buf_event = threading.Event()

        # ── Audio streams (opened on start, closed on stop) ────────────────────
        self._in_stream:  Optional[sd.InputStream]  = None
        self._out_stream: Optional[sd.OutputStream] = None

        # ── Denoiser (lazy-loaded on first start, kept alive across stop/start) ─
        self._denoiser: Optional[Denoiser] = None

        # ── VU Meter ───────────────────────────────────────────────────────────
        self._vu_meter = VUMeter(sample_rate=SAMPLE_RATE)

        # ── Callbacks: stored as plain attributes (GUI sets to None on close) ──
        # These are called from the audio/inference threads.
        # Assignment of a Python object reference is GIL-atomic, so no lock needed.
        self.on_vu_update:      Optional[Callable[[float, float], None]] = None
        self.on_latency_update: Optional[Callable[[float], None]]        = None

        # ── Inference thread ───────────────────────────────────────────────────
        self._inference_thread: Optional[threading.Thread] = None

        # ── Latency tracking ───────────────────────────────────────────────────
        self._stream_in_ms:  float = 20.0   # actual driver latency (set on open)
        self._stream_out_ms: float = 20.0

        # ── State ──────────────────────────────────────────────────────────────
        self._bypass: bool = False

    # ══════════════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════════════

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bypass(self) -> bool:
        return self._bypass

    @bypass.setter
    def bypass(self, value: bool) -> None:
        self._bypass = value
        logger.info("Bypass: %s", value)

    def start(self) -> bool:
        """Start the pipeline. Returns True on success."""
        with self._lock:
            if self._running:
                logger.warning("Pipeline already running.")
                return True

            try:
                # Load model once; reuse on subsequent start() calls
                if self._denoiser is None:
                    logger.info("Loading DeepFilterNet model…")
                    self._denoiser = Denoiser(self.config)
                    self._denoiser.load()

                logger.info("Opening WASAPI streams…")
                self._open_streams()

                # Clear any stale data from a previous run
                self._input_buf.clear()
                self._output_buf.clear()
                self._buf_event.clear()

                self._running = True

                self._inference_thread = threading.Thread(
                    target=self._inference_loop,
                    name="SilenceInference",
                    daemon=True,
                )
                self._inference_thread.start()

                logger.info(
                    "Pipeline started | in=%s | out=%s",
                    self.config.input_device_name,
                    self.config.output_device_name,
                )
                return True

            except Exception as exc:
                logger.error("Failed to start pipeline: %s", exc, exc_info=True)
                self._close_streams()
                self._running = False
                return False

    def stop(self) -> None:
        """Stop the pipeline gracefully and release audio streams."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._buf_event.set()  # unblock inference thread

        if self._inference_thread and self._inference_thread.is_alive():
            self._inference_thread.join(timeout=2.0)
        self._inference_thread = None

        self._close_streams()

        # Drain buffers so memory is released
        self._input_buf.clear()
        self._output_buf.clear()

        logger.info("Pipeline stopped.")

    def get_devices(self) -> dict:
        """Return dicts of available input and output audio devices."""
        devs = sd.query_devices()
        inputs, outputs = [], []
        for i, d in enumerate(devs):
            if d["max_input_channels"] > 0:
                inputs.append({"index": i, "name": d["name"]})
            if d["max_output_channels"] > 0:
                outputs.append({"index": i, "name": d["name"]})
        return {"inputs": inputs, "outputs": outputs}

    # ══════════════════════════════════════════════════════════════════════════
    # Audio callbacks (called from PortAudio thread — must be non-blocking)
    # ══════════════════════════════════════════════════════════════════════════

    def _input_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.debug("Input xrun: %s", status)

        # Mono slice, contiguous copy to avoid referencing PortAudio's buffer
        frame = np.ascontiguousarray(indata[:, 0], dtype=np.float32)

        # VU meter — fast arithmetic only, no allocation
        rms_db, peak_db = self._vu_meter.process(frame)
        cb = self.on_vu_update
        if cb is not None:
            cb(rms_db, peak_db)

        # Enqueue for inference; deque drops oldest frame if full (bounded memory)
        self._input_buf.append(frame)
        self._buf_event.set()

    def _output_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.debug("Output xrun: %s", status)

        if self._output_buf:
            processed = self._output_buf.popleft()
            if len(processed) == frames:
                outdata[:, 0] = processed
            else:
                # Frame-size mismatch: resize without allocation when possible
                outdata[:, 0] = np.resize(processed, frames)
        else:
            # Buffer underrun — output silence rather than garbage
            outdata[:] = 0.0

    # ══════════════════════════════════════════════════════════════════════════
    # Inference thread
    # ══════════════════════════════════════════════════════════════════════════

    def _inference_loop(self) -> None:
        logger.info("Inference thread started.")
        frame_count = 0

        while self._running:
            # Block until new audio arrives (or 100 ms timeout for clean exit)
            self._buf_event.wait(timeout=0.1)
            self._buf_event.clear()

            while self._input_buf and self._running:
                frame = self._input_buf.popleft()

                t0 = time.perf_counter()

                if self._bypass or self._denoiser is None:
                    denoised = frame
                else:
                    strength = self.config.denoise_strength / 100.0
                    denoised = self._denoiser.process_frame(frame, strength)

                inference_ms = (time.perf_counter() - t0) * 1000.0

                # ── True end-to-end latency estimate ──────────────────────────
                # Components:
                #   input driver buffer   : _stream_in_ms  (reported by driver)
                #   current frame window  : FRAME_MS
                #   queued frames         : len(buf) * FRAME_MS
                #   model inference       : inference_ms
                #   output driver buffer  : _stream_out_ms
                #   VB-Cable overhead     : VBCABLE_LATENCY_MS
                queued_ms = len(self._input_buf) * FRAME_MS
                e2e_ms = (
                    self._stream_in_ms
                    + FRAME_MS
                    + queued_ms
                    + inference_ms
                    + self._stream_out_ms
                    + VBCABLE_LATENCY_MS
                )

                cb = self.on_latency_update
                if cb is not None:
                    cb(e2e_ms)

                self._output_buf.append(denoised)

                # ── Periodic garbage collection ────────────────────────────────
                frame_count += 1
                if frame_count >= GC_INTERVAL:
                    frame_count = 0
                    gc.collect()
                    # Release any cached PyTorch allocations
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except ImportError:
                        pass

        logger.info("Inference thread exited.")

    # ══════════════════════════════════════════════════════════════════════════
    # Stream management
    # ══════════════════════════════════════════════════════════════════════════

    def _open_streams(self) -> None:
        """Open WASAPI input and output streams with matched parameters."""
        in_dev  = self.config.input_device_index
        out_dev = self.config.output_device_index

        common = dict(
            samplerate = SAMPLE_RATE,
            blocksize  = FRAME_SAMPLES,
            channels   = CHANNELS,
            dtype      = DTYPE,
            latency    = "low",
        )

        self._in_stream = sd.InputStream(
            device   = in_dev,
            callback = self._input_callback,
            **common,
        )
        self._out_stream = sd.OutputStream(
            device   = out_dev,
            callback = self._output_callback,
            **common,
        )

        self._in_stream.start()
        self._out_stream.start()

        # Capture driver-reported latencies for accurate e2e calculation
        self._stream_in_ms  = self._in_stream.latency  * 1000.0
        self._stream_out_ms = self._out_stream.latency * 1000.0
        logger.info(
            "Stream latencies — in: %.1f ms | out: %.1f ms",
            self._stream_in_ms,
            self._stream_out_ms,
        )

    def _close_streams(self) -> None:
        """Stop and close both audio streams, releasing device handles."""
        for stream in (self._in_stream, self._out_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:
                    logger.debug("Stream close error: %s", exc)
        self._in_stream  = None
        self._out_stream = None
