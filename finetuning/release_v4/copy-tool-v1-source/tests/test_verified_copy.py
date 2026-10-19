"""Real byte-copy and race/cancellation checks, all in bounded disposable folders."""
import hashlib
import ast
from dataclasses import dataclass,field
import tempfile
import threading
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import verified_copy as copy

ROOT=Path(__file__).resolve().parents[1]


class VerifiedCopy(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='copy-check-',dir=ROOT/'finetuning/release_v4')
        self.work=Path(self.temp.name).resolve()
        self.assertTrue(self.work.is_relative_to(ROOT))
        self.source=self.work/'原稿.bin';self.dest=self.work/'副本.bin'
        self.content=b'\xef\xbb\xbf'+('  台灣\t𠮷😀\r\n{{step:99.output}}  '.encode())+bytes(range(256))*8192
        self.source.write_bytes(self.content)

    def tearDown(self):
        self.assertTrue(self.work.is_relative_to(ROOT));self.temp.cleanup()

    def test_binary_multichunk_copy_is_exact_and_independent(self):
        result=copy.copy_verified(self.source,self.dest,workspace=self.work)
        self.assertEqual(self.dest.read_bytes(),self.content)
        self.assertEqual(result['sha256'],hashlib.sha256(self.content).hexdigest())
        self.assertFalse(result['whole_task_verified'])
        self.dest.write_bytes(b'changed later')
        self.assertEqual(self.source.read_bytes(),self.content)
        self.assertFalse(list(self.work.glob('.crossgen-copy-*')))

    def test_empty_source_creates_verified_empty_destination(self):
        self.source.write_bytes(b'')
        result=copy.copy_verified(self.source,self.dest,workspace=self.work)
        self.assertEqual(result['bytes'],0);self.assertEqual(self.dest.read_bytes(),b'')
        self.assertTrue(result['destination_readback_verified'])

    def test_skip_existing_does_not_read_or_require_source(self):
        self.dest.write_bytes(b'other version')
        result=copy.copy_verified('missing-source',self.dest,workspace=self.work,if_exists='skip')
        self.assertFalse(result['source_read']);self.assertFalse(result['copied'])
        self.assertEqual(self.dest.read_bytes(),b'other version')

    def test_destination_appearing_at_publish_is_not_overwritten(self):
        original=copy._publish
        def race(temporary,target):
            target.write_bytes(b'created by another process')
            return original(temporary,target)
        with patch('verified_copy._publish',side_effect=race):
            with self.assertRaises(FileExistsError):copy.copy_verified(self.source,self.dest,workspace=self.work)
        self.assertEqual(self.dest.read_bytes(),b'created by another process')
        self.assertFalse(list(self.work.glob('.crossgen-copy-*')))

    def test_cancel_after_copy_before_publish_removes_only_owned_temp(self):
        event=threading.Event();original=copy._hash
        def cancel_after_readback(stream,cancel=None):
            result=original(stream,cancel);event.set();return result
        with patch('verified_copy._hash',side_effect=cancel_after_readback):
            with self.assertRaises(copy.CopyCancelled):copy.copy_verified(self.source,self.dest,workspace=self.work,cancel=event)
        self.assertFalse(self.dest.exists());self.assertEqual(self.source.read_bytes(),self.content)
        self.assertFalse(list(self.work.glob('.crossgen-copy-*')))

    def test_source_mutation_is_rejected_before_destination_exists(self):
        original=copy._hash;changed=False
        def mutate_source(stream,cancel=None):
            nonlocal changed
            if not changed:
                changed=True
                with self.source.open('r+b') as source:source.write(b'new')
            return original(stream,cancel)
        with patch('verified_copy._hash',side_effect=mutate_source):
            with self.assertRaisesRegex(RuntimeError,'來源在複製期間有變化'):
                copy.copy_verified(self.source,self.dest,workspace=self.work)
        self.assertFalse(self.dest.exists());self.assertFalse(list(self.work.glob('.crossgen-copy-*')))

    def test_outside_destination_is_rejected_without_creation(self):
        with self.assertRaisesRegex(ValueError,'超出工作區'):
            copy.copy_verified(self.source,self.work.parent/'outside.bin',workspace=self.work)

    def test_runtime_catalog_and_handler_carry_actual_copy_evidence(self):
        from jsonschema import Draft202012Validator,ValidationError
        tree=ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig'))
        names={'ToolResult','ToolSpec','tool','object_schema','build_plan_schema'}
        nodes=[node for node in tree.body if getattr(node,'name',None) in names]
        scope={'dataclass':dataclass,'field':field,'TOOL_REGISTRY':{}}
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'<actual catalog definitions>','exec'),scope)
        runtime=SimpleNamespace(**scope);handler=copy.register(runtime)
        self.assertIs(copy.register(runtime),handler)
        plan={'objective':'備份','assumptions':[],'steps':[{'id':1,'goal':'原樣複製','tool':'COPY_FILE_VERIFIED',
              'args':{'source':self.source.name,'destination':self.dest.name},'success_check':'核對回執'}],'completion_criteria':['完成備份']}
        validator=Draft202012Validator(runtime.build_plan_schema(SimpleNamespace(max_plan_steps=24)))
        validator.validate(plan)
        result=handler(SimpleNamespace(settings=SimpleNamespace(workspace=self.work)),self.source.name,self.dest.name)
        self.assertTrue(result.ok);self.assertTrue(result.verified)
        self.assertEqual(result.evidence['sha256'],hashlib.sha256(self.content).hexdigest())
        self.assertFalse(result.evidence['whole_task_verified'])
        plan['steps'][0]['args']['content']='模型不應重新生成原檔內容'
        with self.assertRaises(ValidationError):validator.validate(plan)


if __name__=='__main__':unittest.main()
