import unittest

from spikes.live_native import PCMChunker
from spikes.transport import SourceRouter


class FakeRouter:
    def __init__(self):
        self.frames = []
        self.resets = []

    def feed(self, source, start_ms, pcm):
        self.frames.append((source, start_ms, len(pcm)))

    def reset(self, source, end_ms, reason):
        self.resets.append((source, end_ms, reason))


class PCMChunkerTests(unittest.TestCase):
    def test_converts_native_twenty_ms_buffers_into_bounded_contiguous_frames(self):
        router = FakeRouter()
        chunker = PCMChunker('system', router)
        for index in range(5):
            chunker.feed(100 + index * 20, bytes(640))
        chunker.finish()
        self.assertEqual(router.frames, [
            ('system', 100, 1024), ('system', 132, 1024),
            ('system', 164, 1024), ('system', 196, 128)])
        self.assertEqual(router.resets, [])

    def test_timestamp_jump_drops_uncommitted_tail_and_resets_only_source(self):
        router = FakeRouter()
        chunker = PCMChunker('mic', router)
        chunker.feed(100, bytes(640))
        chunker.feed(300, bytes(1024))
        chunker.finish()
        self.assertEqual(router.resets, [('mic', 300, 'native_timestamp_discontinuity')])
        self.assertEqual(router.frames, [('mic', 300, 1024)])
        self.assertEqual(chunker.discontinuities, 1)

    def test_rejects_unaligned_pcm(self):
        with self.assertRaises(ValueError):
            PCMChunker('system', FakeRouter()).feed(0, b'\x00')

    def test_prepared_decoder_starts_at_first_native_timestamp_without_reset(self):
        created = []
        class Decoder:
            def __init__(self):
                self.offset = None
                self.frames = []
            def start_at(self, start_ms): self.offset = start_ms
            def submit(self, pcm): self.frames.append(pcm); return True
            def abort(self): pass
        def factory(source, epoch, start_ms, callback):
            decoder = Decoder(); created.append(decoder); return decoder
        router = SourceRouter(factory, lambda event: None)
        router.prepare('system')
        self.assertEqual(len(created), 1)
        router.feed('system', 404, bytes(1024))
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].offset, 404)
        self.assertEqual(len(created[0].frames), 1)
        self.assertEqual(router.sources['system']['expected'], 436)


if __name__ == '__main__':
    unittest.main()
