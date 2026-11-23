import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from audio_filters import AudioFilter
from audio_recording import AudioRecording
from auto_noise import detect_steady_tone

# Numerical tests do not require a physical audio device or PortAudio.
try:
    import sounddevice
except OSError:
    sounddevice = types.ModuleType("sounddevice")
    sounddevice.PortAudioError = type("PortAudioError", (Exception,), {})
    sys.modules["sounddevice"] = sounddevice

from audio_engine import AudioEngine
from test_lab import read_voice, run_controlled_test

FS = 48000


class FilterChecks(unittest.TestCase):
    def test_block_continuity(self):
        samples = np.random.default_rng(1).normal(size=5000)
        settings = dict(filter_type="lowpass", sample_rate=FS, cutoff=3500)
        whole = AudioFilter(**settings).process(samples)
        f = AudioFilter(**settings)
        split = np.concatenate([f.process(samples[:711]), f.process(samples[711:2048]), f.process(samples[2048:])])
        np.testing.assert_allclose(split, whole, atol=1e-12)
        f.reset()
        np.testing.assert_allclose(f.process(samples), whole, atol=1e-12)

    def test_invalid_band(self):
        with self.assertRaises(ValueError):
            AudioFilter("bandstop", FS, low=1200, high=800)

    def test_auto_tone_and_silence(self):
        t = np.arange(FS) / FS
        self.assertAlmostEqual(detect_steady_tone(.05 * np.sin(2*np.pi*1000*t), FS), 1000, delta=1)
        self.assertIsNone(detect_steady_tone(np.zeros(FS), FS))

    def test_controlled_scenarios(self):
        t = np.arange(3*FS) / FS
        voice = .3 * np.sin(2*np.pi*440*t)
        for noise, kind, settings in [
            ("rumble", "highpass", {"cutoff":300}),
            ("hiss", "lowpass", {"cutoff":3500}),
            ("band", "bandstop", {"low":800,"high":1200}),
            ("tone", "notch", {"frequency":1000,"quality":20}),
        ]:
            with self.subTest(noise=noise):
                text, tracks = run_controlled_test(voice,FS,noise,{"level":10},"custom",kind,settings)
                attenuation = float(text.split("Added noise attenuation: ")[1].split()[0])
                self.assertGreater(attenuation,5)
                for track in tracks.values():
                    self.assertEqual(len(track),len(voice))
                    self.assertTrue(np.isfinite(track).all())

    def test_auto_lab_and_mismatched_filter(self):
        voice = np.zeros(FS)
        text,_ = run_controlled_test(voice,FS,"tone",{"level":10},"auto","none",{})
        self.assertIn("Detected tone: 1,000.0",text)
        text,_ = run_controlled_test(voice,FS,"hiss",{"level":10},"custom","highpass",{"cutoff":300})
        attenuation=float(text.split("Added noise attenuation: ")[1].split()[0])
        self.assertLess(abs(attenuation),.5)

    def test_wav_conversion_and_silence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"voice.wav"
            t=np.arange(16000)/16000
            x=(12000*np.sin(2*np.pi*440*t)).astype(np.int16)
            wavfile.write(p,16000,np.column_stack((x,x)))
            rate,samples=read_voice(p)
            self.assertEqual(rate,FS)
            self.assertEqual(samples.shape,(FS,))
            self.assertAlmostEqual(float(np.max(np.abs(samples))),.7)
            wavfile.write(p,16000,np.zeros(16000,dtype=np.int16))
            with self.assertRaises(ValueError):read_voice(p)


class RecordingChecks(unittest.TestCase):
    def test_paired_export_limit_gain_and_warnings(self):
        r=AudioRecording(8000,max_seconds=1)
        r.start()
        x=np.linspace(-2,2,12000)
        r.append(x,x*.25,True)
        self.assertEqual(r.status,(False,8000,1))
        with tempfile.TemporaryDirectory() as d:
            folder,gain=r.export(d)
            fs,a=wavfile.read(folder/"original.wav")
            fs2,b=wavfile.read(folder/"filtered.wav")
            self.assertEqual((fs,fs2,len(a),len(b)),(8000,8000,8000,8000))
            self.assertEqual(a.dtype,np.int16)
            self.assertLess(gain,1)
            np.testing.assert_allclose(b,a*.25,atol=1)
            other,_=r.export(d)
            self.assertNotEqual(folder,other)

    def test_stopped_recording_and_empty_export(self):
        r=AudioRecording(FS)
        with self.assertRaises(ValueError):r.snapshot()
        r.start()
        with self.assertRaises(RuntimeError):r.snapshot()
        r.append(np.ones(100),np.zeros(100))
        r.stop()
        r.append(np.zeros(100),np.ones(100))
        samples,_=r.snapshot()
        self.assertEqual(samples.shape,(100,2))
        np.testing.assert_equal(samples[:,0],1)
        np.testing.assert_equal(samples[:,1],0)

    def test_callback_records_with_listen_off(self):
        engine=AudioEngine()
        engine.set_filter("none")
        engine._active_filter=engine._requested_filter
        engine.set_monitoring(False,False,.01)
        engine.recording.start()
        x=np.full((1024,1),.2,dtype=np.float32)
        output=np.empty((1024,2),dtype=np.float32)
        engine._process_audio(x,output,len(x),None,False)
        engine.stop()
        samples,_=engine.recording.snapshot()
        np.testing.assert_equal(output,0)
        np.testing.assert_allclose(samples[:,0],x[:,0])
        np.testing.assert_allclose(samples[:,1],x[:,0])


if __name__ == "__main__":
    unittest.main()
