"""Real headless DOM actionability and side-effect receipts, no external navigation."""
import ast,json,unittest
from dataclasses import dataclass,field
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright

def load():
    source=Path(__file__).resolve().parents[1]/'run_daemon.py'
    nodes=[n for n in ast.parse(source.read_text(encoding='utf-8-sig')).body if getattr(n,'name',None) in {'ToolResult','BrowserSession','tool_browser_click'}]
    for n in nodes:
        if isinstance(n,ast.FunctionDef):n.decorator_list=[]
    scope={'dataclass':dataclass,'field':field,'json':json};module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),'<actual browser handler>','exec'),scope);return scope

class BrowserRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=load();cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()
    def setUp(self):
        self.page=self.browser.new_page();self.page.set_default_timeout(300)
        adapter=self.s['BrowserSession'].__new__(self.s['BrowserSession']);adapter.ensure=lambda:self.page
        self.ctx=SimpleNamespace(runtime=SimpleNamespace(browser=adapter))
    def tearDown(self):self.page.close()
    def test_wrong_label_returns_observed_unique_button_without_clicking(self):
        self.page.set_content('<button onclick="window.count=(window.count||0)+1">另存副本</button>')
        result=self.s['tool_browser_click'](self.ctx,'label','另存副本',True)
        self.assertFalse(result.ok);self.assertFalse(result.terminal)
        self.assertEqual(result.output['observed_locator'],{'by':'role','target':'button|另存副本','exact':True})
        self.assertEqual(self.page.evaluate('window.count||0'),0)
    def test_duplicate_named_buttons_do_not_produce_a_unique_locator(self):
        self.page.set_content('<button>選取</button><button>選取</button>')
        result=self.s['tool_browser_click'](self.ctx,'label','選取',True)
        self.assertEqual(result.output['exact_button_matches'],2);self.assertNotIn('observed_locator',result.output)
    def test_actionability_trial_does_not_double_click(self):
        self.page.set_content('<button onclick="window.count=(window.count||0)+1">顯示摘要</button>')
        result=self.s['tool_browser_click'](self.ctx,'text','顯示摘要',True)
        self.assertTrue(result.ok);self.assertEqual(self.page.evaluate('window.count'),1)
    def test_lost_response_after_click_is_terminal_and_preserves_actual_side_effect(self):
        self.page.set_content('<button onclick="window.count=(window.count||0)+1">新增草稿</button>')
        locator=self.page.get_by_role('button',name='新增草稿',exact=True)
        def click(**kwargs):
            locator.click(**kwargs)
            if not kwargs.get('trial'):raise RuntimeError('response lost after dispatch')
        self.ctx.runtime.browser.locator=lambda *args:SimpleNamespace(click=click)
        result=self.s['tool_browser_click'](self.ctx,'text','新增草稿',True)
        self.assertFalse(result.ok);self.assertTrue(result.terminal);self.assertEqual(self.page.evaluate('window.count'),1)
        self.assertFalse(result.output['outcome_confirmed'])
