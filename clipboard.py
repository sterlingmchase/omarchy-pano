#!/usr/bin/env python3
"""Short-lived clipboard I/O; QML owns the UI, JSON files own history/settings.

No database or background service. wl-paste invokes capture for each selection.
"""
import contextlib
import fcntl
import hashlib
import html.parser
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

MAX_BYTES = 32 * 1024 * 1024
PREVIEW_LIMIT = 8192
DEFAULTS = dict(colors=False, languages=False, filters=False, retention=300,
                previews=False, incognito=False, sessionOnly=False, paste=False,
                horizontal=True)
IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/bmp', 'image/tiff')
FILE_TYPE = 'x-special/gnome-copied-files'


def atomic_json(path, value):
    encoded = json.dumps(value, ensure_ascii=True)
    if path.exists() and path.read_text() == encoded:
        return
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def settings(base):
    result = DEFAULTS.copy()
    path = base / 'settings.json'
    if path.exists():
        value = json.loads(path.read_text())
        for key, default in DEFAULTS.items():
            if key in value and type(value[key]) is type(default):
                result[key] = value[key]
    result['retention'] = max(0, min(5000, result['retention']))
    return result


def capture_allowed():
    path = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'omarchy/shell.json'
    try:
        config = json.loads(path.read_text()) if path.exists() else {}
        return 'omarchy.clipboard' in config.get('disabledPlugins', [])
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def color_value(text):
    """Return explicit RGBA channels; never pass CSS's #RRGGBBAA to Qt's #AARRGGBB."""
    text = text.strip().lower()
    if text == 'transparent':
        return [0, 0, 0, 0]
    if re.fullmatch(r'#[0-9a-f]{3,4}|#[0-9a-f]{6}(?:[0-9a-f]{2})?', text):
        value = text[1:]
        if len(value) in (3, 4):
            value = ''.join(c * 2 for c in value)
        if len(value) == 6:
            value += 'ff'
        return [int(value[i:i+2], 16) / 255 for i in (0, 2, 4, 6)]
    match = re.fullmatch(r'(rgba?|hsla?)\(([^()]+)\)', text)
    if not match:
        return None
    parts = re.split(r'\s*[,/]\s*|\s+', match[2].strip())
    if len(parts) not in (3, 4):
        return None
    try:
        alpha = float(parts[3].rstrip('%')) / (100 if parts[3].endswith('%') else 1) if len(parts) == 4 else 1
        if not 0 <= alpha <= 1:
            return None
        if match[1].startswith('rgb'):
            rgb = [float(p.rstrip('%')) / (100 if p.endswith('%') else 255) for p in parts[:3]]
            return rgb + [alpha] if all(0 <= v <= 1 for v in rgb) else None
        import colorsys
        if not all(p.endswith('%') for p in parts[1:3]):
            return None
        h = float(parts[0].removesuffix('deg')) % 360 / 360
        s, light = [float(p[:-1]) / 100 for p in parts[1:3]]
        if not (0 <= s <= 1 and 0 <= light <= 1):
            return None
        return list(colorsys.hls_to_rgb(h, light, s)) + [alpha]
    except ValueError:
        return None


def language(text):
    # Conservative gates keep Pygments' short-prose guesses out of the Code filter.
    checks = (
        ('SQL', r'(?i)\bSELECT\s+[\w*.,\s]+\s+FROM\s+\w+|\bINSERT\s+INTO\s+\w+'),
        ('Shell', r'^#!\s*/(?:usr/)?bin/(?:env\s+)?(?:ba|z|fi)?sh\b'),
        ('PHP', r'<\?php\b|\$\w+\s*=.+;'),
        ('HTML/XML', r'<(?:!doctype|\?xml)\b|<([\w:-]+)(?:\s[^>]*|)>[\s\S]*</\1\s*>|<\w+\s+[^>]+/?>|<[\w:-]+\s*/>'),
        ('Python', r'(?m)^\s*(?:async\s+)?def\s+\w+\([^\n]*\)\s*(?:->[^:]+)?:|^\s*(?:from\s+[\w.]+\s+import\s+\w+|import\s+[\w.]+)\s*$|\bprint\([^\n]*\)'),
        ('TypeScript', r'\b(?:interface|type)\s+\w+\s*(?:[={])|\b(?:const|let)\s+\w+\s*:\s*[\w\[\]<>|]+\s*='),
        ('JavaScript', r'\b(?:const|let|var)\s+\w+\s*=|\bfunction\s*\w*\s*\(|\([^)]*\)\s*=>|\bconsole\.\w+\('),
        ('CSS', r'[.#]?[\w-]+\s*\{\s*[\w-]+\s*:\s*[^}]+[;}]'),
    )
    text = text[:PREVIEW_LIMIT]
    for name, pattern in checks:
        if re.search(pattern, text, re.I if name == 'HTML/XML' else 0):
            return name
    if not re.search(r'(?m)^\s*(?:#include\s*[<"]|fn\s+\w+\(|func\s+\w+\(|public\s+(?:class|static)\b|class\s+\w+.*[{:])|[;{}]\s*\n.*[;{}]', text):
        return ''
    try:
        from pygments.lexers import guess_lexer
        name = guess_lexer(text).name
        return name if name not in ('Text only', 'Text', 'HTTP') else 'Code'
    except (ImportError, ValueError):
        return 'Code'


