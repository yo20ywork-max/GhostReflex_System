"""Keep speech onset while waiting for VAD confirmation, without duplicating frames."""
from collections import deque


class SpeechSegmenter:
    def __init__(self, pre_roll=8, start_frames=3, silence_frames=8):
        if min(pre_roll, start_frames, silence_frames) < 1 or pre_roll < start_frames:
            raise ValueError('Invalid speech segmentation limits')
        self.pre = deque(maxlen=pre_roll)
        self.start_frames = start_frames
        self.silence_frames = silence_frames
        self.buffer = []
        self.active = False
        self.streak = 0
        self.silence = 0

    def feed(self, chunk, is_speech):
        if not self.active:
            # Include the tentative speech frames, not just preceding silence.
            self.pre.append(chunk)
        if is_speech:
            self.streak += 1
            if not self.active and self.streak >= self.start_frames:
                self.active = True
                self.buffer.extend(self.pre)
            elif self.active:
                self.buffer.append(chunk)
            self.silence = 0
        else:
            self.streak = 0
            if self.active:
                self.buffer.append(chunk)
                self.silence += 1
        if not self.active or self.silence < self.silence_frames:
            return None
        segment = self.buffer
        self.buffer = []
        self.pre.clear()
        self.active = False
        self.streak = self.silence = 0
        return segment
