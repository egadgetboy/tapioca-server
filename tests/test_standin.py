"""CG-10: independently computed BlurHash vectors and FFmpeg isolation."""

import shutil
import subprocess
import unittest
from unittest.mock import patch

from app.standin import blurhash_from_image, blurhash_rgb24


class StandinVectors(unittest.TestCase):
    def test_constant_colors_have_reference_dct_encoding(self):
        cases = (
            ((0, 0, 0), 'T00000' + 'fQ' * 11),
            ((255, 255, 255), 'TfTSUA~qfQ~qt7fQfQfQfQ~qt7fQ'),
            ((255, 0, 0), 'TfTI:j|cfQ|csUfQfQfQfQ|csUfQ'),
            ((0, 255, 0), 'Tf09dghVfQhVg0fQfQfQfQhVg0fQ'),
        )
        for rgb, expected in cases:
            with self.subTest(rgb=rgb):
                actual = blurhash_rgb24(bytes(rgb) * (8 * 8), width=8, height=8)
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), 28)

    def test_different_art_has_different_hash(self):
        red = blurhash_rgb24(bytes([255, 0, 0]) * 64, width=8, height=8)
        blue = blurhash_rgb24(bytes([0, 0, 255]) * 64, width=8, height=8)
        self.assertNotEqual(red, blue)

    def test_raw_rgb_frame_has_exact_shape(self):
        for frame, width, height in (
            (b'', 2, 2),
            (b'\x00' * 11, 2, 2),
            (b'\x00' * 13, 2, 2),
            (b'\x00' * 12, 0, 2),
            (b'\x00' * 12, 2, -1),
        ):
            with self.subTest(length=len(frame), width=width, height=height), self.assertRaises(ValueError):
                blurhash_rgb24(frame, width, height)

    def test_encoded_art_rejects_empty_or_oversized_input_before_ffmpeg(self):
        with patch('app.standin.subprocess.run') as run:
            for invalid_artwork in (b'', b'X' * (32 * 1024 * 1024 + 1)):
                with self.subTest(length=len(invalid_artwork)), self.assertRaises(ValueError):
                    blurhash_from_image(invalid_artwork)
            run.assert_not_called()

    def test_decoder_failure_and_timeout_do_not_leak_ffmpeg_details(self):
        failed = subprocess.CompletedProcess(args=['ffmpeg'], returncode=1, stdout=b'', stderr=b'secret path: /home/owner/poster.jpg')
        with patch('app.standin.subprocess.run', return_value=failed), self.assertRaisesRegex(ValueError, 'could not decode') as caught:
            blurhash_from_image(b'bad image')
            self.assertNotIn('/home/', str(caught.exception))
        with patch('app.standin.subprocess.run', side_effect=subprocess.TimeoutExpired(['ffmpeg'], 10)), self.assertRaisesRegex(ValueError, 'could not decode'):
            blurhash_from_image(b'bad image')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for the image-to-raw integration test')
    def test_real_ffmpeg_raw_frame_is_decoded_without_a_new_library(self):
        # Tiny portable PPM with no image library dependency; PNG/JPEG pass
        # through the same image2pipe decoder when wired by Claude.
        ppm = b'P6\n8 8\n255\n' + bytes([255, 0, 0]) * 64
        result = blurhash_from_image(ppm)
        self.assertEqual(result, 'TKTI:j|cfQ;$o1fQfQfQfQ;$o1fQ')


if __name__ == '__main__':
    unittest.main()