def metadata(raw, mime):
    text = raw[:PREVIEW_LIMIT * 4].decode('utf-8', errors='replace')[:PREVIEW_LIMIT]
    result = dict(preview=text, kind='text', language='', rgba=[])
    if mime in IMAGE_TYPES:
        result.update(kind='image', preview=f'{mime} · {len(raw):,} bytes')
    elif mime in (FILE_TYPE, 'text/uri-list'):
        lines = text.splitlines()
        if mime == FILE_TYPE:
            if not lines or lines[0] not in ('copy', 'cut'):
                raise ValueError('Invalid file operation')
            operation, lines = lines[0], lines[1:]
        else:
            operation = 'reference'
        uris = [v for v in lines if v and not v.startswith('#')]
        if not uris or not all(urllib.parse.urlsplit(v).scheme == 'file' and urllib.parse.urlsplit(v).netloc in ('', 'localhost') and urllib.parse.urlsplit(v).path.startswith('/') for v in uris):
            raise ValueError('Unsupported file references')
        result.update(kind='file', preview=operation + '\n' + '\n'.join(urllib.parse.unquote(v) for v in uris))
    else:
        rgba = color_value(text) if len(raw) < 256 else None
        if rgba is not None:
            result.update(kind='color', rgba=rgba)
        elif re.fullmatch(r'https?://[^\s<>]+', text.strip()) and len(raw) < PREVIEW_LIMIT:
            result['kind'] = 'link'
        elif text.strip() and len(text) <= 80 and all(c.isspace() or ord(c) >= 0x1f000 or 0x2600 <= ord(c) <= 0x27ff or ord(c) in (0x200d, 0xfe0f, 0x20e3) or c in '#*0123456789' for c in text) and any(ord(c) >= 0x2600 for c in text):
            result['kind'] = 'emoji'
        else:
            result['language'] = language(text)
            if result['language']:
                result['kind'] = 'code'
    result['searchText'] = (result['preview'] + ' ' + result['language']).lower()
    return result


