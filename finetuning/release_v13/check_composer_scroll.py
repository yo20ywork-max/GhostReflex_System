"""Actual offscreen Qt long-input interaction, with the product engine disabled."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


INTERACTION = '''
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
literal = '  原始需求開始\\n\\t' + '\\n'.join(f'{i:03d} 保留台灣繁體、空白及原文 {{step:44.output}}。' for i in range(120)) + '\\n  需求結束𠮷😀  '
composer = window.findChild(QObject, 'composer')
composer.setProperty('text', literal)
composer.forceActiveFocus()
def cursor_visible():
    viewport = window.findChild(QObject, 'composerViewport') or composer
    bounds = composer.property('cursorRectangle')
    position = composer.mapToScene(QPointF(bounds.x(), bounds.y()))
    origin = viewport.mapToScene(QPointF(0, 0))
    return (origin.y() - 1 <= position.y() and
            position.y() + bounds.height() <= origin.y() + viewport.height() + 1)
QTest.keyClick(window, Qt.Key_End, Qt.ControlModifier)
QTest.qWait(40)
end_visible = cursor_visible()
end_position = composer.property('cursorPosition')
QTest.keyClick(window, Qt.Key_Home, Qt.ControlModifier)
QTest.qWait(40)
start_visible = cursor_visible()
start_position = composer.property('cursorPosition')
QTest.keyClick(window, Qt.Key_End, Qt.ControlModifier)
QTest.qWait(40)
QTest.keyClick(window, Qt.Key_Return, Qt.ControlModifier)
preserved = bridge.detail == literal and composer.property('text') == literal
no_engine = bridge.state == 'blocked' and bridge._service is None
utf16_units = len(literal.encode('utf-16-le')) // 2
passed = end_visible and start_visible and start_position == 0 and end_position == utf16_units and preserved and no_engine
interaction.update(checked=True, passed=passed, long_input_characters=len(literal),
                   end_cursor_visible=end_visible, start_cursor_visible=start_visible,
                   end_cursor_position=end_position, expected_utf16_units=utf16_units,
                   start_cursor_position=start_position, exact_input_preserved=preserved,
                   computer_engine_not_initialized=no_engine)
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--width', type=int, default=1180)
    parser.add_argument('--height', type=int, default=820)
    parser.add_argument('--dark', action='store_true')
    args = parser.parse_args()
    if Path(args.output).name != args.output or not args.output.endswith('.png'):
        raise ValueError('Use a new PNG filename')
    output = R / 'ui-composer' / args.output
    output.parent.mkdir(exist_ok=True)
    if output.exists() or output.with_suffix('.json').exists():
        raise FileExistsError(output)
    app_path = ROOT / 'desktop_ui/app.py'
    qml_path = ROOT / 'desktop_ui/Main.qml'
    sources = {str(p.relative_to(ROOT)): sha(p) for p in (app_path, qml_path, ROOT / 'desktop_ui/steps.py')}
    tree = ast.parse(app_path.read_text(encoding='utf8'))
    targets = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'interact']
    assert len(targets) == 1
    targets[0].body = ast.parse(INTERACTION).body
    sys.argv = [str(app_path), '--render', str(output), '--interaction-check',
                '--width', str(args.width), '--height', str(args.height)] + (['--dark'] if args.dark else [])
    namespace = {'__name__': 'crossgen_composer_qa', '__file__': str(app_path)}
    exec(compile(ast.fix_missing_locations(tree), str(app_path), 'exec'), namespace)
    status = namespace['main']()
    assert all(sha(ROOT / name) == digest for name, digest in sources.items())
    receipt = json.loads(output.with_suffix('.json').read_text(encoding='utf8'))
    receipt.update(sources=sources, qa_script_sha256=sha(Path(__file__)), image_sha256=sha(output),
                   interaction_override_only=True, engine_started=False)
    output.with_suffix('.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'output': str(output), 'interaction': receipt['interaction'], 'qml_warnings': receipt['qml_warnings']}))
    return 0 if status == 0 and receipt['interaction']['passed'] and not receipt['qml_warnings'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
