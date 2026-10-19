#!/usr/bin/env python3
"""Proves tools/check.py can see what it checks: in a throwaway copy of this tree, committed as the base, each rule is
broken in turn and the check must answer FOUND on that rule's own line. The unbroken copy must answer CLEAR, and a
base that cannot be read must answer UNEVALUABLE.

    python3 tools/prove_check.py      exit 0 when every case answered as it must, 1 otherwise
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(cwd, *args):
    subprocess.run(['git', '-C', cwd, '-c', 'user.name=prove', '-c', 'user.email=prove@example.invalid'] + list(args),
                   check=True, capture_output=True)


def fresh(tmp):
    """A copy of the tree with the base committed; returns its path and the base commit."""
    dst = os.path.join(tmp, 'copy')
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns('.git', '__pycache__'))
    git(dst, 'init', '-q', '-b', 'develop')
    git(dst, 'add', '-A')
    git(dst, 'commit', '-q', '-m', 'base')
    base = subprocess.run(['git', '-C', dst, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    return dst, base


def edit_json(path, fn):
    data = json.load(open(path, encoding='utf-8'))
    fn(data)
    json.dump(data, open(path, 'w', encoding='utf-8'), indent=2)


def flip_last_byte(path):
    b = bytearray(open(path, 'rb').read())
    b[-1] ^= 0x01
    open(path, 'wb').write(bytes(b))
    return hashlib.sha256(bytes(b)).hexdigest()


def check(dst, against):
    out = subprocess.run([sys.executable, os.path.join(dst, 'tools', 'check.py'), '--against', against],
                         capture_output=True, text=True)
    return out.returncode, out.stdout


def mutate_kinds(d):
    edit_json(os.path.join(d, 'sounds.json'), lambda m: m['sounds'].pop('bell'))


def mutate_entries(d):
    edit_json(os.path.join(d, 'sounds.json'), lambda m: m['sounds']['ring'].pop('licence'))


def mutate_sources(d):
    flip_last_byte(os.path.join(d, 'sources', 'task.wav'))


def mutate_dist_missing(d):
    os.remove(os.path.join(d, 'dist', 'web', 'mail.m4a'))


def mutate_dist_too_long(d):
    edit_json(os.path.join(d, 'dist', 'build.json'), lambda b: b['files']['ios/ring.caf'].update(durationMs=31000))


def mutate_sound_without_source(d):
    edit_json(os.path.join(d, 'sounds.json'), lambda m: m['sounds']['ring'].update(sound=2))


def mutate_source_without_sound(d):
    sha = flip_last_byte(os.path.join(d, 'sources', 'message.wav'))
    edit_json(os.path.join(d, 'sounds.json'), lambda m: m['sounds']['message'].update(sha256=sha))


def mutate_reencode_without_build(d):
    sha = flip_last_byte(os.path.join(d, 'dist', 'android', 'raw', 'visitor.ogg'))
    edit_json(os.path.join(d, 'dist', 'build.json'), lambda b: b['files']['android/raw/visitor.ogg'].update(sha256=sha))


CASES = [
    ('kinds', mutate_kinds),
    ('entries', mutate_entries),
    ('sources', mutate_sources),
    ('dist', mutate_dist_missing),
    ('dist', mutate_dist_too_long),
    ('versions', mutate_sound_without_source),
    ('versions', mutate_source_without_sound),
    ('versions', mutate_reencode_without_build),
]


def main():
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        d, base = fresh(tmp)
        rc, out = check(d, base)
        ok = rc == 0 and 'FOUND' not in out
        print('%s  control: the unbroken copy answers CLEAR (exit %d)' % ('ok  ' if ok else 'FAIL', rc))
        failed += not ok
        rc, out = check(d, 'no-such-ref')
        ok = rc == 2 and 'UNEVALUABLE' in out
        print('%s  control: a base that cannot be read answers UNEVALUABLE (exit %d)' % ('ok  ' if ok else 'FAIL', rc))
        failed += not ok
        for rule, mutate in CASES:
            d, base = fresh(tmp)
            mutate(d)
            rc, out = check(d, base)
            line = next((l for l in out.splitlines() if l.split()[1:2] == [rule]), '')
            ok = rc == 1 and line.startswith('FOUND')
            print('%s  %s: %s answers FOUND on its own line (exit %d)%s' % (
                'ok  ' if ok else 'FAIL', mutate.__name__, rule, rc, '' if ok else ' -- ' + (line or out.strip()[:200])))
            failed += not ok
    print('%d of %d cases answered as they must' % (len(CASES) + 2 - failed, len(CASES) + 2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
