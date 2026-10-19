#!/usr/bin/env python3
"""Checks the sound package. Prints one line per rule and exits 0 CLEAR, 1 FOUND, 2 UNEVALUABLE (a rule that could
not look is never folded into one that looked and found nothing).

    python3 tools/check.py [--against <git ref> | --against none]

Rules:
  kinds      sounds.json holds exactly the six kinds: ring, message, visitor, task, mail, bell.
  entries    each entry names a `sound` and a `build` (integers from 1), a source, its sha256, its duration, whether
             it loops, its origin (`original`, or `licensed` with the licence and where it came from), its licence
             and its author.
  sources    each source exists, is mono 16-bit PCM WAV, and its sha256 and duration are the entry's.
  dist       dist/build.json names every built file of every kind (web ogg + m4a, Android ogg, iOS caf); each file
             exists with that sha256, was built from the entry's current source, and lasts under 30 s.
  versions   against the manifest and build record at <ref> (the base being merged into; default origin/develop):
             a new source needs a new `sound`; a `sound` raised needs a new source; a re-encoded file needs a higher
             `build` (or `sound`); no version goes down. `--against none` says there is no earlier version (the first
             one): every kind must then start at sound 1, build 1.
"""
import hashlib
import json
import os
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = ['ring', 'message', 'visitor', 'task', 'mail', 'bell']
TARGETS = ['web/{k}.ogg', 'web/{k}.m4a', 'android/raw/{k}.ogg', 'ios/{k}.caf']
MAX_MS = 30000
FIELDS = ['sound', 'build', 'source', 'sha256', 'durationMs', 'loop', 'origin', 'licence', 'author']

results = []  # (rule, verdict, line)


def say(rule, verdict, line):
    results.append((rule, verdict, line))


def sha256(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def load(path):
    try:
        return json.load(open(os.path.join(ROOT, path), encoding='utf-8')), None
    except (OSError, ValueError) as e:
        return None, str(e)


def at_ref(ref, path):
    """The file at a git ref: (data, None), (None, 'absent') when the ref has no such file, (None, why) otherwise."""
    out = subprocess.run(['git', '-C', ROOT, 'show', '%s:%s' % (ref, path)], capture_output=True, text=True)
    if out.returncode == 0:
        try:
            return json.loads(out.stdout), None
        except ValueError as e:
            return None, 'unreadable at %s: %s' % (ref, e)
    exists = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--verify', '--quiet', ref + '^{commit}'],
                            capture_output=True, text=True)
    return None, ('absent' if exists.returncode == 0 else 'the ref %s could not be read' % ref)


def check_kinds(m):
    have = list(m.get('sounds', {}).keys())
    missing = [k for k in KINDS if k not in have]
    extra = [k for k in have if k not in KINDS]
    if missing or extra:
        say('kinds', 'FOUND', 'missing: %s; not a kind: %s' % (', '.join(missing) or 'none', ', '.join(extra) or 'none'))
    else:
        say('kinds', 'CLEAR', '%d of %d kinds, nothing else' % (len(have), len(KINDS)))


def check_entries(m):
    bad = []
    for k, e in m.get('sounds', {}).items():
        gaps = [f for f in FIELDS if f not in e or e[f] in (None, '')]
        if gaps:
            bad.append('%s lacks %s' % (k, ', '.join(gaps)))
            continue
        for f in ('sound', 'build'):
            if not isinstance(e[f], int) or isinstance(e[f], bool) or e[f] < 1:
                bad.append('%s: %s is not an integer from 1' % (k, f))
        if e['origin'] not in ('original', 'licensed'):
            bad.append('%s: origin is neither original nor licensed' % k)
        if e['origin'] == 'licensed' and not e.get('obtainedFrom'):
            bad.append('%s: licensed, but where it came from is not recorded' % k)
        if not isinstance(e['loop'], bool):
            bad.append('%s: loop is not true or false' % k)
    n = len(m.get('sounds', {}))
    say('entries', 'FOUND' if bad else 'CLEAR',
        ('%d of %d entries: %s' % (len(bad), n, '; '.join(bad))) if bad else '%d of %d entries complete' % (n, n))


def check_sources(m):
    bad = []
    for k, e in m.get('sounds', {}).items():
        path = os.path.join(ROOT, e.get('source', ''))
        if not e.get('source') or not os.path.isfile(path):
            bad.append('%s: no source file' % k)
            continue
        try:
            with wave.open(path) as w:
                if w.getnchannels() != 1 or w.getsampwidth() != 2:
                    bad.append('%s: not mono 16-bit' % k)
                ms = round(w.getnframes() * 1000 / w.getframerate())
        except (wave.Error, EOFError) as err:
            bad.append('%s: not a WAV file (%s)' % (k, err))
            continue
        if sha256(path) != e.get('sha256'):
            bad.append('%s: its sha256 is not the entry\'s' % k)
        if ms != e.get('durationMs'):
            bad.append('%s: lasts %d ms, the entry says %s' % (k, ms, e.get('durationMs')))
    n = len(m.get('sounds', {}))
    say('sources', 'FOUND' if bad else 'CLEAR',
        ('%d of %d sources: %s' % (len(bad), n, '; '.join(bad))) if bad else '%d of %d sources match their entries' % (n, n))


