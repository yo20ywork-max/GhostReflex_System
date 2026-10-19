import ast,unittest
from types import SimpleNamespace
from score import ROOT,equivalent_argument
class KeySemanticsTest(unittest.TestCase):
    def test_matches_real_executor_without_pressing_keys(self):
        tree=ast.parse((ROOT.parent.parent/'run_daemon.py').read_text(encoding='utf-8-sig'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='key_from_name')
        keys=SimpleNamespace(tab=object(),ctrl=object(),enter=object(),cmd=object(),left=object())
        scope={'Any':object,'pynput_keyboard':SimpleNamespace(Key=keys)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<isolated key resolver>','exec'),scope)
        for a,b in [('Tab','tab'),('Control','ctrl'),('Return','enter'),('Win','cmd'),('Arrow Left','left')]:
            self.assertIs(scope['key_from_name'](a),scope['key_from_name'](b))
            self.assertTrue(equivalent_argument('PRESS_KEY','key',a,b))
    def test_no_scope_or_literal_normalization(self):
        self.assertFalse(equivalent_argument('PRESS_KEY','key','tab','enter'))
        self.assertFalse(equivalent_argument('PRESS_KEY','count',10,9))
        self.assertFalse(equivalent_argument('TYPE_TEXT','text','Tab','tab'))
        self.assertFalse(equivalent_argument('BROWSER_PRESS','key','Control','control'))
        self.assertFalse(equivalent_argument('READ_TEXT_FILE','path','File','file'))
        self.assertTrue(equivalent_argument('HOTKEY','keys',['Control','C'],['ctrl','c']))
if __name__=='__main__':unittest.main()
