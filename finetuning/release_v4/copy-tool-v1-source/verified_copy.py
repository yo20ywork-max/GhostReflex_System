"""Byte-preserving, cancellable copy into a new file; no model-generated content."""
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

CHUNK = 1024 * 1024


class CopyCancelled(RuntimeError):
    pass


class CopyUncertain(RuntimeError):
    """The destination was published, but a later observation could not verify it."""


def _check_cancel(event):
    if event is not None and event.is_set(): raise CopyCancelled('複製已取消，尚未建立目的檔。')


def _hash(stream, cancel=None):
    digest, count = hashlib.sha256(), 0
    while True:
        _check_cancel(cancel)
        chunk = stream.read(CHUNK)
        if not chunk: break
        digest.update(chunk); count += len(chunk)
    return digest.hexdigest(), count


def _version(value):
    # Python 3.12 on Windows can report different deprecated st_ctime values
    # for fstat versus stat. Use the explicit creation time there.
    change_time = getattr(value,'st_birthtime_ns',None) if os.name == 'nt' else value.st_ctime_ns
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, change_time)


def _publish(temporary, target):
    # Windows rename refuses an existing destination (also works on filesystems
    # without hard links). POSIX rename can overwrite, so use exclusive link.
    if os.name == 'nt': os.rename(temporary, target)
    else: os.link(temporary, target)


def copy_verified(source, destination, *, workspace, if_exists='error', cancel=None):
    """Verify bytes before publication; never overwrite an existing destination.

    This proves a file operation at observation time, not the whole user task.
    Byte content is preserved; filesystem metadata/ACLs are not cloned.
    """
    if if_exists not in ('error', 'skip'): raise ValueError('if_exists 必須是 error 或 skip。')
    _check_cancel(cancel)
    root = Path(workspace).resolve(strict=True)
    def inside(value):
        path = Path(value)
        if not path.is_absolute(): path = root/path
        resolved = path.resolve()
        if not resolved.is_relative_to(root): raise ValueError('檔案路徑超出工作區。')
        return resolved
    target = inside(destination)
    def existing():
        if not target.is_file(): raise FileExistsError('目的路徑已存在且不是一般檔案。')
        if if_exists == 'error': raise FileExistsError('目的檔已存在，未覆寫。')
        return {'copied':False,'skipped_existing':True,'destination':str(target),
                'source_read':False,'content_verified':False,'whole_task_verified':False}
    # Conditional skip must not inspect/read the source when the destination exists.
    if os.path.lexists(target): return existing()
    original = inside(source)
    if original == target: raise ValueError('來源與目的檔不能相同。')
    if not target.parent.is_dir(): raise FileNotFoundError('目的資料夾尚未建立。')
    temporary, owned_inode, committed = None, None, False
    try:
        with original.open('rb') as incoming:
            before = os.fstat(incoming.fileno())
            if not stat.S_ISREG(before.st_mode): raise ValueError('來源必須是一般檔案。')
            if shutil.disk_usage(target.parent).free < before.st_size + CHUNK:
                raise OSError('目的磁碟空間不足，尚未建立目的檔。')
            descriptor, name = tempfile.mkstemp(prefix='.crossgen-copy-', suffix='.part', dir=target.parent)
            temporary = Path(name)
            owned = os.fstat(descriptor); owned_inode = (owned.st_dev, owned.st_ino)
            copied_hash, count = hashlib.sha256(), 0
            with os.fdopen(descriptor, 'wb') as outgoing:
                while True:
                    _check_cancel(cancel)
                    chunk = incoming.read(CHUNK)
                    if not chunk: break
                    outgoing.write(chunk);copied_hash.update(chunk);count += len(chunk)
                outgoing.flush();os.fsync(outgoing.fileno())
            incoming.seek(0)
            source_hash, source_count = _hash(incoming, cancel)
            if (_version(before) != _version(os.fstat(incoming.fileno())) or
                    _version(before) != _version(original.stat()) or
                    source_hash != copied_hash.hexdigest() or count != source_count or count != before.st_size):
                raise RuntimeError('來源在複製期間有變化，未建立目的檔。')
        with temporary.open('rb') as check:
            temp_stat = os.fstat(check.fileno())
            if (temp_stat.st_dev,temp_stat.st_ino) != owned_inode: raise RuntimeError('暫存檔身分改變。')
            if _hash(check, cancel) != (source_hash,count): raise RuntimeError('暫存內容未通過讀回核對。')
        _check_cancel(cancel)
        # Publish only a complete verified file, without replacing a destination
        # that another process created in the meantime.
        try: _publish(temporary, target)
        except FileExistsError: return existing()
        committed = True
        try:
            with target.open('rb') as check:
                if _hash(check) != (source_hash,count): raise CopyUncertain('目的檔已建立，但讀回內容不符；請重新檢查。')
        except OSError as exc:
            raise CopyUncertain('目的檔已建立，但讀回失敗；不能宣稱核對完成。') from exc
        return {'copied':True,'skipped_existing':False,'source':str(original),'destination':str(target),
                'bytes':count,'sha256':source_hash,'source_read':True,'content_verified':True,
                'destination_readback_verified':True,'whole_task_verified':False,
                'cancel_requested_after_commit':bool(cancel is not None and cancel.is_set())}
    finally:
        if temporary is not None and temporary.exists():
            value = temporary.stat()
            if (value.st_dev,value.st_ino) == owned_inode:
                try: temporary.unlink()
                except OSError as exc:
                    if committed: raise CopyUncertain(f'目的檔已建立，但暫存檔清理失敗：{temporary}') from exc
                    raise RuntimeError(f'複製未完成，暫存檔清理失敗：{temporary}') from exc


def register(runtime):
    """Explicit catalog extension. Call before constructing the Planner."""
    name = 'COPY_FILE_VERIFIED'
    if name in runtime.TOOL_REGISTRY:
        existing = runtime.TOOL_REGISTRY[name].handler
        if existing.__module__ == __name__: return existing
        raise RuntimeError('Verified copy tool name conflicts with another handler')
    schema = runtime.object_schema({'source':{'type':'string'},'destination':{'type':'string'},
                                    'if_exists':{'type':'string','enum':['error','skip'],'default':'error'}},
                                   required=('source','destination'))
    @runtime.tool(name, '將工作區內一個檔案原樣複製成新檔，直接傳遞位元組並讀回核對SHA256，不需把全文填入參數。'
                  '不覆寫既有檔案；只有使用者要求已存在就略過時才用if_exists=skip。目的資料夾須先存在。'
                  '回傳copied/略過、雜湊與讀回結果，僅證明本次檔案操作，不代表整個任務完成。', schema, risk='high')
    def handler(ctx, source, destination, if_exists='error'):
        try:
            result = copy_verified(source,destination,workspace=ctx.settings.workspace,if_exists=if_exists,cancel=getattr(ctx,'cancel_event',None))
            return runtime.ToolResult(True,output=result,verified=True,evidence={'operation':'verified_byte_copy',**result})
        except CopyUncertain as exc:
            return runtime.ToolResult(False,error=str(exc),terminal=True,evidence={'destination_may_exist':True,'whole_task_verified':False})
        except Exception as exc:
            return runtime.ToolResult(False,error=str(exc),terminal=isinstance(exc,CopyCancelled))
    return handler
