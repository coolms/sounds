#!/usr/bin/env python3
"""Encodes every source into the formats each client plays, and records what was built in dist/build.json.

    python3 tools/encode.py

- dist/web/<kind>.ogg      Opus, 64 kb/s   (browsers)
- dist/web/<kind>.m4a      AAC, 96 kb/s    (Safari before Opus)
- dist/android/raw/<kind>.ogg  Vorbis      (res/raw; a notification channel's sound)
- dist/ios/<kind>.caf      linear PCM      (the app bundle; under 30 s, so the ring is its loop repeated to 20 s)

The encoder is tools/encoder/Dockerfile, built here when missing and run with no network as the calling user.
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKERFILE_DIR = os.path.join(ROOT, 'tools', 'encoder')
IMAGE = 'coolms-sound-encoder:bookworm-ffmpeg-5.1.9'
# The ring's loop unit repeated for iOS, which cannot loop a notification sound: 10 x 2.0 s = 20 s, under 30 s.
IOS_RING_REPEATS = 10
BITEXACT = ['-map_metadata', '-1', '-fflags', '+bitexact', '-flags:a', '+bitexact']

TARGETS = [
    ('web/{k}.ogg', ['-c:a', 'libopus', '-b:a', '64k'], 'opus'),
    ('web/{k}.m4a', ['-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart'], 'aac'),
    ('android/raw/{k}.ogg', ['-c:a', 'libvorbis', '-q:a', '5'], 'vorbis'),
    ('ios/{k}.caf', ['-c:a', 'pcm_s16le', '-f', 'caf'], 'pcm_s16le'),
]


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def image_id():
    out = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', IMAGE], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ''


def docker(entrypoint, args):
    return run(['docker', 'run', '--rm', '--network', 'none', '-u', '%d:%d' % (os.getuid(), os.getgid()),
                '-v', ROOT + ':/work', '-w', '/work', '--entrypoint', entrypoint, IMAGE] + args,
               capture_output=True, text=True)


def sha256(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def main():
    if not image_id():
        print('encode: building %s from tools/encoder/Dockerfile' % IMAGE)
        run(['docker', 'build', '-q', '-t', IMAGE, DOCKERFILE_DIR])
    manifest = json.load(open(os.path.join(ROOT, 'sounds.json'), encoding='utf-8'))
    version = docker('ffmpeg', ['-hide_banner', '-version']).stdout.splitlines()[0]
    built = {}
    for kind, entry in manifest['sounds'].items():
        src = entry['source']
        for pattern, codec_args, codec in TARGETS:
            rel = pattern.format(k=kind)
            os.makedirs(os.path.dirname(os.path.join(ROOT, 'dist', rel)), exist_ok=True)
            loop = ['-stream_loop', str(IOS_RING_REPEATS - 1)] if rel.startswith('ios/') and entry.get('loop') else []
            docker('ffmpeg', ['-nostdin', '-y', '-loglevel', 'error'] + loop + ['-i', src] + codec_args + BITEXACT
                   + ['dist/' + rel])
            probe = json.loads(docker('ffprobe', ['-v', 'error', '-print_format', 'json', '-show_entries',
                                                  'format=duration:stream=codec_name', 'dist/' + rel]).stdout)
            built[rel] = {
                'kind': kind,
                'sha256': sha256(os.path.join(ROOT, 'dist', rel)),
                'codec': probe['streams'][0]['codec_name'],
                'durationMs': int(round(float(probe['format']['duration']) * 1000)),
                'fromSource': entry['sha256'],
            }
            print('%-28s %-9s %6d ms' % (rel, built[rel]['codec'], built[rel]['durationMs']))
    record = {
        'encoder': {
            'image': IMAGE,
            'imageId': image_id(),
            'dockerfileSha256': sha256(os.path.join(DOCKERFILE_DIR, 'Dockerfile')),
            'ffmpeg': version,
        },
        'files': built,
    }
    with open(os.path.join(ROOT, 'dist', 'build.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write('\n')
    print('encode: %d files, recorded in dist/build.json' % len(built))
    return 0


if __name__ == '__main__':
    sys.exit(main())
