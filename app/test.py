from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

import numpy as np
import pygame

SAMPLE_RATE = 44100
BUFFER_SECONDS = 8.0
BASE_DIR = Path(__file__).resolve().parent
SOUNDS_DIR = BASE_DIR / "sounds-wav"


def generate_white_noise(duration_seconds: float = BUFFER_SECONDS) -> np.ndarray:
    sample_count = int(SAMPLE_RATE * duration_seconds)
    return np.random.normal(0, 1, sample_count)


def moving_average(signal: np.ndarray, window_size: int) -> np.ndarray:
    if window_size <= 1:
        return signal
    kernel = np.ones(window_size, dtype=np.float32) / float(window_size)
    return np.convolve(signal, kernel, mode="same")


def apply_fade_edges(samples: np.ndarray, fade_duration: float = 0.1) -> np.ndarray:
    fade_len = min(int(fade_duration * SAMPLE_RATE), len(samples) // 2)
    if fade_len <= 0:
        return samples
    fade_in = np.linspace(0.0, 1.0, fade_len, dtype=samples.dtype)
    fade_out = fade_in[::-1]
    samples[:fade_len] *= fade_in
    samples[-fade_len:] *= fade_out
    return samples


def normalize(samples: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(samples))
    if peak == 0:
        return samples
    return samples / peak

SOUND_PROFILES = [
    {"name": "Birds", "filename": "birds.wav"},
    {"name": "Crickets", "filename": "cricket.wav"},
    {"name": "Fire", "filename": "fire.wav"},
    {"name": "Rainfall", "filename": "rain.wav"},
    {"name": "Singing Bowl", "filename": "singingbowl.wav"},
    {"name": "Ocean Waves", "filename": "waves.wav"},
    {"name": "Wind", "filename": "wind.wav"},
    {"name": "Coffee Shop", "filename": "coffeeshop.wav"},
]


class AmbientMixerApp:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("Ambient Noise Mixer")
        self.master.configure(padx=20, pady=20)

        self.sounds = {}
        self.channels = {}

        self.volume_vars = {}
        self.value_labels = {}

        self._init_audio()
        self._build_sounds()
        self._build_ui()

        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_audio(self) -> None:
        pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=1024)
        pygame.mixer.init()
        pygame.sndarray.use_arraytype("numpy")
        pygame.mixer.set_num_channels(len(SOUND_PROFILES))

    def _build_sounds(self) -> None:
        for idx, profile in enumerate(SOUND_PROFILES):
            sound = self._load_sound(profile)
            name = profile["name"]
            channel = pygame.mixer.Channel(idx)
            channel.play(sound, loops=-1)
            channel.set_volume(0.5)
            self.sounds[name] = sound
            self.channels[name] = channel

    def _load_sound(self, profile: dict) -> pygame.mixer.Sound:
        file_path = SOUNDS_DIR / profile["filename"]
        if file_path.exists():
            try:
                return pygame.mixer.Sound(str(file_path))
            except pygame.error as err:
                print(f"Unable to load {file_path}: {err}. Falling back to generated audio.")
        else:
            print(f"Missing audio file for {profile['name']}: expected {file_path}.")
        return self._create_sound(profile["fallback"])

    def _create_sound(self, generator) -> pygame.mixer.Sound:
        """Generate a pygame Sound object from a procedural generator.

        Adapts the ndarray shape to whatever channel configuration the mixer
        actually initialized with. Some systems may force mono output even if
        we requested stereo, which previously caused:
            ValueError: Array depth must match number of mixer channels
        """
        raw = np.asarray(generator(), dtype=np.float32)
        raw = apply_fade_edges(normalize(raw).copy())

        init_info = pygame.mixer.get_init()
        if init_info is None:
            # Fallback: assume our requested defaults
            channels = 2
        else:
            _, _, channels = init_info

        # Ensure we have shape (n,) for mono or (n, channels) for >1.
        if channels <= 1:
            samples = raw
        else:
            # Tile the mono procedural signal across the required channels.
            samples = np.tile(raw[:, None], (1, channels))

        # Convert to int16 expected by -16 mixer format.
        try:
            int_samples = np.clip(samples * 32767, -32768, 32767).astype(np.int16)
            return pygame.sndarray.make_sound(int_samples.copy())
        except ValueError as err:
            # Provide detailed diagnostics to aid future debugging.
            print(
                f"[AudioGen] Failed to create sound (channels={channels}, shape={samples.shape}): {err}. "
                "Attempting emergency mono fallback.")
            mono = raw.astype(np.float32)
            int_mono = np.clip(mono * 32767, -32768, 32767).astype(np.int16)
            return pygame.sndarray.make_sound(int_mono.copy())

    def _build_ui(self) -> None:
        heading = ttk.Label(self.master, text="Mix and match your perfect ambience", font=("Segoe UI", 14, "bold"))
        heading.grid(row=0, column=0, columnspan=len(SOUND_PROFILES), pady=(0, 20))

        for col, profile in enumerate(SOUND_PROFILES):
            name = profile["name"]
            frame = ttk.Frame(self.master, padding=5)
            frame.grid(row=1, column=col, padx=12)

            ttk.Label(frame, text=name, font=("Segoe UI", 11)).pack()

            volume_var = tk.DoubleVar(value=50.0)
            self.volume_vars[name] = volume_var

            scale = ttk.Scale(
                frame,
                orient="vertical",
                from_=100.0,
                to=0.0,
                length=220,
                command=lambda value, key=name: self.on_volume_change(key, float(value)),
                variable=volume_var,
            )
            scale.pack(pady=6)

            value_var = tk.StringVar(value="50%")
            self.value_labels[name] = value_var
            ttk.Label(frame, textvariable=value_var).pack()

        ttk.Label(
            self.master,
            text="Tip: Leave channels around 40-60% and tweak slightly to taste.",
            font=("Segoe UI", 10),
        ).grid(row=2, column=0, columnspan=len(SOUND_PROFILES), pady=(18, 0))

    def on_volume_change(self, name: str, raw_value: float) -> None:
        volume = max(0.0, min(raw_value / 100.0, 1.0))
        if name in self.channels:
            self.channels[name].set_volume(volume)
        if name in self.value_labels:
            self.value_labels[name].set(f"{int(volume * 100)}%")

    def on_close(self) -> None:
        for channel in self.channels.values():
            channel.stop()
        pygame.mixer.quit()
        self.master.destroy()


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as err:
        print("Unable to start the GUI:", err)
        sys.exit(1)

    app = AmbientMixerApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except pygame.error as err:
        print("Audio subsystem error:", err)
        sys.exit(1)