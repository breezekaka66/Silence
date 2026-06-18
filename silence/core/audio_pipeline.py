"""
Audio Pipeline — Real-time audio capture, denoising, and output.

Architecture:
  Microphone (sounddevice) 
      → Ring buffer 
      → Denoiser thread (DeepFilterNet ONNX) 
      → VU Meter calculation 
      → VB-Cable output (sounddevice)

Thread model:
  - Main thread: Qt GUI
  - Audio I/O thread: sounddevice callback (high priority, <1ms budget)
  - Inference thread: ONNX Runtime on DirectML (~8-15ms per 10ms frame)
"""
import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from silence.core.denoiser import Denoiser
from silence.core.vu_meter import VUMeter
from silence.utils.config import Config

logger = logging.getLogger(__name__)

# Audio constants
SAMPLE_RATE = 48000          # Hz — DeepFilterNet native rate
FRAME_DURATION_MS = 10       # ms per processing frame
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples
CHANNELS = 1                 # Mono
DTYPE = "float32"


class AudioPipeline:
    """
    Manages the complete real-time audio processing pipeline.
    
    Call start() to begin processing, stop() to halt.
    Emits callbacks for VU meter updates and latency readings.
    """

    def __init__(self, config: Config):
        self.config = config
        self._running = False
        self._lock = threading.Lock()

        # Ring buffer: audio callback → inference thread
        # Holds up to 10 frames (100ms) to absorb jitter
        self._input_buffer: deque[np.ndarray] = deque(maxlen=10)
        self._output_buffer: deque[np.ndarray] = deque(maxlen=10)
        self._buffer_event = threading.Event()

        # Audio streams
        self._input_stream: Optional[sd.InputStream] = None
        self._output_stream: Optional[sd.OutputStream] = None

        # Denoiser (lazy-loaded on first start)
        self._denoiser: Optional[Denoiser] = None

        # VU Meter
        self._vu_meter = VUMeter(sample_rate=SAMPLE_RATE)

        # Callbacks for GUI updates
        self.on_vu_update: Optional[Callable[[float, float], None]] = None  # (rms_db, peak_db)
        self.on_latency_update: Optional[Callable[[float], None]] = None    # latency_ms

        # Inference thread
        self._inference_thread: Optional[threading.Thread] = None

        # Current processing latency measurement
        self._last_latency_ms: float = 0.0

        # Silence passthrough (bypass denoising)
        self._bypass = False

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bypass(self) -> bool:
        return self._bypass

    @bypass.setter
    def bypass(self, value: bool):
        self._bypass = value
        logger.info(f"Bypass mode: {value}")

    def start(self) -> bool:
        """Start the audio pipeline. Returns True on success."""
        with self._lock:
            if self._running:
                logger.warning("Pipeline already running.")
                return True

            try:
                logger.info("Initialising Denoiser...")
                if self._denoiser is None:
                    self._denoiser = Denoiser(self.config)
                    self._denoiser.load()

                logger.info("Opening audio streams...")
                self._open_streams()

                self._running = True

                # Start inference thread
                self._inference_thread = threading.Thread(
                    target=self._inference_loop,
                    name="SilenceInference",
                    daemon=True,
                )
                self._inference_thread.start()

                logger.info(
                    f"Pipeline started. Input: '{self.config.input_device_name}', "
                    f"Output: '{self.config.output_device_name}'"
                )
                return True

            except Exception as e:
                logger.error(f"Failed to start pipeline: {e}", exc_info=True)
                self._cleanup_streams()
                return False

    def stop(self):
        """Stop the audio pipeline gracefully."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._buffer_event.set()  # Wake up inference thread to exit

        if self._inference_thread:
            self._inference_thread.join(timeout=2.0)

        self._cleanup_streams()
        logger.info("Pipeline stopped.")

    def get_devices(self) -> dict:
        """Return available input and output audio devices."""
        devices = sd.query_devices()
        inputs = []
        outputs = []
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                inputs.append({"index": i, "name": dev["name"]})
            if dev["max_output_channels"] > 0:
                outputs.append({"index": i, "name": dev["name"]})
        return {"inputs": inputs, "outputs": outputs}

    # -------------------------------------------------------------------------
    # Internal: Audio stream callbacks
    # -------------------------------------------------------------------------

    def _input_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ):
        """
        Called by sounddevice for each input frame.
        MUST be fast — no blocking, no heavy computation.
        """
        if status:
            logger.debug(f"Input stream status: {status}")

        # Copy data to avoid buffer reuse issues
        frame = indata[:, 0].copy()  # mono

        # VU meter update (fast, in-callback)
        rms_db, peak_db = self._vu_meter.process(frame)
        if self.on_vu_update:
            self.on_vu_update(rms_db, peak_db)

        # Push to inference buffer
        self._input_buffer.append(frame)
        self._buffer_event.set()

    def _output_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ):
        """
        Called by sounddevice when output needs data.
        MUST be fast — pulls from output ring buffer.
        """
        if status:
            logger.debug(f"Output stream status: {status}")

        if self._output_buffer:
            frame = self._output_buffer.popleft()
            # Ensure frame length matches requested frames
            if len(frame) == frames:
                outdata[:, 0] = frame
            else:
                outdata[:, 0] = np.resize(frame, frames)
        else:
            # Buffer underrun: output silence
            outdata[:] = 0

    # -------------------------------------------------------------------------
    # Internal: Inference loop (runs in dedicated thread)
    # -------------------------------------------------------------------------

    def _inference_loop(self):
        """
        Dedicated thread: pulls frames from input buffer,
        runs DeepFilterNet inference, pushes to output buffer.
        """
        logger.info("Inference thread started.")

        while self._running:
            # Wait for data
            self._buffer_event.wait(timeout=0.1)
            self._buffer_event.clear()

            while self._input_buffer and self._running:
                frame = self._input_buffer.popleft()

                t_start = time.perf_counter()

                if self._bypass or self._denoiser is None:
                    denoised = frame
                else:
                    strength = self.config.denoise_strength / 100.0  # 0.0–1.0
                    denoised = self._denoiser.process_frame(frame, strength)

                t_end = time.perf_counter()
                latency_ms = (t_end - t_start) * 1000
                self._last_latency_ms = latency_ms

                if self.on_latency_update:
                    self.on_latency_update(latency_ms)

                self._output_buffer.append(denoised)

        logger.info("Inference thread exited.")

    # -------------------------------------------------------------------------
    # Internal: Stream management
    # -------------------------------------------------------------------------

    def _open_streams(self):
        """Open sounddevice input and output streams."""
        input_device = self.config.input_device_index
        output_device = self.config.output_device_index

        self._input_stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            device=input_device,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._input_callback,
            latency="low",
        )

        self._output_stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            device=output_device,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._output_callback,
            latency="low",
        )

        self._input_stream.start()
        self._output_stream.start()

    def _cleanup_streams(self):
        """Close and clean up audio streams."""
        for stream in (self._input_stream, self._output_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as e:
                    logger.debug(f"Stream cleanup error: {e}")
        self._input_stream = None
        self._output_stream = None
