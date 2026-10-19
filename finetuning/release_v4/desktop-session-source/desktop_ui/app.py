"""Qt Quick shell; preview rendering never initializes the computer-use engine."""
import argparse,json,os,sys,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--render',type=Path);parser.add_argument('--width',type=int,default=1180);parser.add_argument('--height',type=int,default=820);parser.add_argument('--development',action='store_true');parser.add_argument('--interaction-check',action='store_true');parser.add_argument('--history-preview',action='store_true');parser.add_argument('--progress-check',action='store_true');parser.add_argument('--voice-check',action='store_true');parser.add_argument('--dark',action='store_true');args=parser.parse_args()
    if args.interaction_check and not args.render:parser.error('--interaction-check requires offscreen --render')
    if args.history_preview and (not args.render or args.interaction_check):parser.error('--history-preview requires offscreen --render without composer interaction')
    if args.progress_check and not args.history_preview:parser.error('--progress-check requires --history-preview')
    if args.voice_check and (not args.render or args.history_preview or args.interaction_check):parser.error('--voice-check requires its own offscreen render')
    began=time.perf_counter()
    os.environ['QT_QUICK_CONTROLS_STYLE']='Basic'
    if args.render:
        os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_QUICK_BACKEND']='software'
    from PySide6.QtCore import QObject,Signal,Slot,Property,QUrl,QTimer
    from PySide6.QtGui import QGuiApplication,QFontDatabase
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from desktop_ui.store import TaskStore
    from desktop_ui.dialogs import DialogBroker
    from desktop_ui.steps import StepListModel
    from desktop_ui.progress import completed_progress,display_detail
    from desktop_ui.voice_session import run_voice
    from desktop_ui.speech import SpeechCancelled
    app=QGuiApplication(sys.argv[:1]);app.setApplicationName('CrossGen-AGI-μ');app.setOrganizationName('跨世代媒體科技股份有限公司')
    # The offscreen plugin does not enumerate Windows fonts. Load the host fonts
    # explicitly for rendering, without copying or distributing font files.
    if args.render:
        for name in ['msjh.ttc','msjhbd.ttc','segoeui.ttf','seguisb.ttf']:
            path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
            if path.is_file():QFontDatabase.addApplicationFont(str(path))

    class Bridge(QObject):
        changed=Signal();taskResult=Signal(str,object);engineReady=Signal(object);engineFailed=Signal(str);toolProgress=Signal(object)
        questionQueued=Signal(object);dialogRequested=Signal(str,str,str,bool);dialogClosed=Signal()
        voiceEvent=Signal(str,object);voiceTextReady=Signal(str)
        def __init__(self):
            super().__init__();self._store=None if args.render else TaskStore(ROOT/'workspace_state/tasks.sqlite3')
            self._tasks=self._store.list() if self._store else [];self._service=None;self._loading=False;self._active='';self._detail='';self._result='';self._state='idle';self._engine='介面預覽' if args.render else '尚未啟動';self._pending=[];self._dialog_event=None;self._dialog_answer=None;self._steps=StepListModel(self)
            self.taskResult.connect(self.done);self.engineReady.connect(self.ready);self.engineFailed.connect(self.failed)
            self.toolProgress.connect(self.progress)
            self._dialogs=DialogBroker();self.questionQueued.connect(self.showQuestion)
            self._closing=False
            self._voice_id='';self._voice_state='idle';self._voice_message='';self._voice_thread=None
            self._voice_stop=threading.Event();self._voice_cancel=threading.Event();self._voice_runner=run_voice
            self.voiceEvent.connect(self.voiceUpdate)
            self._dark=args.dark or (self._store.preference('dark',False) if self._store else False)
        @Property('QVariantList',notify=changed)
        def tasks(self):return self._tasks
        @Property(QObject,constant=True)
        def steps(self):return self._steps
        @Property(str,notify=changed)
        def state(self):return self._state
        @Property(str,notify=changed)
        def detail(self):return self._detail
        @Property(str,notify=changed)
        def result(self):return self._result
        @Property(str,notify=changed)
        def engine(self):return self._engine
        @Property(bool,notify=changed)
        def busy(self):return bool(self._active or self._loading or self._voice_id)
        @Property(str,notify=changed)
        def voiceState(self):return self._voice_state
        @Property(str,notify=changed)
        def voiceMessage(self):return self._voice_message
        @Slot()
        def startVoice(self):
            if self.busy or self._closing:return
            if args.render and not args.voice_check:
                self._voice_message='離線預覽不會開啟麥克風。';self.changed.emit();return
            model_dir=ROOT/'models/asr/faster-whisper-small'
            if not args.voice_check and not (model_dir/'model.bin').is_file():
                self._voice_state='failed';self._voice_message='語音模型尚未安裝，請先完成模型設定。';self.changed.emit();return
            token=uuid.uuid4().hex;self._voice_id=token;self._voice_state='preparing';self._voice_message='正在準備麥克風…'
            stop,cancel=threading.Event(),threading.Event();self._voice_stop=stop;self._voice_cancel=cancel
            runner=self._voice_runner
            def work():
                try:
                    result=runner(model_dir,stop,cancel,lambda state:None if self._closing else self.voiceEvent.emit(token,{'state':state}))
                    event={'state':'done','text':result['text']}
                except SpeechCancelled:event={'state':'cancelled'}
                except Exception as exc:event={'state':'failed','message':str(exc).splitlines()[-1][:300] if str(exc) else '語音輸入未完成。'}
                if not self._closing:self.voiceEvent.emit(token,event)
            self._voice_thread=threading.Thread(target=work,daemon=True,name='CrossGenVoice');self._voice_thread.start();self.changed.emit()
        @Slot()
        def stopVoice(self):
            if self._voice_id and self._voice_state=='recording':
                self._voice_stop.set();self._voice_state='transcribing';self._voice_message='錄音已停止，正在辨識…';self.changed.emit()
        @Slot()
        def cancelVoice(self):
            if self._voice_id:
                self._voice_cancel.set();self._voice_state='cancelling';self._voice_message='正在取消語音輸入…';self.changed.emit()
        @Slot(str,object)
        def voiceUpdate(self,token,event):
            if self._closing or token!=self._voice_id:return
            state=event['state']
            insert=''
            if self._voice_cancel.is_set():
                if state not in ('done','failed','cancelled'):return
                state='cancelled'
            if state in ('done','failed','cancelled'):
                self._voice_id='';self._voice_state=state
                if state=='done':
                    text=event.get('text','')
                    self._voice_message='語音已加入輸入框。' if text.strip() else '沒有辨識到語音，請再試一次。'
                    if text.strip():insert=text
                elif state=='cancelled':self._voice_message='已取消語音輸入，未加入辨識文字。'
                else:self._voice_message=event.get('message','語音輸入未完成，請確認麥克風。')
            else:
                self._voice_state=state;self._voice_message='正在錄音，完成後按「停止錄音」。' if state=='recording' else '正在辨識語音…'
            self.changed.emit()
            if insert:self.voiceTextReady.emit(insert)
        @Property(bool,constant=True)
        def development(self):return args.development
        @Property(bool,notify=changed)
        def darkMode(self):return self._dark
        @Slot()
        def toggleTheme(self):
            self._dark=not self._dark
            if self._store:self._store.set_preference('dark',self._dark)
            self.changed.emit()
        def refresh(self):
            if self._store:self._tasks=self._store.list()
            self.changed.emit()
        @Slot(str)
        def selectTask(self,task_id):
            for task in self._tasks:
                if task['id']==task_id:
                    self._detail=task['prompt'];self._result=task['result'];self._state=task['status']
                    self._steps.replace([{'label':f"步驟 {x['step_id']}",'status':'結果待核對' if x.get('outcome_recorded') is False else '工具已回應' if x['ok'] else '步驟未成功','detail':display_detail(x),'full':not x.get('evidence_summary',False)} for x in (self._store.history(task_id) if self._store else [])])
                    self.changed.emit();return
        @Slot()
        def newTask(self):
            if not self.busy:self._detail='';self._result='';self._steps.clear();self._state='idle';self.changed.emit()
        @Slot(str)
        def submit(self,prompt):
            if not prompt.strip() or self.busy:return
            self._detail=prompt;self._result='';self._steps.clear()
            if args.render:
                self._state='blocked';self._result='這是離線介面預覽，不會操作電腦。';self.changed.emit();return
            task_id=self._store.add(prompt)
            if not args.development:
                self._state='blocked';self._result='目前仍在發布驗收階段，自動操作尚未開放。';self._store.update(task_id,'blocked',self._result);self.refresh();return
            self._active=task_id;self._state='queued';self._pending=[(task_id,prompt)];self.refresh()
            self._dialogs.begin_task()
            if self._service:self.dispatch()
            elif not self._loading:
                self._loading=True;self._engine='正在載入引擎';self.changed.emit()
                threading.Thread(target=self.load_engine,daemon=True,name='CrossGenSetup').start()
        def load_engine(self):
            try:
                import run_daemon as runtime
                from verified_copy import register as register_verified_copy
                register_verified_copy(runtime)
                from desktop_session import install as install_desktop_guard
                install_desktop_guard(runtime)
                bridge=self
                original_log=runtime.write_event
                def forward(settings,event,payload):
                    original_log(settings,event,payload)
                    if event=='tool_result':bridge.toolProgress.emit(completed_progress(settings.workspace,payload))
                runtime.write_event=forward
                class Dialogs:
                    def bind(self,*_):pass
                    def ask_text(self,title,prompt,default=''):return bridge.ask(title,prompt,False)
                    def confirm(self,title,prompt):return bridge.ask(title,prompt,True)=='yes'
                runtime.UI=Dialogs();runtime.APP_NAME='CrossGen-AGI-μ'
                service=runtime.AgentService(runtime.Settings.from_env())
                service.start()
                if not service.ready_event.wait(180):
                    service.stop();raise TimeoutError('引擎初始化逾時，尚未執行任何任務。')
                if service.startup_error:
                    service.stop();raise RuntimeError(service.startup_error)
                if self._closing:service.stop()
                else:self.engineReady.emit(service)
            except Exception as exc:self.engineFailed.emit(str(exc))
        def ask(self,title,prompt,confirm):
            request=self._dialogs.request(title,prompt,confirm)
            if request is None:return None
            self.questionQueued.emit(request);request.ready.wait();return request.answer
        @Slot(object)
        def showQuestion(self,request):
            if self._dialogs.is_pending(request.token):
                self.dialogRequested.emit(request.token,request.title,request.prompt,request.confirmation)
        @Slot(str,str)
        def answer(self,token,value):
            if self._dialogs.resolve(token,value):self.dialogClosed.emit()
        @Slot(object)
        def ready(self,service):
            if self._closing:service.stop();return
            self._loading=False;self._service=service;self._engine='引擎已載入';self.dispatch();self.changed.emit()
        @Slot(str)
        def failed(self,error):
            self._loading=False;self._engine='引擎未能啟動';self._result=error;self._state='failed'
            if self._active:self._store.update(self._active,'failed',error)
            self._active='';self._pending=[];self.refresh()
        def dispatch(self):
            if not self._pending:return
            task_id,prompt=self._pending.pop(0);self._state='running';self._store.update(task_id,'running');self.refresh()
            try:self._service.submit(prompt,lambda result:self.taskResult.emit(task_id,result),request_id=task_id)
            except Exception as exc:self.failed(str(exc))
        @Slot(object)
        def progress(self,event):
            if not self._active or event.get('request_id')!=self._active:return
            self._store.add_event(self._active,{**event,'evidence_summary':event.get('evidence_summary',True)})
            self._steps.append({'label':f"步驟 {event['step_id']} · 第 {event['attempt']} 次",'status':'工具已回應' if event['ok'] else '步驟未成功','detail':display_detail(event),'full':not event.get('evidence_summary',True)})
            self.changed.emit()
        @Slot(str,object)
        def done(self,task_id,result):
            self._store.update(task_id,result.status,result.message,result.history)
            if task_id==self._active:
                self._state=result.status;self._result=result.message;self._active=''
            self.refresh()
        @Slot()
        def cancel(self):
            self.cancelVoice()
            if self._pending:
                for task_id,_ in self._pending:self._store.update(task_id,'cancelled','已取消，未開始執行。')
                self._pending=[];self._active='';self._state='cancelled';self._result='已取消，未開始執行。'
            elif self._active:
                self._state='cancelling';self._result='正在停止後續步驟；目前的單一步驟結束後生效。';self._store.update(self._active,'cancelling',self._result)
                if self._service:self._service.cancel_all()
            self._dialogs.cancel();self.dialogClosed.emit();self.refresh()
        @Slot()
        def copyResult(self):app.clipboard().setText(self._result)
        def close(self):
            self._closing=True
            self.cancel()
            if self._service:self._service.stop()
            # The daemon worker may finish an in-flight step after the window closes.
            # Persisted active state is recovered as interrupted on the next launch.

    bridge=Bridge();engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('crossgen',bridge)
    errors=[];engine.warnings.connect(lambda warnings:errors.extend(w.toString() for w in warnings))
    engine.load(QUrl.fromLocalFile(str(ROOT/'desktop_ui/Main.qml')))
    if not engine.rootObjects():raise RuntimeError('QML failed to load: '+str(errors))
    window=engine.rootObjects()[0];window.setWidth(args.width);window.setHeight(args.height)
    interaction={'checked':False}
    if args.render:
        if args.voice_check:
            transcript='  不要刪除檔案\n\t只列出目錄。  '
            draft='前段|後段';expected=draft[:2]+transcript+draft[2:]
            calls=[];phase={'value':0,'started':time.monotonic()}
            def simulated_voice(model,stop,cancel,on_state):
                calls.append(len(calls)+1);number=calls[-1];on_state('recording')
                signal=stop if number==1 else cancel
                if not signal.wait(2):raise RuntimeError('QA did not stop/cancel the simulated input')
                on_state('transcribing')
                return {'text':transcript if number==1 else '取消後不應插入'}
            bridge._voice_runner=simulated_voice
            def voice_interact():
                try:
                    from PySide6.QtCore import Qt
                    from PySide6.QtTest import QTest
                    composer=window.findChild(QObject,'composer');button=window.findChild(QObject,'voiceButton')
                    if time.monotonic()-phase['started']>4:raise AssertionError('Voice UI check timed out')
                    if phase['value']==0:
                        composer.setProperty('text',draft);composer.setProperty('cursorPosition',2)
                        button.forceActiveFocus();QTest.keyClick(window,Qt.Key_Space);phase['value']=1
                    elif phase['value']==1 and bridge.voiceState=='recording':
                        button.forceActiveFocus();QTest.keyClick(window,Qt.Key_Space);phase['value']=2
                    elif phase['value']==2 and bridge.voiceState=='done':
                        if composer.property('text')!=expected:raise AssertionError('Voice insertion changed the existing draft or whitespace')
                        bridge.startVoice();phase['value']=3
                    elif phase['value']==3 and bridge.voiceState=='recording':
                        bridge.cancelVoice();phase['value']=4
                    elif phase['value']==4 and bridge.voiceState=='cancelled':
                        bridge.voiceUpdate('stale-token',{'state':'done','text':'舊工作結果'})
                        if composer.property('text')!=expected or bridge._active or bridge._service is not None:
                            raise AssertionError('Cancelled or stale voice result altered text or dispatched a task')
                        interaction.update(checked=True,passed=True,voice_input_inserted_at_cursor=True,cancelled_result_ignored=True,stale_result_ignored=True,microphone_opened=False,asr_simulated=True,computer_engine_not_initialized=True)
                        return
                    QTimer.singleShot(15,voice_interact)
                except Exception as exc:print(str(exc),file=sys.stderr,flush=True);app.exit(1)
            QTimer.singleShot(100,voice_interact)
        if args.history_preview:
            literal='  原始工具回應\n\t保留空白與換行。\n'+('離線顯示資料；不代表操作成功。'*200)
            bridge._detail='離線紀錄預覽：120個步驟';bridge._state='interrupted'
            bridge._steps.replace([{'label':f'步驟 {i+1}','status':'預覽紀錄','detail':literal} for i in range(120)]);bridge.changed.emit()
            def history_interact():
                try:
                    from PySide6.QtCore import Qt
                    from PySide6.QtTest import QTest
                    def visual(name):
                        pending=[window.contentItem()]
                        while pending:
                            item=pending.pop()
                            if item.objectName()==name:return item
                            pending.extend(item.childItems())
                        return None
                    button=visual('stepToggle-0');button.forceActiveFocus()
                    QTest.keyClick(window,Qt.Key_Space)
                    full=visual('stepFull-0')
                    if full is None or full.property('text')!=literal:raise AssertionError('Expanded detail did not preserve complete text')
                    if args.progress_check:
                        from types import SimpleNamespace
                        events=[];bridge._store=SimpleNamespace(add_event=lambda task,event:events.append((task,event)))
                        bridge._active='offline-progress-check'
                        first=visual('stepCard-0');update_started=time.perf_counter()
                        for i in range(10):
                            bridge.progress({'request_id':bridge._active,'step_id':121+i,'attempt':1,'ok':True,'output':'新到的離線紀錄\n\t原文保留'})
                        app.processEvents()
                        full=visual('stepFull-0')
                        if visual('stepCard-0') is not first or full is None or full.property('text')!=literal:
                            raise AssertionError('New progress replaced the expanded step or lost its original text')
                        bridge.changed.emit();app.processEvents()
                        if visual('stepFull-0') is not full:raise AssertionError('Unrelated state notification replaced expanded evidence')
                        if len(events)!=10:raise AssertionError('Progress evidence was not persisted exactly once')
                        if visual('stepToggle-120').property('text')!='展開摘要':raise AssertionError('Summary-only progress was labelled as a full response')
                        interaction.update(progress_updates=10,expanded_step_preserved=True,progress_update_seconds=time.perf_counter()-update_started)
                        bridge._active='';bridge._store=None;bridge.changed.emit()
                    QTest.keyClick(window,Qt.Key_Space)
                    interaction.update(checked=True,passed=True,history_rows=bridge._steps.rowCount(),expanded_detail_exact=True,computer_engine_not_initialized=True)
                except Exception as exc:print(str(exc),file=sys.stderr,flush=True);app.exit(1)
            QTimer.singleShot(100,history_interact)
        if args.interaction_check:
            def interact():
                try:
                    from PySide6.QtCore import Qt
                    from PySide6.QtTest import QTest
                    literal='  讀取 測試資料/原文.txt，保留原文\n\t不要送出或刪除。  '
                    composer=window.findChild(QObject,'composer');composer.setProperty('text',literal);composer.forceActiveFocus()
                    QTest.keyClick(window,Qt.Key_Return,Qt.ControlModifier)
                    if bridge.detail!=literal or bridge.state!='blocked' or bridge._service is not None:raise AssertionError('Composer submission did not preserve the exact text or initialized an engine')
                    interaction.update(checked=True,passed=True,exact_whitespace_preserved=True,computer_engine_not_initialized=True)
                except Exception as exc:print(str(exc),file=sys.stderr,flush=True);app.exit(1)
            QTimer.singleShot(100,interact)
        def capture():
            try:
                if (args.history_preview or args.interaction_check or args.voice_check) and not interaction['checked']:
                    QTimer.singleShot(100,capture);return
                args.render.parent.mkdir(parents=True,exist_ok=True);img=window.grabWindow()
                if img.isNull() or not img.save(str(args.render)):raise RuntimeError('Offscreen render failed')
                import psutil
                receipt={'width':img.width(),'height':img.height(),'seconds_to_render':time.perf_counter()-began,'working_set_mb':psutil.Process().memory_info().rss/1024**2,'qml_warnings':errors,'interaction':interaction,'mode':'offscreen software renderer; no model or computer action initialized','release_approved':False}
                args.render.with_suffix('.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(receipt,ensure_ascii=False),flush=True);app.quit()
            except Exception as exc:print(str(exc),file=sys.stderr,flush=True);app.exit(1)
        QTimer.singleShot(600,capture)
    else:app.aboutToQuit.connect(bridge.close)
    return app.exec()
if __name__=='__main__':raise SystemExit(main())
