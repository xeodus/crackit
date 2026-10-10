import unittest
from dataclasses import FrozenInstanceError, replace
from spikes.core import ContextStore, Segment, RequestGate, clip_utf8
from spikes.metrics import audio_cost, token_cost, word_error_rate, percentile
from decimal import Decimal


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.store = ContextStore()
        self.store.start('tenant-a', 'meeting')

    def tearDown(self):
        self.store.close()

    def segment(self, text='Approved annual pricing is twelve thousand dollars.', **kwargs):
        return Segment('pricing', 'tenant-a', 'meeting', 0, 0, 2000, text, **kwargs)

    def test_revisions_replace_partials_without_duplicates(self):
        base = self.segment('The price is fifteen', state='partial')
        self.store.ingest(base)
        self.store.ingest(replace(base, revision=1, text='The price is twelve thousand', state='partial'))
        self.store.ingest(replace(base, revision=2, text='The price is twelve thousand dollars.', state='final'))
        rows = self.store.transcript('tenant-a', 'meeting')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['text'], 'The price is twelve thousand dollars.')

    def test_duplicate_replay_is_idempotent(self):
        seg = self.segment()
        self.assertTrue(self.store.ingest(seg))
        version = self.store.session('tenant-a', 'meeting')['version']
        self.assertFalse(self.store.ingest(seg))
        self.assertEqual(self.store.session('tenant-a', 'meeting')['version'], version)

    def test_out_of_order_revision_is_ignored(self):
        seg = replace(self.segment(), revision=3)
        self.store.ingest(seg)
        self.assertFalse(self.store.ingest(replace(seg, revision=2, text='stale text')))
        self.assertEqual(self.store.transcript('tenant-a', 'meeting')[0]['revision'], 3)

    def test_conflicting_same_revision_rejected(self):
        seg = self.segment()
        self.store.ingest(seg)
        with self.assertRaises(ValueError):
            self.store.ingest(replace(seg, text='conflicting value'))

    def test_final_correction_removes_stale_search_hit(self):
        seg = self.segment('Pricing was fifteen thousand dollars.')
        self.store.ingest(seg)
        with self.assertRaises(ValueError):
            self.store.ingest(replace(seg, revision=1, text='Pricing is twelve thousand dollars.'))
        self.store.ingest(replace(seg, revision=1, text='Pricing is twelve thousand dollars.'), correction=True)
        self.assertEqual(self.store.retrieve('tenant-a', 'meeting', 'fifteen'), [])
        self.assertEqual(self.store.retrieve('tenant-a', 'meeting', 'twelve')[0].revision, 1)

    def test_final_cannot_regress_to_partial(self):
        seg = self.segment()
        self.store.ingest(seg)
        with self.assertRaises(ValueError):
            self.store.ingest(replace(seg, revision=1, state='partial'), correction=True)

    def test_source_or_epoch_cannot_change_on_revision(self):
        seg = self.segment(state='partial')
        self.store.ingest(seg)
        for fields in ({'source': 'mic'}, {'epoch': 1}):
            with self.assertRaises(ValueError):
                self.store.ingest(replace(seg, revision=1, **fields))

    def test_tenant_and_session_are_always_scoped(self):
        self.store.start('tenant-b', 'meeting')
        self.store.start('tenant-a', 'other')
        self.store.ingest(self.segment())
        self.store.ingest(replace(self.segment('secret pricing'), tenant='tenant-b'))
        self.store.ingest(replace(self.segment('other meeting pricing'), session='other'))
        answers = self.store.retrieve('tenant-a', 'meeting', 'pricing')
        self.assertEqual(len(answers), 1)
        self.assertNotIn('secret', answers[0].text)
        self.assertNotIn('other meeting', answers[0].text)
        with self.assertRaises(KeyError):
            self.store.freeze('unknown', 'meeting', 'r', 'pricing')

    def test_partials_are_not_durable_retrieval_evidence(self):
        self.store.ingest(self.segment('provisional fifteen thousand', state='partial'))
        self.assertEqual(self.store.retrieve('tenant-a', 'meeting', 'fifteen'), [])
        snap = self.store.freeze('tenant-a', 'meeting', 'r', 'What was said?')
        self.assertEqual(snap.evidence, ())
        self.assertEqual(snap.provisional[0].state, 'partial')

    def test_pause_stop_resume_and_gaps(self):
        self.store.transition('tenant-a', 'meeting', 'pause')
        with self.assertRaises(ValueError):
            self.store.ingest(self.segment())
        self.store.transition('tenant-a', 'meeting', 'resume')
        self.store.ingest(self.segment())
        self.store.gap('tenant-a', 'meeting', 2000, 4000, 'network_disconnect')
        self.assertEqual(self.store.gaps('tenant-a', 'meeting')[0]['reason'], 'network_disconnect')
        self.store.transition('tenant-a', 'meeting', 'stop')
        with self.assertRaises(ValueError):
            self.store.transition('tenant-a', 'meeting', 'stop')
        self.store.transition('tenant-a', 'meeting', 'resume')
        self.assertEqual(len(self.store.transcript('tenant-a', 'meeting')), 1)

    def test_snapshot_is_immutable_and_versioned(self):
        self.store.ingest(self.segment())
        snap = self.store.freeze('tenant-a', 'meeting', 'r', 'pricing')
        self.assertIsInstance(snap.evidence, tuple)
        with self.assertRaises(FrozenInstanceError):
            snap.evidence[0].text = 'mutation'
        self.store.ingest(replace(self.segment(), revision=1, text='new pricing'), correction=True)
        newer = self.store.freeze('tenant-a', 'meeting', 'new', 'pricing')
        self.assertLess(snap.version, newer.version)
        self.assertNotEqual(snap.digest, newer.digest)
        self.assertNotEqual(snap.evidence[0].text, newer.evidence[0].text)

    def test_budget_is_bounded_for_unicode_and_huge_segments(self):
        self.store.ingest(self.segment('बजट बारह हजार है। ' * 1000))
        snap = self.store.freeze('tenant-a', 'meeting', 'r', 'कितना है? ' * 1000,
                                 token_budget=100, max_utf8_bytes=250)
        self.assertLessEqual(snap.utf8_bytes, 250)
        self.assertLessEqual(snap.estimated_tokens, 100)
        self.assertTrue(snap.truncated)
        snap.question.encode('utf-8')

    def test_old_relevant_fact_survives_long_meeting(self):
        self.store.ingest(self.segment('Orion launch approval belongs to Mira.'))
        for i in range(500):
            self.store.ingest(replace(self.segment('Routine unrelated status update.'), id=str(i),
                                      start_ms=3000+i*2000, end_ms=4000+i*2000))
        snap = self.store.freeze('tenant-a', 'meeting', 'r', 'Orion launch approval', recent_count=4)
        self.assertIn('pricing', [e.id for e in snap.evidence])
        self.assertLessEqual(snap.estimated_tokens, 1800)

    def test_delete_removes_transcript_and_fts(self):
        self.store.ingest(self.segment())
        self.store.delete('tenant-a', 'meeting')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM evidence_fts').fetchone()[0], 0)
        with self.assertRaises(KeyError):
            self.store.transcript('tenant-a', 'meeting')

    def test_untrusted_query_cannot_inject_fts_operators(self):
        self.store.ingest(self.segment())
        self.store.retrieve('tenant-a', 'meeting', '" OR * NEAR(pricing) ; DROP TABLE segments;')
        self.assertEqual(len(self.store.transcript('tenant-a', 'meeting')), 1)

    def test_invalid_timestamps_rejected(self):
        with self.assertRaises(ValueError):
            self.store.ingest(replace(self.segment(), start_ms=100, end_ms=10))


