#!/usr/bin/env python3
"""AUDIO layer -- procedural arcade SFX, presentation-only.
Every sound is synthesized with the Python standard library
(wave, io, struct, math, random) into in-memory WAV data and loaded into
pygame.mixer.Sound. No external .wav files. This is NOT realistic boxing
audio -- it is simple, clear arcade feedback.
Hard guarantees:
* Importing this module never imports pygame and never raises.
* If the mixer cannot initialize (headless box / no audio device),
SfxBank silently degrades to no-ops. The simulation never notices.
* Waveform randomness uses its own random.Random instance and can never
touch the simulation RNG (match.rng).
"""
import io
import math
import random
import struct
import wave

SAMPLE_RATE = 22050

# Waveform-only RNG. Deliberately separate from the simulation RNG.
_wrng = random.Random(0xB100)

def _noise():
    return _wrng.uniform(-1.0, 1.0)

def _whoosh(dur=0.12, vol=0.5):
    """Low-passed noise with a swell envelope: a swing through air."""
    n = max(1, int(SAMPLE_RATE * dur))
    out = []
    lp = 0.0
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 2
        lp = lp * 0.55 + _noise() * 0.45
        out.append(max(-1.0, min(1.0, lp * 2.2)) * env * vol)
    return out

def _thump(dur=0.18, f0=140.0, drop=3.0, noise_amt=0.5, decay=6.0, vol=0.9):
    """Pitch-dropping sine + noise burst: an impact."""
    n = max(1, int(SAMPLE_RATE * dur))
    out = []
    phase = 0.0
    for i in range(n):
        t = i / n
        env = math.exp(-decay * t)
        f = f0 * (1.0 + (drop - 1.0) * math.exp(-8.0 * t))
        phase += 2.0 * math.pi * f / SAMPLE_RATE
        s = math.sin(phase) * 0.8 + _noise() * noise_amt
        out.append(max(-1.0, min(1.0, s)) * env * vol)
    return out

def _bell(dur=1.3, vol=0.55):
    """Round bell: detuned partials, slow decay, slight tremolo."""
    n = max(1, int(SAMPLE_RATE * dur))
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-2.2 * t)
        s = (math.sin(2 * math.pi * 880.0 * t)
             + 0.6 * math.sin(2 * math.pi * 1321.0 * t + 0.3)
             + 0.35 * math.sin(2 * math.pi * 1763.0 * t))
        s *= 1.0 + 0.15 * math.sin(2 * math.pi * 6.0 * t)
        out.append(max(-1.0, min(1.0, s * 0.33)) * env * vol)
    return out

def _crowd(dur=1.1, vol=0.5):
    """Crowd reaction: muffled noise roar that swells and fades."""
    n = max(1, int(SAMPLE_RATE * dur))
    out = []
    lp = 0.0
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 1.2
        wob = 0.75 + 0.25 * math.sin(2 * math.pi * 5.3 * t * dur)
        lp = lp * 0.86 + _noise() * 0.14
        out.append(max(-1.0, min(1.0, lp * 3.2)) * env * wob * vol)
    return out

