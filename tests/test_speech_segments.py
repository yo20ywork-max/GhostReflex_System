"""Regression checks for the live microphone's initial-frame loss."""
import unittest
from speech_segments import SpeechSegmenter


class SpeechSegmentationTests(unittest.TestCase):
    def test_confirmation_keeps_first_two_speech_frames_once(self):
        segmenter = SpeechSegmenter()
        for frame in range(-10, 0):
            self.assertIsNone(segmenter.feed(frame, False))
        for frame in range(5):
            self.assertIsNone(segmenter.feed(frame, True))
        for frame in range(5, 12):
            self.assertIsNone(segmenter.feed(frame, False))
        segment = segmenter.feed(12, False)
        self.assertEqual(segment, list(range(-5, 13)))

    def test_short_noise_bursts_do_not_dispatch_or_cumulate(self):
        segmenter = SpeechSegmenter()
        for frame in range(40):
            self.assertIsNone(segmenter.feed(frame, frame % 3 != 2))

    def test_next_utterance_starts_with_clean_history(self):
        segmenter = SpeechSegmenter(pre_roll=3, start_frames=3, silence_frames=2)
        for frame in range(3): segmenter.feed(frame, True)
        self.assertIsNone(segmenter.feed(3, False))
        self.assertEqual(segmenter.feed(4, False), [0,1,2,3,4])
        for frame in range(10, 13): segmenter.feed(frame, True)
        segmenter.feed(13, False)
        self.assertEqual(segmenter.feed(14, False), [10,11,12,13,14])


if __name__ == '__main__': unittest.main()