class Store:
    def __init__(self, base, session, create_session=True):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.base, 0o700)
        self.session = Path(session)
        if create_session:
            self.session.mkdir(parents=True, exist_ok=True, mode=0o700)
        elif not self.session.is_dir():
            raise ValueError("Plugin session has ended")

    @contextlib.contextmanager
    def locked(self):
        with (self.base / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def directory(self, prefs):
        return self.session if prefs['sessionOnly'] else self.base

    def load(self, directory):
        path = directory / 'history.json'
        if not path.exists():
            return []
        values = json.loads(path.read_text())
        if not isinstance(values, list):
            raise ValueError('History is not a list; left untouched')
        entries = []
        for value in values:
            if not isinstance(value, dict) or not re.fullmatch('[a-f0-9]{64}', str(value.get('id', ''))):
                raise ValueError('Invalid history entry; left untouched')
            if not isinstance(value.get('mime'), str) or not isinstance(value.get('preview'), str):
                raise ValueError('Invalid history metadata; left untouched')
            if (directory / value['id']).is_file():
                entries.append(value)
        return entries

    def save(self, directory, entries, limit):
        ordinary = 0
        kept = []
        for entry in entries:
            protected = entry.get('favorite') or entry.get('pinnedAt')
            if protected or ordinary < limit:
                kept.append(entry)
                if not protected:
                    ordinary += 1
        atomic_json(directory / 'history.json', kept)
        ids = {v['id'] for v in kept}
        for path in directory.iterdir():
            if re.fullmatch('[a-f0-9]{64}', path.name) and path.name not in ids:
                path.unlink(missing_ok=True)
        return kept

    def capture(self, raw, mime, sensitive=False):
        if sensitive or not raw or len(raw) > MAX_BYTES:
            return
        if mime not in IMAGE_TYPES + (FILE_TYPE, 'text/uri-list', 'UTF8_STRING', 'STRING') and not (mime == 'text/plain' or mime.startswith('text/plain;')):
            return
        info = metadata(raw, mime)
        with self.locked():
            prefs = settings(self.base)
            if prefs['incognito']:
                return
            directory = self.directory(prefs)
            entries = self.load(directory)
            key = hashlib.sha256(mime.encode() + b'\0' + raw).hexdigest()
            previous = next((e for e in entries if e['id'] == key), {})
            entry = dict(info, id=key, mime=mime, copiedAt=time.time(), size=len(raw), favorite=previous.get('favorite', False), pinnedAt=previous.get('pinnedAt', 0))
            fd, name = tempfile.mkstemp(dir=directory)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                os.replace(name, directory / key)
            finally:
                Path(name).unlink(missing_ok=True)
            self.save(directory, [entry] + [e for e in entries if e['id'] != key], prefs['retention'])

    def command(self, action, argument=''):
        with self.locked():
            prefs = settings(self.base)
            directory = self.directory(prefs)
            entries = self.load(directory)
            if action == 'settings':
                value = json.loads(argument)
                for key, item in value.items():
                    if key not in DEFAULTS or type(item) is not type(DEFAULTS[key]):
                        raise ValueError('Invalid setting')
                previous = prefs
                prefs = dict(prefs, **value)
                prefs['retention'] = max(0, min(5000, prefs['retention']))
                atomic_json(self.base / 'settings.json', prefs)
                if prefs['sessionOnly'] != previous['sessionOnly']:
                    # Privacy boundary: never move persistent history into a temporary session.
                    self.save(self.session, [], 0)
                directory = self.directory(prefs)
                entries = self.load(directory)
            elif action == 'delete':
                entries = [e for e in entries if e['id'] != argument]
            elif action == 'favorite':
                for entry in entries:
                    if entry['id'] == argument:
                        entry['favorite'] = not entry.get('favorite', False)
            elif action == 'pin':
                for entry in entries:
                    if entry['id'] == argument:
                        entry['pinnedAt'] = 0 if entry.get('pinnedAt') else time.time()
            elif action == 'clear':
                self.save(self.base, [], 0)
                self.save(self.session, [], 0)
                entries = []
            elif action not in ('init', 'list'):
                raise ValueError('Unknown operation')
            # Backfill older metadata in a bounded analysis without changing payloads.
            for entry in entries:
                if 'language' not in entry or entry.get('kind') not in ('text', 'code', 'color', 'image', 'link', 'file', 'emoji'):
                    with (directory / entry['id']).open('rb') as stream:
                        info = metadata(stream.read(PREVIEW_LIMIT * 4), entry['mime'])
                    entry.update(info)
            entries = self.save(directory, entries, prefs['retention'])
            return dict(settings=prefs, entries=entries, directory=str(directory), captureAllowed=capture_allowed())


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=3, stderr=subprocess.DEVNULL, **kwargs)


def snapshot(store, trigger):
    """Single watcher triggers a bounded snapshot. Recheck the offer before recording."""
    if os.environ.get('CLIPBOARD_STATE') in ('sensitive', 'nil', 'clear'):
        return
    prefs = settings(store.base)
    if prefs['incognito']:
        return
    offered = run(['wl-paste', '--list-types'], stdout=subprocess.PIPE).stdout.splitlines()
    types = [v.decode('ascii', 'replace') for v in offered]
    if 'x-kde-passwordManagerHint' in types or 'application/x-kde-cutselection' in types:
        return
    mime = next((v for v in (FILE_TYPE, 'text/uri-list', *IMAGE_TYPES, 'text/plain;charset=utf-8', 'text/plain', 'UTF8_STRING', 'STRING') if v in types), None)
    if mime is None:
        return
    # The installed wl-paste does not export CLIPBOARD_TYPE. Fetch explicitly;
    # compare offers before/after and the preferred text against the trigger.
    raw = bounded_paste(mime)
    after = run(['wl-paste', '--list-types'], stdout=subprocess.PIPE).stdout.splitlines()
    if after != offered:
        return
    plain = next((v for v in ('text/plain;charset=utf-8', 'text/plain') if v in types), None)
    if plain and bounded_paste(plain) != trigger:
        return
    store.capture(raw, mime)


