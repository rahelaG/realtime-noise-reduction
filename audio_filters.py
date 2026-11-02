import numpy as np
from scipy import signal


class AudioFilter:
    """Apply a stateful filter to consecutive mono audio blocks."""

    def __init__(
        self,
        filter_type,
        sample_rate,
        cutoff=300.0,
        low=800.0,
        high=1200.0,
        frequency=1000.0,
        quality=30.0,
        order=4,
    ):
        if sample_rate <= 0:
            raise ValueError("Sample rate must be positive.")

        if order < 1:
            raise ValueError("Filter order must be at least 1.")

        nyquist = sample_rate / 2
        self.sos = None
        self.state = None

        if filter_type == "none":
            return

        if filter_type in ("highpass", "lowpass"):
            if not 0 < cutoff < nyquist:
                raise ValueError(
                    f"Cutoff must be between 0 and {nyquist:g} Hz."
                )

            self.sos = signal.butter(
                order,
                cutoff,
                btype=filter_type,
                fs=sample_rate,
                output="sos",
            )

        elif filter_type == "bandstop":
            if not 0 < low < high < nyquist:
                raise ValueError(
                    "Band limits must satisfy "
                    f"0 < low < high < {nyquist:g} Hz."
                )

            self.sos = signal.butter(
                order,
                [low, high],
                btype="bandstop",
                fs=sample_rate,
                output="sos",
            )

        elif filter_type == "notch":
            if not 0 < frequency < nyquist:
                raise ValueError(
                    f"Notch frequency must be between 0 and {nyquist:g} Hz."
                )

            if quality <= 0:
                raise ValueError("Quality factor must be positive.")

            b, a = signal.iirnotch(
                frequency,
                quality,
                fs=sample_rate,
            )
            self.sos = signal.tf2sos(b, a)

        else:
            raise ValueError(f"Unknown filter type: {filter_type}")

        # These values are updated after every processed block.
        self.state = np.zeros((self.sos.shape[0], 2))

    def process(self, samples):
        """Process one block while preserving the filter state."""
        if self.sos is None:
            return samples

        filtered, self.state = signal.sosfilt(
            self.sos,
            samples,
            zi=self.state,
        )
        return filtered

    def reset(self):
        """Reset the filter before processing an independent signal."""
        if self.state is not None:
            self.state.fill(0)