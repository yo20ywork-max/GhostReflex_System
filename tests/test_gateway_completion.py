"""Read only the gateway AST; no desktop hooks, model loading or app startup."""
import ast,json,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

source=Path(__file__).resolve().parents[1]/'run_daemon.py'
tree=ast.parse(source.read_text(encoding='utf-8-sig'))
gateway=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OllamaGateway')
module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),gateway],type_ignores=[])
scope={'extract_json_object':json.loads}
exec(compile(ast.fix_missing_locations(module),str(source),'exec'),scope)
Gateway=scope['OllamaGateway']

def fake_ollama(chat):
    class Client:
        def __init__(self,**kwargs):pass
        def _request(self,response_type,method,path,**kwargs):return chat(**kwargs['json'])
        def chat(self,**kwargs):return self._request(dict,'POST','/api/chat',json=kwargs)
    return SimpleNamespace(Client=Client)

class GatewayCompletion(unittest.TestCase):
    def setUp(self):
        # These controls isolate response framing; the actual disk/SDK guard is
        # exercised with real temporary blobs in test_gateway_model_integrity.
        guard = patch('ollama_model_integrity.OllamaModelIntegrityGuard')
        guard.start()
        self.addCleanup(guard.stop)

    def test_text_generation_has_identity_and_preserves_task_and_literal_output(self):
        from product_identity import GENERATION_SYSTEM
        calls=[]
        literal='  e\u0301\n我是別的故事角色。\t'
        def chat(**kwargs):
            calls.append(kwargs)
            return {'done':True,'done_reason':'stop','message':{'content':literal}}
        scope['ollama']=fake_ollama(chat=chat)
        gateway=Gateway(SimpleNamespace(planner_models=('candidate',),planner_num_ctx=12288))
        task='僅輸出 JSON；保留 e\u0301。'
        for system in ('',task,GENERATION_SYSTEM):
            text,_=gateway.chat_text(prompt='原樣引用 e\u0301',system=system)
            self.assertEqual(text,literal)
            self.assertEqual(calls[-1]['messages'][-1],{'role':'user','content':'原樣引用 e\u0301'})
            self.assertTrue(calls[-1]['messages'][0]['content'].startswith(GENERATION_SYSTEM))
        self.assertTrue(calls[1]['messages'][0]['content'].endswith(task))
        self.assertEqual(calls[2]['messages'][0]['content'],GENERATION_SYSTEM)

    def test_text_generation_keeps_leading_and_trailing_literal_whitespace(self):
        literal='  第一行\n\t第二行\n'
        scope['ollama']=fake_ollama(chat=lambda **kwargs:{'done':True,'done_reason':'stop','message':{'content':literal}})
        gateway=Gateway(SimpleNamespace(planner_models=('candidate',),planner_num_ctx=6144))
        text,_=gateway.chat_text(prompt='輸出原文')
        self.assertEqual(text,literal)
    def test_schema_error_never_falls_back_to_unconstrained_json(self):
        formats=[]
        def chat(**kwargs):
            formats.append(kwargs['format'])
            raise RuntimeError('Unsupported schema')
        scope['ollama']=fake_ollama(chat=chat)
        gateway=Gateway(SimpleNamespace(planner_models=('candidate',),planner_num_ctx=6144))
        with self.assertRaises(RuntimeError):gateway.chat_json(messages=[{'role':'user','content':'plan'}],schema={'type':'object'})
        self.assertEqual(formats,[{'type':'object'}])
    def test_valid_looking_json_from_truncated_generation_is_rejected(self):
        scope['ollama']=fake_ollama(chat=lambda **kwargs:{'done':True,'done_reason':'length','message':{'content':'{}'}})
        gateway=Gateway(SimpleNamespace(planner_models=('candidate',),planner_num_ctx=6144))
        with self.assertRaisesRegex(RuntimeError,'截斷'):gateway.chat_json(messages=[{'role':'user','content':'plan'}],schema={})
    def test_completed_response_works_for_mapping_and_object(self):
        self.assertEqual(Gateway._message_content({'done':True,'done_reason':'stop','message':{'content':'ok'}}),'ok')
        self.assertEqual(Gateway._message_content(SimpleNamespace(done=True,done_reason='stop',message=SimpleNamespace(content='ok'))),'ok')
    def test_missing_or_false_completion_is_rejected(self):
        for response in ({'message':{'content':'ok'}},{'done':False,'message':{'content':'ok'}}):
            with self.assertRaises(RuntimeError):Gateway._message_content(response)
    def test_unicode_file_names_and_original_messages_are_preserved(self):
        messages=[{'role':'user','content':'e\u0301 / 精確檔名.txt','images':['unchanged']}]
        calls=[]
        def chat(**kwargs):
            calls.append(kwargs)
            return {'done':True,'done_reason':'stop','message':{'content':'{}'}}
        scope['ollama']=fake_ollama(chat=chat)
        gateway=Gateway(SimpleNamespace(planner_models=('candidate',),planner_num_ctx=6144))
        gateway.chat_json(messages=messages,schema={},images=['new-image'])
        self.assertEqual(messages[0]['content'],'e\u0301 / 精確檔名.txt')
        self.assertEqual(calls[0]['messages'][0]['content'],messages[0]['content'])
        self.assertEqual(messages[0]['images'],['unchanged'])
        self.assertEqual(calls[0]['messages'][0]['images'],['new-image'])
        self.assertIs(calls[0]['truncate'],False)
        self.assertIs(calls[0]['shift'],False)
        self.assertEqual(calls[0]['options'], {'temperature': 0, 'num_ctx': 6144,
                                              'repeat_penalty': 1.0, 'num_predict': 2048})

    def test_model_read_timeout_is_finite_and_reported_as_failure(self):
        import ollama,httpx
        clients=[]
        def transport(request):raise httpx.ReadTimeout('模型沒有回應',request=request)
        def client(**kwargs):
            instance=ollama.Client(transport=httpx.MockTransport(transport),**kwargs)
            clients.append(instance);return instance
        scope['ollama']=SimpleNamespace(Client=client)
        gateway=Gateway(SimpleNamespace(planner_models=('candidate',),planner_num_ctx=6144))
        try:
            self.assertEqual(clients[0]._client.timeout.read,180.0)
            with self.assertRaisesRegex(RuntimeError,'模型沒有回應'):gateway.chat_text(prompt='讀取')
        finally:clients[0]._client.close()

if __name__=='__main__':unittest.main()
