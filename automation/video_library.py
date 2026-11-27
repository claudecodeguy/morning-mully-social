#!/usr/bin/env python3
"""Discover MP4 uploads; preserve reviewed captions and require explicit approval."""
import argparse
import csv
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import quote
import plan

FIELDS = ['post_id','filename','public_url','sha256','instagram_caption','facebook_caption',
          'hashtags','youtube_title','youtube_description','approval_status','review_notes']


def read():
    path = plan.ROOT / 'data/videos.csv'
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def files():
    # Some uploads land at repository root. Preserve their public paths and bytes.
    found = {}
    for folder in (plan.ROOT / 'videos', plan.ROOT):
        for path in sorted(folder.glob('*')):
            if path.is_file() and path.suffix.lower() == '.mp4':
                if path.name in found:
                    raise ValueError('Ambiguous video filename: ' + path.name)
                found[path.name] = path
    return found


def public_url(filename):
    if Path(filename).name != filename or Path(filename).suffix.lower() != '.mp4':
        raise ValueError('Unsafe video filename')
    path = files().get(filename, plan.ROOT / 'videos' / filename)
    return plan.CONFIG['pages_base_url'].rstrip('/') + '/' + quote(path.relative_to(plan.ROOT).as_posix(), safe='/')


def sync():
    records = read()
    known = {r['filename']: r for r in records}
    if len(known) != len(records):
        raise ValueError('Duplicate video filenames')
    for path in sorted(files().values()):
        if path.suffix.lower() != '.mp4':
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.name not in known:
            number = max([int(r['post_id'][1:]) for r in records] + [0]) + 1
            row = dict.fromkeys(FIELDS, '')
            row.update(post_id=f'V{number:03}', filename=path.name, sha256=digest,
                       public_url=public_url(path.name), approval_status='NEEDS_REVIEW',
                       review_notes='New upload: review video/audio and add captions before approval.')
            records.append(row)
        else:
            row = known[path.name]
            if row['sha256'] != digest:
                row.update(sha256=digest, approval_status='NEEDS_REVIEW',
                           review_notes='File replaced; review again. Publication history is retained.')
            row['public_url'] = public_url(path.name)
    write(records)
    return records


def write(records):
    with (plan.ROOT / 'data/videos.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def captions(row):
    tags = row['hashtags'].strip()
    return {service: '\n\n'.join(s for s in [row[field].strip(), tags] if s)
            for service, field in [('instagram','instagram_caption'),('facebook','facebook_caption'),
                                   ('youtube','youtube_description')]}


def validate(remote=False):
    records = read()
    ids, names, hashes = set(), set(), set()
    for r in records:
        if r['post_id'] in ids or r['filename'] in names or r['sha256'] in hashes:
            raise ValueError('Duplicate video ID, filename or video bytes')
        ids.add(r['post_id']); names.add(r['filename']); hashes.add(r['sha256'])
        if not r['post_id'].startswith('V') or not r['post_id'][1:].isdigit():
            raise ValueError('Invalid video ID')
        url = public_url(r['filename'])
        path = files()[r['filename']]
        data = path.read_bytes()
        if r['public_url'] != url or hashlib.sha256(data).hexdigest() != r['sha256'] or data[4:8] != b'ftyp':
            raise ValueError('Video mapping/checksum/MP4 mismatch: ' + r['post_id'])
        if r['approval_status'] == 'APPROVED':
            if any(not r[f].strip() for f in ['instagram_caption','facebook_caption','youtube_title','youtube_description']):
                raise ValueError('Approved video has missing copy')
            if len(captions(r)['instagram']) > 2200 or len(r['youtube_title']) > 100 or len(captions(r)['youtube']) > 5000:
                raise ValueError('Video copy exceeds platform limits')
        if remote:
            with urllib.request.urlopen(url, timeout=30) as response:
                hosted = response.read()
                if response.status != 200 or hashlib.sha256(hosted).hexdigest() != r['sha256']:
                    raise ValueError('Hosted video mismatch: ' + r['post_id'])
    if set(files()) != names:
        raise ValueError('Run video_library.py sync for new uploads')
    return records


def probe():
    """Conservative format shared by Reels and Shorts; no transcoding or paid services."""
    for r in validate():
        result = subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-show_format',
            '-of','json',str(files()[r['filename']])], text=True)
        info = json.loads(result)
        stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
        if stream['codec_name'] != 'h264' or stream['width'] > stream['height'] or not 3 <= float(info['format']['duration']) <= 60:
            raise ValueError('Requires manual format review: ' + r['filename'])
        print(r['post_id'], r['filename'], stream['width'], stream['height'], info['format']['duration'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['sync','verify','probe','approve'])
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--id')
    for field in ['instagram_caption','facebook_caption','youtube_title','youtube_description','hashtags']:
        parser.add_argument('--' + field.replace('_','-'))
    args = parser.parse_args()
    if args.command == 'sync':
        sync()
    elif args.command == 'probe':
        probe()
    elif args.command == 'approve':
        records = sync()
        row = next((r for r in records if r['post_id'] == args.id), None)
        if row is None:
            parser.error('Unknown video ID')
        for field in ['instagram_caption','facebook_caption','youtube_title','youtube_description','hashtags']:
            if getattr(args, field) is not None:
                row[field] = getattr(args, field)
        row.update(approval_status='APPROVED', review_notes='Explicitly approved by repository owner.')
        # Validate before replacing the library on disk.
        original = (plan.ROOT / 'data/videos.csv').read_bytes()
        try:
            write(records); validate()
        except Exception:
            (plan.ROOT / 'data/videos.csv').write_bytes(original)
            raise
    else:
        print('Verified',len(validate(args.remote)), 'videos')


if __name__ == '__main__':
    main()
