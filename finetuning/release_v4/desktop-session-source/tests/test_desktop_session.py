"""Guard transitions without ever injecting real mouse/keyboard events."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import desktop_session as session


class DesktopSession(unittest.TestCase):
    def runtime(self):
        from tests.test_objective_completion import load
        result=load()['ToolResult']
        registry={name:SimpleNamespace(handler=Mock(return_value=result(True,output=name,verified=True))) for name in session.NATIVE_TOOLS}
        registry['READ_TEXT_FILE']=SimpleNamespace(handler=Mock())
        return SimpleNamespace(TOOL_REGISTRY=registry,ToolResult=result)

    def test_each_native_tool_is_blocked_without_input_desktop(self):
        runtime=self.runtime();handlers={n:s.handler for n,s in runtime.TOOL_REGISTRY.items()}
        session.install(runtime)
        with patch.object(session,'observe',return_value={'ready':False,'known':True,'reason':'桌面未啟用'}):
            for name in session.NATIVE_TOOLS:
                result=runtime.TOOL_REGISTRY[name].handler(None)
                self.assertFalse(result.ok);self.assertTrue(result.terminal)
                self.assertFalse(result.evidence['native_dispatch_sent']);handlers[name].assert_not_called()
        self.assertIs(runtime.TOOL_REGISTRY['READ_TEXT_FILE'].handler,handlers['READ_TEXT_FILE'])

    def test_rechecks_between_native_steps_and_can_resume_after_unlock(self):
        runtime=self.runtime();handler=runtime.TOOL_REGISTRY['HOTKEY'].handler
        session.install(runtime);guarded=runtime.TOOL_REGISTRY['HOTKEY'].handler
        session.install(runtime);self.assertIs(runtime.TOOL_REGISTRY['HOTKEY'].handler,guarded)
        with patch.object(session,'observe',side_effect=[{'ready':True},{'ready':False,'reason':'未啟用'},{'ready':True}]):
            self.assertTrue(guarded(None,keys=['ctrl','c']).ok)
            self.assertFalse(guarded(None,keys=['ctrl','v']).ok)
            self.assertTrue(guarded(None,keys=['ctrl','v']).ok)
        self.assertEqual(handler.call_count,2)

    def test_query_failure_fails_closed_without_claiming_locked(self):
        with patch.object(session.os,'name','nt'),patch.object(session,'_windows_observation',side_effect=OSError('unavailable')):
            value=session.observe()
        self.assertFalse(value['ready']);self.assertFalse(value['known']);self.assertIn('無法確認',value['reason'])

    def test_disconnected_session_is_not_ready_even_with_input_desktop(self):
        with patch.object(session.os,'name','nt'),patch.object(session,'_windows_observation',return_value={
            'thread_desktop_receiving_input':True,'session_connection_state':4,'session_active':False}):
            self.assertFalse(session.observe()['ready'])

    def test_actual_vision_click_rechecks_after_model_wait(self):
        import ast
        from pathlib import Path
        from types import ModuleType
        runtime=self.runtime();module=ModuleType('isolated_native_handlers')
        module.__dict__.update(runtime.__dict__)
        tree=ast.parse((Path(__file__).resolve().parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig'))
        nodes=[n for n in tree.body if getattr(n,'name',None) in {'tool_vision_click','tool_mouse_click'}]
        for node in nodes:node.decorator_list=[]
        mouse=Mock()
        module.__dict__.update(pynput_mouse=mouse,object_schema=lambda *a,**k:{},
            capture_screen_file=lambda *a:('fixture.png',100,100,0,0))
        code=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
        exec(compile(ast.fix_missing_locations(code),'<actual native handlers>','exec'),module.__dict__)
        module.TOOL_REGISTRY['VISION_CLICK'].handler=module.tool_vision_click
        module.TOOL_REGISTRY['MOUSE_CLICK'].handler=module.tool_mouse_click
        session.install(module)
        ctx=SimpleNamespace(settings=SimpleNamespace(vision_models=['fixture']),gateway=Mock())
        ctx.gateway.chat_json.return_value=({'found':True,'x':20,'y':30,'confidence':1,'reason':'fixture'},'fixture')
        with patch.object(session,'observe',side_effect=[{'ready':True},{'ready':False,'reason':'桌面已切換'}]):
            result=module.TOOL_REGISTRY['VISION_CLICK'].handler(ctx,'button')
        self.assertFalse(result.ok);self.assertTrue(result.terminal)
        mouse.Controller.assert_not_called();ctx.gateway.chat_json.assert_called_once()


if __name__=='__main__':unittest.main()
