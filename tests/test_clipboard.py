import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

MODULE = Path(__file__).resolve().parents[1] / 'clipboard.py'
spec = importlib.util.spec_from_file_location('clipboard_io', MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / 'state'
        self.session = Path(self.temp.name) / 'session'
        self.store = c.Store(self.base, self.session)
        self.env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def entries(self):
        return self.store.command('list')['entries']

    def test_exact_bytes_and_dedup_favorite_order(self):
        for raw, mime in [(b'  hello\r\n\n\x00 ', 'text/plain;charset=utf-8'),
                          (b'\x89PNG\r\n\x1a\n\xff\x00', 'image/png'),
                          (b'cut\nfile:///tmp/a%20b\n', c.FILE_TYPE),
                          (b'file:///tmp/a\r\n', 'text/uri-list'),
                          ('🙂'.encode(), 'text/plain'), (b' \t\n', 'text/plain')]:
            self.store.capture(raw, mime)
            entry = self.entries()[0]
            self.assertEqual((self.base / entry['id']).read_bytes(), raw)
            self.assertEqual(entry['mime'], mime)
        first = self.entries()[0]
        self.store.command('favorite', first['id'])
        self.store.capture(b'other', 'text/plain')
        self.store.capture(b' \t\n', 'text/plain')
        self.assertEqual(self.entries()[0]['id'], first['id'])
        self.assertTrue(self.entries()[0]['favorite'])
        self.assertEqual(len(self.entries()), 7)

    def test_retention_deletion_clear_and_private_files(self):
        self.store.capture(b'favorite', 'text/plain')
        favorite = self.entries()[0]['id']
        self.store.command('favorite', favorite)
        self.store.command('settings', '{"retention":1}')
        self.store.capture(b'old', 'text/plain')
        old = self.entries()[0]['id']
        self.store.capture(b'new', 'text/plain')
        self.assertFalse((self.base / old).exists())
        self.assertEqual(len(self.entries()), 2)
        self.assertEqual(self.base.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.base / favorite).stat().st_mode & 0o777, 0o600)
        self.store.command('delete', favorite)
        self.assertFalse((self.base / favorite).exists())
        self.store.command('clear')
        self.assertEqual(self.entries(), [])
        self.assertFalse(any(len(p.name) == 64 for p in self.base.iterdir()))

    def test_incognito_sensitive_session_boundaries(self):
        self.store.capture(b'persistent', 'text/plain')
        self.store.command('settings', '{"incognito":true}')
        self.store.capture(b'private', 'text/plain')
        self.assertEqual(len(self.entries()), 1)
        self.store.command('settings', '{"incognito":false,"sessionOnly":true}')
        self.store.capture(b'session', 'text/plain')
        self.store.capture(b'secret', 'text/plain', sensitive=True)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(len(self.store.load(self.base)), 1)
        self.assertNotIn('session', (self.base / 'history.json').read_text())
        self.store.command('settings', '{"sessionOnly":false}')
        self.assertEqual(self.entries()[0]['preview'], 'persistent')
        self.assertEqual(self.store.load(self.session), [])

    def test_optional_defaults_and_independent_settings(self):
        initial = self.store.command('init')['settings']
        for key in ('colors', 'languages', 'filters', 'previews', 'paste'):
            self.assertFalse(initial[key])
        for key in ('colors', 'languages', 'filters'):
            self.store.command('settings', json.dumps({key: True}))
            self.assertTrue(self.store.command('list')['settings'][key])
        self.assertTrue(all(self.store.command('list')['settings'][key] for key in ('colors', 'languages', 'filters')))
        with self.assertRaises(ValueError):
            self.store.command('settings', '{"retention":"bad"}')

    def test_malformed_history_is_never_overwritten(self):
        (self.base / 'history.json').write_text('private corrupt history')
        with self.assertRaises(json.JSONDecodeError):
            self.store.command('clear')
        self.assertEqual((self.base / 'history.json').read_text(), 'private corrupt history')

    def test_no_write_loop_on_list(self):
        self.store.command('init')
        path = self.base / 'history.json'
        before = path.stat().st_mtime_ns
        self.store.command('list')
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_colors_alpha_and_invalid(self):
        for value, expected in [('#f008', [1, 0, 0, 136/255]),
                                ('#ff000080', [1, 0, 0, 128/255]),
                                ('rgba(255, 0, 0, 0.5)', [1, 0, 0, .5]),
                                ('rgb(100% 0% 0% / 50%)', [1, 0, 0, .5]),
                                ('hsl(0 100% 50% / 25%)', [1, 0, 0, .25]),
                                ('transparent', [0, 0, 0, 0])]:
            self.assertEqual(c.color_value(value), expected, value)
        for value in ('#zzzzzz', 'rgba(999,0,0,1)', 'rgb(0 0 0 / 2)', 'ordinary prose', 'hsl(0 100 50)'):
            self.assertIsNone(c.color_value(value), value)
        original = b'  rgba(255, 0, 0, 0.5)\n'
        self.store.capture(original, 'text/plain')
        e = self.entries()[0]
        self.assertEqual(e['kind'], 'color')
        self.assertEqual((self.base / e['id']).read_bytes(), original)

    def test_code_short_prose_bounded(self):
        snippets = {'HTML/XML': '<div>Hello</div>', 'PHP': '<?php echo "hi";',
                    'CSS': '.a { color: red; }', 'JavaScript': 'const x = 1;',
                    'TypeScript': 'const x: number = 1;', 'Python': 'print("hello")',
                    'SQL': 'SELECT name FROM users;', 'Shell': '#!/bin/bash\necho hello'}
        for expected, text in snippets.items():
            self.assertEqual(c.language(text), expected, text)
        for text in ('Please call me tomorrow.', 'Hello world', 'Meet at 10:30.', 'This is a class of students.', 'Go to the store; then turn left.'):
            self.assertEqual(c.language(text), '', text)
        self.assertEqual(c.language('x' * 9000 + '\nconst y = 1;'), '')

    def test_older_metadata_backfill(self):
        self.store.capture(b'const x = 1;', 'text/plain')
        entry = self.entries()[0]
        del entry['language']
        c.atomic_json(self.base / 'history.json', [entry])
        self.assertEqual(self.entries()[0]['language'], 'JavaScript')

    def test_copy_uses_original_mime_and_bytes(self):
        raw = b'cut\nfile:///tmp/a\n'
        self.store.capture(raw, c.FILE_TYPE)
        entry = self.entries()[0]
        commands = []
        def fake_run(args, **kwargs):
            commands.append((args, kwargs['stdin'].read()))
        with patch.object(c, 'run', fake_run), patch.object(c.sys, 'argv', ['clipboard.py', 'copy', str(self.base), str(self.session), entry['id']]):
            c.main()
        self.assertEqual(commands, [(['wl-copy', '--type', c.FILE_TYPE], raw)])

    def test_preview_private_redirects_size_and_no_persistence(self):
        for url in ('file:///etc/passwd', 'http://user:pass@example.com/', 'http://127.0.0.1/'):
            with self.assertRaises(ValueError):
                c.link_title(url)
        self.store.capture(b'https://example.com/', 'text/plain')
        entry = self.entries()[0]
        result = Mock(status=200, headers={'Content-Type': 'text/html'})
        result.read.return_value = b'<title>Useful &amp; bounded</title>'
        connection = Mock()
        connection.getresponse.return_value = result
        with patch.object(c.socket, 'getaddrinfo', return_value=[(2,1,6,'',('93.184.216.34',443))]), patch('http.client.HTTPSConnection', return_value=connection):
            self.assertEqual(c.link_title('https://example.com/'), 'Useful & bounded')
            result.read.assert_called_once_with(128*1024)
            connection.close.assert_called_once()
        self.assertNotIn('title', self.entries()[0])

    def test_snapshot_sensitive_changed_offer_and_file_cut(self):
        self.store.command('init')
        result = Mock(stdout=b'text/plain\nx-special/gnome-copied-files\n')
        def payload(mime):
            return b'file:///tmp/a' if mime == 'text/plain' else b'cut\nfile:///tmp/a\n'
        with patch.dict(os.environ, {'CLIPBOARD_STATE': 'data'}), patch.object(c, 'run', return_value=result), patch.object(c, 'bounded_paste', side_effect=payload):
            c.snapshot(self.store, b'file:///tmp/a')
        self.assertEqual(self.entries()[0]['mime'], c.FILE_TYPE)
        with patch.dict(os.environ, {'CLIPBOARD_STATE': 'sensitive'}), patch.object(c, 'run') as run:
            c.snapshot(self.store, b'secret')
            run.assert_not_called()
        with patch.dict(os.environ, {'CLIPBOARD_STATE': 'data'}), patch.object(c, 'run', side_effect=[Mock(stdout=b'text/plain\n'), Mock(stdout=b'image/png\n')]), patch.object(c, 'bounded_paste', return_value=b'changed'):
            c.snapshot(self.store, b'changed')
        self.assertEqual(len(self.entries()), 1)

    def test_unsupported_malformed_and_size(self):
        self.store.capture(b'unsupported', 'application/octet-stream')
        self.assertEqual(self.entries(), [])
        with self.assertRaises(ValueError):
            self.store.capture(b'launch\nfile:///tmp/a', c.FILE_TYPE)
        with self.assertRaises(ValueError):
            self.store.capture(b'file://remote/tmp/a', 'text/uri-list')
        with patch.object(c, 'MAX_BYTES', 4):
            self.store.capture(b'oversize', 'text/plain')
        self.store.capture(b'\xff\xfe\0', 'text/plain')
        self.assertEqual(len(self.entries()), 1)
        self.assertIn('\ufffd', self.entries()[0]['preview'])



