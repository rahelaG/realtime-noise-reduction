import argparse
import time

import sounddevice as sd


def main():
    parser = argparse.ArgumentParser(
        description="Listen to microphone audio through headphones."
    )
    parser.add_argument("--input-device", type=int, required=True)
    parser.add_argument("--output-device", type=int, required=True)
    parser.add_argument("--sample-rate", type=int, default=48000)
    args = parser.parse_args()

    # Count audio callbacks that report warnings.
    status_count = 0

    def audio_callback(indata, outdata, frames, time_info, status):
        nonlocal status_count

        if status:
            status_count += 1

        # Send the microphone signal to both headphone channels.
        outdata[:, 0] = indata[:, 0] * 0.5
        outdata[:, 1] = indata[:, 0] * 0.5

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
        print("Live monitoring started. Press Ctrl+C to stop.")

        with sd.Stream(
            device=(args.input_device, args.output_device),
            samplerate=args.sample_rate,
            channels=(1, 2),
            dtype="float32",
            blocksize=0,
            latency="high",
            callback=audio_callback,
        ):
            while True:
                time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nLive monitoring stopped.")

    except sd.PortAudioError as error:
        print(f"\nAudio device error: {error}")

    finally:
        print(
            "Audio callbacks reporting a status warning: "
            f"{status_count}"
        )


if __name__ == "__main__":
    main()