def _to_wav_bytes(samples):
    """Pack float samples (-1..1) into an in-memory 16-bit mono WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 32767)
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return buf.getvalue()

# name -> zero-arg sample generator. Arcade feedback, not realism.
SOUND_SPECS = {
    "JAB":            lambda: _whoosh(0.09, 0.45),
    "CROSS":          lambda: _whoosh(0.12, 0.55),
    "HOOK":           lambda: _whoosh(0.14, 0.60),
    "UPPERCUT":       lambda: _whoosh(0.16, 0.60),
    "PUNCH_MISS":     lambda: _whoosh(0.10, 0.22),
    "HIT_LIGHT":      lambda: _thump(0.14, f0=160.0, noise_amt=0.45, decay=8.0),
    "HIT_HEAVY":      lambda: _thump(0.26, f0=90.0,  noise_amt=0.60, decay=5.0),
    "GUARD_HIT":      lambda: _thump(0.10, f0=230.0, noise_amt=0.30, decay=12.0, vol=0.7),
    "EVADE":          lambda: _whoosh(0.10, 0.32),
    "STEP":           lambda: _thump(0.06, f0=110.0, noise_amt=0.22, decay=16.0, vol=0.5),
    "BELL":           lambda: _bell(),
    "KNOCKDOWN":      lambda: _thump(0.40, f0=70.0,  noise_amt=0.70, decay=4.0),
    "CROWD_REACTION": lambda: _crowd(),
}

def build_wav_bytes():
    """Synthesize every SFX into WAV bytes. Pure stdlib; testable headless."""
    return {name: _to_wav_bytes(gen()) for name, gen in SOUND_SPECS.items()}

class SfxBank:
    """Loads procedural WAVs into pygame.mixer.Sound. Never raises."""
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        try:
            import pygame
            if not pygame.get_init():
                pygame.init()
            
            # CRITICAL: Reset mixer and reinit with explicit parameters
            # This ensures compatibility with our 22050Hz mono WAV files
            if pygame.mixer.get_init():
                pygame.mixer.quit()
            
            pygame.mixer.init(
                frequency=SAMPLE_RATE,
                size=-16,        # 16-bit signed
                channels=1,      # mono
                buffer=512       # small buffer for low latency
            )
            
            # Load sounds using BytesIO (more reliable than buffer parameter)
            for name, data in build_wav_bytes().items():
                buf = io.BytesIO(data)
                self.sounds[name] = pygame.mixer.Sound(file=buf)
            
            self.enabled = True
            print(f"[AUDIO] Mixer initialized: {pygame.mixer.get_init()}")
            print(f"[AUDIO] Loaded {len(self.sounds)} sounds")
            
        except Exception as e:
            # No audio device / headless / mixer trouble: stay silent.
            print(f"[AUDIO] Failed to initialize: {e}")
            self.enabled = False
            self.sounds = {}

    def play(self, name, volume=1.0):
        if not self.enabled:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            snd.set_volume(max(0.0, min(1.0, volume)))
            snd.play()
        except Exception:
            pass

class AudioDirector:
    """Consumes NEW match events exactly once and maps them to sounds.
    Event-driven, not frame-polled:
    * attack_start  -> punch whoosh, once per swing
    * hit           -> impact once (heavy = deeper/louder variant)
    * miss          -> lighter whoosh once per resolution
    * guard_hit     -> blocked impact
    * step          -> footstep (sim already rate-limits the event)
    * round_start/round_end -> bell
    * knockdown     -> thud + crowd reaction
    * rise/result   -> crowd reaction
    The 30 ms per-name guard below is a presentation-side safety net only
    (e.g. two footsteps in the same tick). It can NEVER change a
    simulation outcome -- the simulation does not know this class exists.
    """
    SIMPLE_MAP = {
        "round_start": [("BELL", 1.0)],
        "round_end":   [("BELL", 0.9)],
        "miss":        [("PUNCH_MISS", 0.8)],
        "guard_hit":   [("GUARD_HIT", 1.0)],
        "evade":       [("EVADE", 0.7)],
        "step":        [("STEP", 0.5)],
        "rise":        [("CROWD_REACTION", 0.5)],
        "result":      [("CROWD_REACTION", 1.0)],
        "knockdown":   [("KNOCKDOWN", 1.0), ("CROWD_REACTION", 0.9)],
    }

    def __init__(self, bank):
        self.bank = bank
        self.seen = 0
        self._last_played = {}

    def reset(self):
        self.seen = 0
        self._last_played = {}

    def process(self, match):
        events = match.events[self.seen:]
        self.seen = len(match.events)
        now = match.total_time
        for kind, payload in events:
            if kind == "attack_start":
                _name, key = payload
                sounds = [(key.upper(), 0.9)]
            elif kind == "hit":
                _name, _key, _dmg, heavy = payload
                sounds = [("HIT_HEAVY" if heavy else "HIT_LIGHT", 1.0)]
            else:
                sounds = self.SIMPLE_MAP.get(kind, [])
            
            for sname, vol in sounds:
                last = self._last_played.get(sname)
                if last is not None and (now - last) < 0.03:
                    continue
                self._last_played[sname] = now
                self.bank.play(sname, vol)