class LifecycleTests(unittest.TestCase):
    setUp = ClipboardTests.setUp
    entries = ClipboardTests.entries
    def test_session_cleanup_and_late_capture(self):
        runtime = Path(self.temp.name)
        session = runtime / 'omarchy-pano-123-abc'
        store = c.Store(self.base, session)
        store.command('settings', '{"sessionOnly":true}')
        store.capture(b'private session', 'text/plain')
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR': str(runtime)}), patch.object(c.sys, 'argv', ['clipboard.py', 'cleanup-session', str(self.base), str(session)]):
            c.main()
        self.assertFalse(session.exists())
        with self.assertRaises(ValueError):
            c.Store(self.base, session, create_session=False)
        with self.assertRaises(FileNotFoundError):
            store.capture(b'late capture', 'text/plain')
        self.assertFalse(session.exists())

    def test_clear_removes_saved_and_session_history(self):
        self.store.capture(b'saved', 'text/plain')
        self.store.command('settings', '{"sessionOnly":true}')
        self.store.capture(b'temporary', 'text/plain')
        self.store.command('clear')
        self.assertEqual(self.store.load(self.base), [])
        self.assertEqual(self.store.load(self.session), [])

    def test_capture_lock_and_concurrency(self):
        from concurrent.futures import ThreadPoolExecutor
        def add(i):
            self.store.capture(str(i).encode(), 'text/plain')
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(add, range(30)))
        self.assertEqual(len(self.entries()), 30)
        self.assertEqual(len({e['id'] for e in self.entries()}), 30)

    def test_bounded_read_timeout_and_limit(self):
        read, write = os.pipe()
        with os.fdopen(read, 'rb', buffering=0) as stream:
            try:
                with self.assertRaises(TimeoutError):
                    c.bounded_read(stream, 10, timeout=.01)
                os.write(write, b'12345678901')
                with self.assertRaises(ValueError):
                    c.bounded_read(stream, 10)
            finally:
                os.close(write)

    def test_capture_rejects_kde_cut_hint_and_mismatched_trigger(self):
        for offered, trigger, raw in [
            (b'text/plain\napplication/x-kde-cutselection\n', b'secret', b'secret'),
            (b'text/plain\nx-kde-passwordManagerHint\n', b'secret', b'secret'),
            (b'text/plain\n', b'old', b'new'),
        ]:
            with patch.dict(os.environ, {'CLIPBOARD_STATE': 'data'}), patch.object(c, 'run', return_value=Mock(stdout=offered)), patch.object(c, 'bounded_paste', return_value=raw):
                c.snapshot(self.store, trigger)
        self.assertEqual(self.entries(), [])


if __name__ == '__main__':
    unittest.main()
