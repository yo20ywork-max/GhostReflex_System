import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from text_reader import read_text_segment, uncovered_file_reads, file_read_progress, validate_read_continuations, completed_file_contents, file_text_from_step, available_file_text_references
from types import SimpleNamespace


class TextReader(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'finetuning/release_v3'
        self.temp = tempfile.TemporaryDirectory(dir=root, prefix='text-read-test-')
        self.path = Path(self.temp.name) / '台灣原稿.txt'
    def tearDown(self):
        self.temp.cleanup()
    def observe(self, limit=100, start=0, sha=''):
        text, evidence = read_text_segment(self.path, limit, start, sha)
        return {'tool': 'READ_TEXT_FILE', 'args': {'path': str(self.path)}, 'output': text, 'evidence': evidence, 'ok': True, 'verified': True}
    def test_complete_segments_preserve_unicode_crlf_and_whitespace(self):
        text = '  臺灣🎞️\t\r\n' * 37
        raw = text.encode('utf8');self.path.write_bytes(raw)
        history=[];start=0;sha=''
        while True:
            item=self.observe(start=start,sha=sha);history.append(item)
            extent=item['evidence']['read_extent'];sha=extent['sha256'];start=extent['next_offset_chars']
            if start is None:break
        self.assertEqual(''.join(x['output'] for x in history),text)
        self.assertEqual(sha,hashlib.sha256(raw).hexdigest())
        self.assertEqual(uncovered_file_reads(history),[])
        self.assertTrue(uncovered_file_reads(history[:-1]))
    def test_a_missing_middle_is_not_hidden_by_reading_the_end(self):
        self.path.write_text('字'*300,encoding='utf8')
        first=self.observe();sha=first['evidence']['read_extent']['sha256']
        end=self.observe(start=200,sha=sha)
        gaps=uncovered_file_reads([first,end])
        self.assertEqual([(x['start'],x['end']) for x in gaps],[(100,200)])
        middle=self.observe(start=100,sha=sha)
        self.assertEqual(uncovered_file_reads([first,end,middle]),[])
    def test_continuation_requires_same_content_even_when_length_is_unchanged(self):
        self.path.write_text('甲'*200,encoding='utf8');first=self.observe()
        with self.assertRaisesRegex(ValueError,'expected_sha256'):self.observe(start=100)
        self.path.write_text('乙'*200,encoding='utf8')
        with self.assertRaisesRegex(ValueError,'雜湊'):self.observe(start=100,sha=first['evidence']['read_extent']['sha256'])
        new=self.observe();self.assertTrue(uncovered_file_reads([first,new]))
    def test_full_read_new_version_supersedes_older_partial_evidence(self):
        self.path.write_text('甲'*200,encoding='utf8');first=self.observe()
        self.path.write_text('完成',encoding='utf8');last=self.observe()
        self.assertEqual(uncovered_file_reads([first,last]),[])
        legacy={'tool':'READ_TEXT_FILE','ok':True,'verified':True,'output':'前段','evidence':{'path':last['evidence']['path'],'truncated':True}}
        self.assertTrue(uncovered_file_reads([legacy]));self.assertEqual(uncovered_file_reads([legacy,last]),[])
    def test_empty_file_and_multibyte_decoder_boundary(self):
        self.path.write_bytes(b'');item=self.observe()
        self.assertEqual(item['output'],'');self.assertEqual(uncovered_file_reads([item]),[])
        self.path.write_bytes(('a'*65535+'臺灣').encode('utf8'))
        item=self.observe(limit=100,start=65500,sha=hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(item['output'],'a'*35+'臺灣')

    def test_full_reference_rejects_reverted_version_and_untrusted_anchor(self):
        self.path.write_text('原稿',encoding='utf8');first=dict(self.observe(),step_id=1)
        self.path.write_text('變更',encoding='utf8');second=dict(self.observe(),step_id=2)
        self.path.write_text('原稿',encoding='utf8');third=dict(self.observe(),step_id=3)
        with self.assertRaisesRegex(ValueError,'較早'):file_text_from_step(1,[first,second,third])
        self.assertEqual(file_text_from_step(3,[first,second,third]),'原稿')
        self.assertEqual(available_file_text_references([first,second,third])[0]['reference'],'{{step:3.file_text}}')
        with self.assertRaisesRegex(ValueError,'唯一'):file_text_from_step(1,[first,first])
        for change in ({'verified':False},{'tool':'MODEL_GENERATE'},{'ok':False}):
            with self.assertRaisesRegex(ValueError,'已驗證'):file_text_from_step(1,[dict(first,**change)])

    def test_full_text_reference_catalog_contains_only_complete_usable_versions(self):
        self.path.write_text('原稿'*90,encoding='utf8');first=dict(self.observe(),step_id=7)
        self.assertEqual(available_file_text_references([first]),[])
        last=dict(self.observe(limit=1000,start=100,sha=first['evidence']['read_extent']['sha256']),step_id=8)
        references=available_file_text_references([first,last])
        self.assertEqual(references[0]['reference'],'{{step:7.file_text}}')
        self.assertEqual(file_text_from_step(7,[first,last]),'原稿'*90)
    def test_invalid_extent_or_wrong_output_length_cannot_satisfy(self):
        self.path.write_text('甲'*200,encoding='utf8');item=self.observe()
        item['evidence']['read_extent']['end']=200
        self.assertTrue(uncovered_file_reads([item]))
    def test_strict_offsets_do_not_silently_clamp_or_accept_booleans(self):
        self.path.write_text('內容',encoding='utf8')
        for offset in (-1,True):
            with self.assertRaises(ValueError):self.observe(start=offset)

    def test_progress_proposes_only_observed_missing_ranges(self):
        self.path.write_text('字'*227,encoding='utf8');first=self.observe()
        progress=file_read_progress([first]);record=progress['files'][0]
        self.assertFalse(record['whole_file_observed']);self.assertEqual(record['missing_ranges'],[{'start':100,'end':227}])
        self.assertEqual(record['next_reads'][0]['max_chars'],127)
        last=self.observe(limit=127,start=100,sha=record['sha256'])
        done=file_read_progress([first,last])['files'][0]
        self.assertTrue(done['whole_file_observed']);self.assertEqual(done['next_reads'],[])

    def test_prospective_plan_rejects_out_of_bounds_and_wrong_version(self):
        self.path.write_text('字'*227,encoding='utf8');first=self.observe();sha=first['evidence']['read_extent']['sha256']
        args={'path':str(self.path),'offset_chars':100,'expected_sha256':sha}
        def plan(value):return SimpleNamespace(steps=[SimpleNamespace(tool='READ_TEXT_FILE',args=value)])
        validate_read_continuations(plan(args),[first])
        for offset in (227,300):
            with self.assertRaisesRegex(ValueError,'超出'):validate_read_continuations(plan({**args,'offset_chars':offset}),[first])
        with self.assertRaisesRegex(ValueError,'最新觀察'):validate_read_continuations(plan({**args,'expected_sha256':'b'*64}),[first])
        with self.assertRaisesRegex(ValueError,'來源'):validate_read_continuations(plan({**args,'path':'其他.txt'}),[first])

    def test_unverified_legacy_read_does_not_erase_a_gap(self):
        self.path.write_text('字'*200,encoding='utf8');first=self.observe()
        legacy={'tool':'READ_TEXT_FILE','ok':True,'verified':False,'output':'字'*200,'evidence':{'path':first['evidence']['path'],'truncated':False}}
        self.assertTrue(uncovered_file_reads([first,legacy]))

    def test_assembly_retains_exact_text_and_source_positions_without_new_action(self):
        text='  字\t\r\n'*41;self.path.write_bytes(text.encode('utf8'))
        first=self.observe();sha=first['evidence']['read_extent']['sha256']
        overlapping=self.observe(limit=500,start=80,sha=sha)
        result=completed_file_contents([first,overlapping])[first['evidence']['path']]
        self.assertEqual(result['text'],text);self.assertFalse(result['new_dispatch'])
        self.assertEqual([x['sequence_index'] for x in result['source_segments']],[1,2])
        self.assertEqual(completed_file_contents([first]),{})

    def test_conflicting_overlap_cannot_be_assembled_even_with_same_claimed_hash(self):
        self.path.write_text('甲'*200,encoding='utf8');first=self.observe()
        last=self.observe(limit=200,start=80,sha=first['evidence']['read_extent']['sha256'])
        last['output']='乙'+last['output'][1:]
        with self.assertRaisesRegex(ValueError,'重疊'):completed_file_contents([first,last])

    def test_assembly_uses_latest_version_and_leaves_original_history_unchanged(self):
        import copy
        self.path.write_text('甲'*200,encoding='utf8');first=self.observe()
        self.path.write_bytes(' 新版\n'.encode('utf8'));last=self.observe();history=[first,last];before=copy.deepcopy(history)
        result=completed_file_contents(history)[last['evidence']['path']]
        self.assertEqual(result['text'],' 新版\n');self.assertEqual(result['source_segments'][0]['sequence_index'],2)
        self.assertEqual(history,before)

    def test_cancelled_read_returns_no_fragment(self):
        self.path.write_text('內容',encoding='utf8');event=threading.Event();event.set()
        with self.assertRaisesRegex(ValueError,'已取消'):read_text_segment(self.path,cancel_event=event)

    def test_handle_metadata_change_rejects_the_observation(self):
        import os
        self.path.write_text('內容',encoding='utf8');real=os.fstat;calls=[]
        def changed(fd):
            stat=real(fd);calls.append(1)
            if len(calls)==1:return stat
            from types import SimpleNamespace
            return SimpleNamespace(st_dev=stat.st_dev,st_ino=stat.st_ino,st_size=stat.st_size,
                                   st_mtime_ns=stat.st_mtime_ns+1,st_ctime_ns=stat.st_ctime_ns)
        with patch('text_reader.os.fstat',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'已變更'):self.observe()


if __name__ == '__main__':unittest.main()
