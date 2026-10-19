"""Delayed engine callbacks must not overwrite a different active task."""
import ast,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

tree=ast.parse((Path(__file__).resolve().parents[1]/'desktop_ui/app.py').read_text(encoding='utf8'))
bridge=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='Bridge')
scope={}
for method in bridge.body:
    if isinstance(method,ast.FunctionDef) and method.name in {'progress','done','ready'}:
        method.decorator_list=[]
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'<actual Qt task callbacks>','exec'),scope)

class TaskRouting(unittest.TestCase):
    def test_delayed_progress_cannot_enter_new_task(self):
        ui=SimpleNamespace(_active='new',_store=Mock(),_steps=[],changed=Mock())
        scope['progress'](ui,{'request_id':'old','step_id':1,'attempt':1,'ok':True,'output':'old evidence'})
        ui._store.add_event.assert_not_called();self.assertEqual(ui._steps,[])
    def test_delayed_result_persists_old_task_without_clearing_active_task(self):
        ui=SimpleNamespace(_active='new',_state='running',_result='',_store=Mock(),refresh=Mock())
        result=SimpleNamespace(status='completed',message='old result',history=[])
        scope['done'](ui,'old',result)
        ui._store.update.assert_called_once_with('old','completed','old result',[])
        self.assertEqual((ui._active,ui._state,ui._result),('new','running',''))
    def test_engine_ready_after_close_is_stopped_without_dispatch(self):
        ui=SimpleNamespace(_closing=True,dispatch=Mock());service=Mock()
        scope['ready'](ui,service)
        service.stop.assert_called_once();ui.dispatch.assert_not_called()
if __name__=='__main__':unittest.main()
