import argparse
import time

import sounddevice as sd

from audio_filters import AudioFilter


def main():
    parser = argparse.ArgumentParser(
        description="Monitor and filter microphone audio in real time."
    )

    parser.add_argument("--input-device", type=int, required=True)
    parser.add_argument("--output-device", type=int, required=True)
    parser.add_argument("--sample-rate", type=int, default=48000)

    parser.add_argument(
        "--filter",
        choices=["none", "highpass", "lowpass", "bandstop", "notch"],
        default="none",
    )
    parser.add_argument("--cutoff", type=float, default=300.0)
    parser.add_argument("--low", type=float, default=800.0)
    parser.add_argument("--high", type=float, default=1200.0)
    parser.add_argument("--frequency", type=float, default=1000.0)
    parser.add_argument("--quality", type=float, default=30.0)
    parser.add_argument("--order", type=int, default=4)
    parser.add_argument("--gain", type=float, default=0.5)

    args = parser.parse_args()

    if not 0 <= args.gain <= 1:
        parser.error("Gain must be between 0 and 1.")

    try:
        audio_filter = AudioFilter(
            filter_type=args.filter,
            sample_rate=args.sample_rate,
            cutoff=args.cutoff,
            low=args.low,
            high=args.high,
            frequency=args.frequency,
            quality=args.quality,
            order=args.order,
        )
    except ValueError as error:
        parser.error(str(error))

    status_count = 0
    callback_error = None

    def audio_callback(indata, outdata, frames, time_info, status):
        nonlocal status_count, callback_error

        # Start with silence so the entire output buffer is initialized.
        outdata.fill(0)

        if status:
            status_count += 1

        try:
            microphone_audio = indata[:, 0]
            processed_audio = audio_filter.process(microphone_audio)

            outdata[:, 0] = processed_audio * args.gain
            outdata[:, 1] = outdata[:, 0]

        except Exception as error:
            callback_error = str(error)
            raise sd.CallbackAbort

    try:
        sd.check_input_settings(
            device=args.input_device,
            channels=1,
            dtype="float32",
            samplerate=args.sample_rate,
        )

        sd.check_output_settings(
            device=args.output_device,
            channels=2,
            dtype="float32",
            samplerate=args.sample_rate,
        )

        input_info = sd.query_devices(args.input_device)
        output_info = sd.query_devices(args.output_device)

        print(f"Input: {input_info['name']}")
        print(f"Output: {output_info['name']}")
        print(f"Sample rate: {args.sample_rate} Hz")
        print(f"Filter: {args.filter}")

        if args.filter in ("highpass", "lowpass"):
            print(f"Cutoff: {args.cutoff:g} Hz")
        elif args.filter == "bandstop":
            print(f"Stop band: {args.low:g}-{args.high:g} Hz")
        elif args.filter == "notch":
            print(f"Notch frequency: {args.frequency:g} Hz")
            print(f"Quality factor: {args.quality:g}")

        with sd.Stream(
            device=(args.input_device, args.output_device),
            samplerate=args.sample_rate,
            channels=(1, 2),
            dtype="float32",
            blocksize=0,
            latency="high",
            callback=audio_callback,
        ) as stream:
            print("Live monitoring started. Press Ctrl+C to stop.")

            while stream.active:
                time.sleep(0.1)

            if callback_error is not None:
                print(f"Audio processing error: {callback_error}")
            else:
                print("Audio stream stopped.")

    except KeyboardInterrupt:
        print("\nLive monitoring stopped.")

    except (sd.PortAudioError, ValueError) as error:
        print(f"\nAudio device error: {error}")

    finally:
        print(
            "Audio callbacks reporting a status warning: "
            f"{status_count}"
        )


if __name__ == "__main__":
    main()