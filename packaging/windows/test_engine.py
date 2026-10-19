import hashlib
import http.server
import io
import json
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import zipfile
from unittest.mock import patch
from engine import download,extract,Cancelled,Job,Installer,SafeRedirect


class InstallerTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.cancel=threading.Event()
    def tearDown(self):self.temp.cleanup()
    def server(self,ignore_range=False,wrong_range=False):
        data=b'crossgen-resume-data'*10000
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                start=int(self.headers.get('Range','bytes=0-')[6:].split('-')[0])
                if ignore_range:start=0
                self.send_response(206 if self.headers.get('Range') and not ignore_range else 200)
                if self.headers.get('Range') and not ignore_range:self.send_header('Content-Range',f'bytes {start+int(wrong_range)}-{len(data)-1}/{len(data)}')
                self.send_header('Content-Length',str(len(data)-start));self.end_headers();self.wfile.write(data[start:])
        srv=socketserver.TCPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        self.addCleanup(srv.server_close);self.addCleanup(srv.shutdown)
        return {'url':f'http://127.0.0.1:{srv.server_address[1]}/file','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},data
    def test_resume_keeps_verified_bytes(self):
        item,data=self.server();target=self.root/'model';target.with_suffix('.part').write_bytes(data[:1000])
        download(item,target,self.cancel,lambda *_:None)
        self.assertEqual(target.read_bytes(),data)
    def test_server_ignoring_range_restarts_cleanly(self):
        item,data=self.server(ignore_range=True);target=self.root/'model';target.with_suffix('.part').write_bytes(data[:1000])
        download(item,target,self.cancel,lambda *_:None)
        self.assertEqual(target.read_bytes(),data)
    def test_wrong_range_never_appends(self):
        item,data=self.server(wrong_range=True);target=self.root/'model';part=target.with_suffix('.part');part.write_bytes(data[:1000])
        with self.assertRaisesRegex(RuntimeError,'續傳範圍'):download(item,target,self.cancel,lambda *_:None)
        self.assertEqual(part.read_bytes(),data[:1000]);self.assertFalse(target.exists())
    def test_hash_mismatch_not_published(self):
        item,data=self.server();item['sha256']='0'*64;target=self.root/'model'
        with self.assertRaisesRegex(RuntimeError,'校驗失敗'):download(item,target,self.cancel,lambda *_:None)
        self.assertFalse(target.exists())
    def test_cancel_never_publishes_partial_file(self):
        item,data=self.server();target=self.root/'model'
        with self.assertRaises(Cancelled):download(item,target,self.cancel,lambda *_:self.cancel.set())
        self.assertFalse(target.exists())
    def test_secrets_removed_on_cross_host_redirect(self):
        request=urllib.request.Request('https://huggingface.co/model',headers={'Authorization':'Bearer secret'})
        new=SafeRedirect().redirect_request(request,None,302,'',{},'https://cdn.example.org/file')
        self.assertIsNone(new.get_header('Authorization'))
    def test_zip_traversal_and_ads_rejected(self):
        for name in ['../outside','/absolute','C:/outside','good:stream','a\\..\\outside']:
            blob=self.root/'bad.zip'
            with zipfile.ZipFile(blob,'w') as z:z.writestr(name,b'bad')
            with self.assertRaises(ValueError):extract(blob,self.root/'out',self.cancel)
    def test_zip_extracts_normal_tree(self):
        blob=self.root/'ok.zip'
        with zipfile.ZipFile(blob,'w') as z:z.writestr('App/sub/file',b'correct')
        extract(blob,self.root/'out',self.cancel,'App/')
        self.assertEqual((self.root/'out/sub/file').read_bytes(),b'correct')
    def test_close_all_kills_owned_descendants_but_not_unrelated_process(self):
        import psutil
        unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)
        job=Job()
        try:
            child=job.start([sys.executable,'-c',"import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);print(p.pid,flush=True);time.sleep(30)"],stdout=subprocess.PIPE)
            grandchild=int(child.stdout.readline())
            job.close();child.stdout.close()
            time.sleep(0.2)
            self.assertIsNotNone(child.poll());self.assertFalse(psutil.pid_exists(grandchild));self.assertIsNone(unrelated.poll())
            with self.assertRaises(Cancelled):job.start([sys.executable,'-c','pass'])
        finally:job.close();unrelated.terminate();unrelated.wait()
    def test_model_service_environment_does_not_receive_hf_credentials(self):
        with patch.dict('os.environ',{'HF_TOKEN':'secret','HUGGING_FACE_HUB_TOKEN':'secret'}):
            worker=Installer(self.root,{},lambda *_:None,self.cancel,None)
        self.assertNotIn('HF_TOKEN',worker.env);self.assertNotIn('HUGGING_FACE_HUB_TOKEN',worker.env)
    def test_parts_assembled_and_verified_before_extract(self):
        part,data=self.server()
        item={'parts':[part,part],'bytes':len(data)*2,'sha256':hashlib.sha256(data+data).hexdigest()}
        worker=Installer(self.root,{},lambda *_:None,self.cancel,None)
        target=self.root/'application.zip';worker.fetch(item,target)
        self.assertEqual(target.read_bytes(),data+data)
        self.assertFalse(list(worker.cache.glob('*-part-*.bin')))


if __name__=='__main__':unittest.main()
