"""Read-only Windows input readiness and explicit native-tool dispatch guard."""
import ctypes
import functools
import os
from datetime import datetime,timezone

NATIVE_TOOLS=frozenset({
    'PAUSE_OR_PLAY','CLOSE_TAB','TYPE_TEXT','HOTKEY','PRESS_KEY','MOUSE_CLICK',
    'MOUSE_SCROLL','CAPTURE_SCREEN','ANALYZE_SCREEN','VISION_CLICK','VERIFY_SCREEN',
    'GET_ACTIVE_WINDOW','FOCUS_WINDOW',
})


def _windows_observation():
    from ctypes import wintypes as w
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    wts=ctypes.WinDLL('wtsapi32',use_last_error=True)
    kernel.GetCurrentThreadId.argtypes=[];kernel.GetCurrentThreadId.restype=w.DWORD
    user.GetThreadDesktop.argtypes=[w.DWORD];user.GetThreadDesktop.restype=w.HANDLE
    user.GetUserObjectInformationW.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
    user.GetUserObjectInformationW.restype=w.BOOL
    wts.WTSQuerySessionInformationW.argtypes=[w.HANDLE,w.DWORD,ctypes.c_int,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(w.DWORD)]
    wts.WTSQuerySessionInformationW.restype=w.BOOL
    wts.WTSFreeMemory.argtypes=[ctypes.c_void_p];wts.WTSFreeMemory.restype=None
    desktop=user.GetThreadDesktop(kernel.GetCurrentThreadId())
    if not desktop:raise ctypes.WinError(ctypes.get_last_error())
    # Borrowed GetThreadDesktop handle: do not CloseDesktop it.
    receiving=w.BOOL();needed=w.DWORD()
    if not user.GetUserObjectInformationW(desktop,6,ctypes.byref(receiving),ctypes.sizeof(receiving),ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    buffer=ctypes.c_void_p();size=w.DWORD()
    # WTS_CURRENT_SERVER_HANDLE, WTS_CURRENT_SESSION, WTSConnectState.
    if not wts.WTSQuerySessionInformationW(None,0xffffffff,8,ctypes.byref(buffer),ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not buffer or size.value<ctypes.sizeof(ctypes.c_int):raise OSError('Invalid WTS state buffer')
        state=ctypes.cast(buffer,ctypes.POINTER(ctypes.c_int)).contents.value
    finally:
        if buffer:wts.WTSFreeMemory(buffer)
    return {'thread_desktop_receiving_input':bool(receiving.value),'session_connection_state':state,
            'session_active':state==0}


def observe():
    value={'observed_utc':datetime.now(timezone.utc).isoformat(),'ready':False,
           'scope':'Current thread input desktop and current local session only; observation is not an action guarantee.'}
    if os.name!='nt':return {**value,'reason':'此桌面操作檢查目前僅支援 Windows。','known':False}
    try:
        actual=_windows_observation();ready=actual['thread_desktop_receiving_input'] and actual['session_active']
        return {**value,**actual,'known':True,'ready':ready,
                'reason':'目前桌面可接收輸入。' if ready else '目前桌面無法接收輸入，或工作階段已中斷；請解鎖或恢復連線後再接續。'}
    except Exception as exc:
        return {**value,'known':False,'reason':'無法確認目前桌面可接收輸入，尚未派發操作。','error':str(exc)}


def install(runtime):
    """Qt extension only; refuse unavailable native dispatch, without retries.

    Does not switch desktops, unlock, wait unattended, or authorize shell code.
    Browser DOM/file/network tools are outside this specific native-input guard.
    """
    missing=NATIVE_TOOLS-set(runtime.TOOL_REGISTRY)
    if missing:raise RuntimeError('Missing native tool registrations: '+', '.join(sorted(missing)))
    for name in sorted(NATIVE_TOOLS):
        spec=runtime.TOOL_REGISTRY[name]
        if getattr(spec.handler,'_crossgen_input_guard',False) is True:continue
        def wrap(handler):
            @functools.wraps(handler)
            def guarded(ctx,*args,**kwargs):
                observation=observe()
                if observation.get('ready') is not True:
                    return runtime.ToolResult(False,error=observation['reason'],terminal=True,
                                              evidence={'native_dispatch_sent':False,'desktop_session':observation})
                return handler(ctx,*args,**kwargs)
            guarded._crossgen_input_guard=True
            return guarded
        original=spec.handler
        guarded_handler=wrap(original)
        # Production ToolSpec is frozen; replace its registry entry instead of
        # assigning a field. Mutable fixture specs remain supported.
        from dataclasses import is_dataclass, replace
        if is_dataclass(spec):
            runtime.TOOL_REGISTRY[name]=replace(spec,handler=guarded_handler)
        else:
            spec.handler=guarded_handler
        # Composite native tools can call a handler directly after waiting for
        # model output (VISION_CLICK -> tool_mouse_click). Guard that entry too.
        function_name=getattr(original,'__name__',None)
        if isinstance(function_name,str) and getattr(runtime,function_name,None) is original:
            setattr(runtime,function_name,guarded_handler)