def check_dist(m, b):
    if b is None:
        say('dist', 'FOUND', 'dist/build.json is missing or unreadable')
        return
    files = b.get('files', {})
    bad = []
    want = [(k, t.format(k=k)) for k in m.get('sounds', {}) for t in TARGETS]
    for k, rel in want:
        rec = files.get(rel)
        path = os.path.join(ROOT, 'dist', rel)
        if rec is None:
            bad.append('%s not in build.json' % rel)
        elif not os.path.isfile(path):
            bad.append('%s missing' % rel)
        elif sha256(path) != rec.get('sha256'):
            bad.append('%s: its sha256 is not the record\'s' % rel)
        elif rec.get('fromSource') != m['sounds'][k].get('sha256'):
            bad.append('%s was built from another source' % rel)
        elif not isinstance(rec.get('durationMs'), int) or rec['durationMs'] >= MAX_MS:
            bad.append('%s lasts %s ms, not under %d' % (rel, rec.get('durationMs'), MAX_MS))
    extra = [rel for rel in files if rel not in dict((r, k) for k, r in want)]
    if extra:
        bad.append('recorded but not a target: %s' % ', '.join(extra))
    say('dist', 'FOUND' if bad else 'CLEAR',
        ('%d of %d files: %s' % (len(bad), len(want), '; '.join(bad))) if bad
        else '%d of %d files present, as recorded, from the current sources, each under %d s' % (len(want), len(want), MAX_MS // 1000))


def check_versions(m, b, ref):
    sounds = m.get('sounds', {})
    if ref == 'none':
        bad = [k for k, e in sounds.items() if e.get('sound') != 1 or e.get('build') != 1]
        say('versions', 'FOUND' if bad else 'CLEAR',
            ('not at sound 1, build 1 with no earlier version: %s' % ', '.join(bad)) if bad
            else 'no earlier version (--against none): %d of %d kinds start at sound 1, build 1' % (len(sounds), len(sounds)))
        return
    prev, why = at_ref(ref, 'sounds.json')
    if prev is None and why != 'absent':
        say('versions', 'UNEVALUABLE', why)
        return
    if prev is None:
        say('versions', 'UNEVALUABLE', '%s holds no sounds.json; say --against none for the first version' % ref)
        return
    prev_build, why_b = at_ref(ref, 'dist/build.json')
    if prev_build is None and why_b != 'absent':
        say('versions', 'UNEVALUABLE', why_b)
        return
    prev_files = (prev_build or {}).get('files', {})
    files = (b or {}).get('files', {})
    bad = []
    for k, e in sounds.items():
        p = prev.get('sounds', {}).get(k)
        if p is None:
            continue
        new_source = e.get('sha256') != p.get('sha256')
        if e.get('sound', 0) < p.get('sound', 0):
            bad.append('%s: sound went down, %s -> %s' % (k, p.get('sound'), e.get('sound')))
        elif e.get('sound', 0) == p.get('sound', 0) and e.get('build', 0) < p.get('build', 0):
            bad.append('%s: build went down, %s -> %s' % (k, p.get('build'), e.get('build')))
        if new_source and e.get('sound') == p.get('sound'):
            bad.append('%s: a new source without a new sound' % k)
        if not new_source and e.get('sound', 0) > p.get('sound', 0):
            bad.append('%s: a new sound without a new source' % k)
        reencoded = [rel for rel in (t.format(k=k) for t in TARGETS)
                     if rel in prev_files and rel in files and prev_files[rel].get('sha256') != files[rel].get('sha256')]
        if reencoded and not new_source and e.get('sound') == p.get('sound') and e.get('build') == p.get('build'):
            bad.append('%s: re-encoded (%s) without a new build' % (k, ', '.join(reencoded)))
    compared = len([k for k in sounds if k in prev.get('sounds', {})])
    say('versions', 'FOUND' if bad else 'CLEAR',
        ('%d finding(s) against %s: %s' % (len(bad), ref, '; '.join(bad))) if bad
        else '%d of %d kinds compared with %s, each version follows its source and its files' % (compared, len(sounds), ref))


def main(argv):
    ref = 'origin/develop'
    if '--against' in argv:
        i = argv.index('--against')
        if i + 1 >= len(argv):
            print('usage: check.py [--against <git ref> | --against none]')
            return 2
        ref = argv[i + 1]
    m, why = load('sounds.json')
    if m is None:
        print('UNEVALUABLE  manifest  sounds.json could not be read: %s' % why)
        return 2
    b, _ = load('dist/build.json')
    check_kinds(m)
    check_entries(m)
    check_sources(m)
    check_dist(m, b)
    check_versions(m, b, ref)
    for rule, verdict, line in results:
        print('%-12s %-9s %s' % (verdict, rule, line))
    verdicts = [v for _, v, _ in results]
    if 'FOUND' in verdicts:
        return 1
    if 'UNEVALUABLE' in verdicts:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