class MetricsTests(unittest.TestCase):
    def test_wer_edits_and_empty_reference(self):
        self.assertEqual(word_error_rate('one two three', 'one four three')['wer'], 1/3)
        self.assertEqual(word_error_rate('Hello, WORLD!', 'hello world')['wer'], 0)
        self.assertEqual(word_error_rate('', '')['wer'], 0)
        self.assertIsNone(word_error_rate('', 'hallucination')['wer'])

    def test_audio_cost_counts_two_streams_and_fractional_seconds(self):
        self.assertEqual(audio_cost('3600', 2, '.15'), Decimal('.30'))
        self.assertEqual(audio_cost('30', 1, '.15'), Decimal('.00125'))

    def test_token_cost_does_not_round_each_small_call(self):
        self.assertEqual(token_cost(6000, 250, '.10', '.40'), Decimal('.0007'))
        with self.assertRaises(ValueError):
            token_cost(-1, 0, '.1', '.4')

    def test_percentile_definition(self):
        self.assertEqual(percentile([3, 1, 2, 4], 50), 2)
        self.assertEqual(percentile([3, 1, 2, 4], 95), 4)
        with self.assertRaises(ValueError):
            percentile([], 95)

    def test_request_gate_rejects_old_or_canceled_outputs(self):
        gate = RequestGate()
        gate.begin('old'); gate.begin('new')
        self.assertFalse(gate.accepts('old'))
        self.assertTrue(gate.accepts('new'))
        gate.cancel(); self.assertFalse(gate.accepts('new'))

    def test_utf8_clipping_never_splits_characters(self):
        self.assertEqual(clip_utf8('ह', 2), '')
        self.assertEqual(clip_utf8('ह', 3), 'ह')


if __name__ == '__main__':
    unittest.main()