def bounded_read(stream, limit, timeout=3):
    import selectors
    deadline = time.monotonic() + timeout
    data = bytearray()
    with selectors.DefaultSelector() as poll:
        poll.register(stream, selectors.EVENT_READ)
        while True:
            if time.monotonic() >= deadline or not poll.select(max(0, deadline - time.monotonic())):
                raise TimeoutError('Clipboard read timed out')
            chunk = os.read(stream.fileno(), min(65536, limit + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('Clipboard exceeds size limit')


def bounded_paste(mime):
    proc = subprocess.Popen(['wl-paste', '--no-newline', '--type', mime], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        data = bounded_read(proc.stdout, MAX_BYTES)
        proc.wait(timeout=1)
        if proc.returncode:
            raise ValueError('Clipboard read failed')
        return data
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()


class TitleParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data[:512 - len(self.title)]


def link_title(url):
    # No credentials, cookies, proxy credentials, redirects or private destinations.
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError('Unsupported preview URL')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private preview address')
    import http.client
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    connection_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    connection = connection_class(parsed.hostname, port, timeout=2)
    connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection((addresses[0][4][0], port), timeout, source_address)
    try:
        path = urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
        connection.request('GET', path, headers={'User-Agent': 'Omarchy-Pano/0.1', 'Accept': 'text/html', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
            return ''
        parser = TitleParser()
        parser.feed(response.read(128 * 1024).decode('utf-8', 'replace'))
        return ' '.join(parser.title.split())[:512]
    finally:
        connection.close()



def main():
    os.umask(0o077)
    action, base, session, *args = sys.argv[1:]
    if action == 'cleanup-session':
        runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
        target = Path(session)
        if target.parent != runtime or not re.fullmatch(r'omarchy-pano-[0-9]+-[a-z0-9]+', target.name) or target.is_symlink():
            raise ValueError('Invalid session directory')
        import shutil
        with (Path(base) / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            shutil.rmtree(target, ignore_errors=True)
        return
    store = Store(base, session, create_session=action == 'init')
    if action == 'capture':
        if not capture_allowed() or settings(store.base)['incognito'] or os.environ.get('CLIPBOARD_STATE') in ('sensitive', 'nil', 'clear'):
            return
        # Drain without retaining arbitrarily large or sensitive input.
        raw = bounded_read(sys.stdin.buffer, MAX_BYTES)
        snapshot(store, raw)
        print('{}')
    elif action == 'copy':
        with store.locked():
            prefs = settings(store.base)
            directory = store.directory(prefs)
            entry = next((e for e in store.load(directory) if e['id'] == args[0]), None)
            if not entry:
                raise ValueError('Entry was removed')
            with (directory / entry['id']).open('rb') as stream:
                run(['wl-copy', '--type', entry['mime']], stdin=stream)
        if len(args) > 1 and args[1] == 'paste':
            # QML waits until its layer surface is unmapped before invoking this.
            time.sleep(0.15)
            run(['wtype', '-M', 'shift', '-k', 'Insert', '-m', 'shift'])
    elif action == 'preview':
        with store.locked():
            prefs = settings(store.base)
            entry = next((e for e in store.load(store.directory(prefs)) if e['id'] == args[0]), None)
            if not prefs['previews'] or not entry or entry['kind'] != 'link':
                return
            url = entry['preview'].strip()
        print(json.dumps(dict(id=entry['id'], title=link_title(url))))
    else:
        print(json.dumps(store.command(action, args[0] if args else '')))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Clipboard values, URLs, paths and subprocess output must never reach logs.
        print(json.dumps({'error': 'Clipboard operation failed; check permissions, storage or format.'}))
        sys.exit(1)
