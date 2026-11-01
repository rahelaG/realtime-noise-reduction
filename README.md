# Real-Time Noise Reduction

A Python application for reducing background noise in real time
by filtering selected frequency ranges with SciPy.

## Goal

Capture audio from a microphone, process it continuously, and
compare the original and filtered signals.

## Planned Features

- Real-time audio capture and filtering.
- High-pass, low-pass, band-stop, and notch filters.
- Desktop interface for selecting audio devices and adjusting filters.
- Live waveform, frequency spectrum, and filter response plots.
- Controlled testing with known noise signals.
- Export of original and filtered audio recordings.
- Evaluation of noise attenuation and processing time.

## Requirements

- Python 3.12
- A microphone
- Headphones recommended for live audio monitoring

## Setup

Create a virtual environment:

```powershell
py -3.12 -m venv .venv
Install the exact dependency versions used during development:
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt