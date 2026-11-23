# Noise Reduction Studio

A Python desktop application that reduces selected frequency ranges in microphone audio in real time. Built as a signal-processing course project by **Rahela Gruici**.

It combines live filtering, signal plots, steady-tone calibration, repeatable WAV experiments, and paired recording/export. Frequency filtering can also affect speech when speech and noise overlap.

## Features

- Microphone and stereo output selection, device refresh, and Start/Stop controls.
- Original/Filtered monitoring, Listen switch, and playback volume.
- Stateful high-pass, low-pass, band-stop, and notch filters implemented with SciPy.
- Presets, validated custom settings, and a short crossfade when changing filters.
- Auto calibration for one steady tone between 40 and 3000 Hz.
- Live waveform, frequency spectrum, and filter response plots.
- Input peak, callback processing time, and audio warning counter.
- Test Lab with clean WAV loading, generated noise, independent filter selection, playback comparison, and noise attenuation measurement.
- Simultaneous original/filtered recording, up to 60 seconds, with paired WAV export.

## Requirements

- Python 3.12 and Git for the commands below.
- Windows is the primary development platform; the interface prefers WASAPI devices.
- A microphone and a stereo output supporting 48 kHz.
- Headphones for live monitoring, to avoid speaker-to-microphone feedback.

Bluetooth headphones can add noticeable delay. This project measures callback processing time, not total microphone-to-headphone latency. Linux additionally requires the system PortAudio library; the Windows setup is the supported demonstration workflow.

## Install and run on Windows

Open PowerShell in the folder where you want to download the project:

```powershell
git clone https://github.com/rahelaG/realtime-noise-reduction.git
cd realtime-noise-reduction
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe app.py
```

The lock file contains the exact development versions. `requirements.txt` lists the direct dependencies and can be used for a separately resolved environment. Activating the virtual environment is optional because the commands explicitly use its interpreter.

## Live Studio

1. Choose the microphone and headphones. Use Refresh Devices after connecting a device.
2. Press Start. The default applied filter is a low-pass at 1000 Hz.
3. Select a preset and click Apply Preset, or configure Custom and click Apply Changes.
4. Enable Listen and choose Original or Filtered to compare at the same volume.
5. Press Stop to close the audio stream.

The Listen switch only controls playback. Processing, plots, calibration and recording can continue with Listen off.

### Filters and modes

| Filter | Effect | Typical experiment |
| --- | --- | --- |
| High-pass | Attenuates frequencies below a cutoff | Low-frequency rumble |
| Low-pass | Attenuates frequencies above a cutoff | High-frequency hiss |
| Band-stop | Attenuates a selected interval | Noise concentrated in a band |
| Notch | Attenuates a narrow region around a center frequency | Steady hum or whistle |

**Presets in Live Studio** are deliberately strong voice demonstrations: Low Voice Notch Demo, Muffled Voice Demo, Thin Voice Demo and Mid Voice Notch Demo. They show the effect of filtering and are not universal noise-removal settings. **Custom** exposes frequency controls and the notch quality factor Q; higher Q produces a narrower notch. Butterworth filters use order 4.

**Auto** analyzes the background during calibration:

1. Start the microphone and leave the unwanted steady tone present.
2. Stay quiet and click Calibrate. Listening can remain off.
3. The interface waits two seconds and analyzes the latest second of original audio.
4. If a stable tone is detected, a notch with Q=20 is applied. Otherwise no filter is applied.
5. Recalibrate if the tone changes.

Auto is a calibration feature, not continuous adaptive cancellation. It does not identify arbitrary noises such as typing or competing speech.

### Plots and metrics

- **Waveform:** last 50 ms of original and filtered samples.
- **Spectrum:** Hann-windowed FFT of the last second; blue is original and green is filtered. Curves may overlap when the filter changes little in the signal.
- **Filter Response:** the requested filter's gain by frequency. Only one curve is needed here.
- **Input peak:** peak absolute microphone sample in the latest callback.
- **Processing:** time spent in the latest audio callback, including filtering and bookkeeping. It is not an end-to-end latency measurement or a worst-case benchmark.
- **Audio warnings:** callbacks reporting a PortAudio status flag. This is not an exact count of lost samples.

Plots can be panned and zoomed. A short startup wait is needed to collect a full second for the spectrum.

## Test Lab

Load a WAV of 1–60 seconds at 8 kHz or higher. The application converts it to mono, resamples to 48 kHz if needed, and scales its peak to 0.7. Use an initially clean voice recording for an interpretable comparison.

Choose the added noise independently of the filter:

| Added noise | Suggested setting |
| --- | --- |
| Single tone at 1000 Hz | Custom Notch: 1000 Hz, Q=20; or Auto |
| Low-frequency rumble, approximately 40–180 Hz | Preset: Reduce low rumble |
| High-frequency hiss, approximately 6–12 kHz | Preset: Reduce high hiss |
| Band-limited noise at 800–1200 Hz | Preset: Reduce mid-band noise |

Noise level is RMS as a percentage of full scale. Generated random noise uses a fixed seed so repeated settings reproduce the same experiment. These bands have filter slopes, not perfectly sharp boundaries.

Press Run Test after changing settings. Compare Play Clean, Play Noisy and Play Filtered. Stop live microphone audio before test playback. The selected output device comes from Live Studio. Playback uses a shared gain across all three tracks, preserving relative levels.

Test Lab Auto analyzes one second of generated noise alone, simulating a noise-only calibration. It does not estimate noise from the mixed voice recording. Broadband noise may produce no stable-tone detection.

**Added noise attenuation** is calculated by separately filtering the known generated noise:

```text
attenuation_dB = 20 * log10(RMS(noise) / RMS(filtered_noise))
```

The measurement includes filter startup transients. It describes noise reduction in this experiment, not speech quality or general denoising accuracy. A mismatched filter can yield approximately 0 dB. Always listen for changes to the voice as well.

## Recording and export

1. Start live audio and apply the intended filter before recording.
2. Press Record, speak or reproduce a background tone, then press Stop Recording.
3. Press Export WAV and choose a parent folder.

A new uniquely named subfolder contains:

- `original.wav`: microphone input, including background noise.
- `filtered.wav`: corresponding filtered samples.
- `details.txt`: sample rate, sample count, duration, shared export gain and audio warning count.

Both files are mono 16-bit PCM with identical sample counts. Listen, monitoring source and volume do not affect recording. If required to prevent clipping, both tracks are scaled down by the same factor. Filter changes during the take appear in the filtered track.

Recording stops at 60 seconds or when live audio stops. Recordings remain in memory until export and are not recovered after a crash. The interface asks before replacing or closing an unexported take. Device overruns may cause gaps; export does not reconstruct missing audio.

Keep local recordings in `recordings/` (ignored by Git). Only publish demonstration recordings you intend to share.

## Verification

Run the automated checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py audio_engine.py audio_filters.py audio_plots.py audio_recording.py auto_noise.py test_lab.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests check filter behavior and block continuity, tone detection, controlled experiments, WAV loading, paired recording/export and callback recording independent of Listen. They do not validate a physical microphone, Bluetooth behavior or audible playback.

See [the manual checklist](docs/VALIDATION.md) for the Windows checks and [the demo guide](docs/DEMO_GUIDE_RO.md) for a natural presentation and recording plan. The validation report distinguishes automated results from checks still requiring the user's hardware.

## Project structure

| File | Purpose |
| --- | --- |
| `app.py` | Desktop interface, controls, calibration and recording actions |
| `audio_engine.py` | Audio stream, monitoring, filter transitions and callback metrics |
| `audio_filters.py` | Stateful SciPy filter design and processing |
| `auto_noise.py` | Detection of one persistent narrow tone |
| `audio_plots.py` | Waveform, spectrum and filter response |
| `test_lab.py` | Controlled WAV/noise experiments and comparison playback |
| `audio_recording.py` | Paired in-memory capture and WAV export |
| `live_audio.py` | Earlier command-line microphone monitoring utility |
| `styles.qss` | Interface styling |

## Troubleshooting

- **No microphone signal:** verify Windows microphone permissions, the selected input and its level. Check whether the spectrum responds to speech.
- **Auto cannot detect a phone tone:** calibrate without speaking, check the microphone level, and check whether device noise suppression is removing the tone. Retry with a moderate-volume 1000 Hz tone. Test Lab provides a repeatable alternative.
- **No playback:** enable Listen in Live Studio, select the correct source/output and check volume. In Test Lab, stop the live stream first.
- **Unsupported audio settings:** choose another input/output supporting mono input, stereo output and 48 kHz. Bluetooth hands-free modes may have different capabilities.
- **Filtered resembles Noisy:** match the filter to the noise frequency range, press Apply/Run Test as appropriate, and compare at the same volume.
- **Only one spectrum color is visible:** overlapping curves can hide each other. Use a controlled tone in the filter's attenuated region.
- **Voice sounds unnatural:** aggressive settings remove parts of speech as well as noise; choose a narrower notch or less aggressive cutoffs.

## Limits

This is frequency-selective noise reduction, not active acoustic cancellation or a general speech-enhancement model. Noise overlapping speech cannot be removed selectively by these filters. Python, PortAudio, the operating system and hardware determine practical timing; the application does not guarantee hard real-time deadlines.

