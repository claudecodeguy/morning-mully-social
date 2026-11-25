#!/usr/bin/env python3
"""Reproducible, offline queue preview from a complete read-only Buffer snapshot."""
import argparse
import copy
import json
from datetime import datetime, timezone
import plan
import publish
import rolling_queue
import video_library


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',default='data/video-queue-snapshot.json')
    parser.add_argument('--date',default='2026-11-25T01:00:00+00:00')
    parser.add_argument('--assume-approved',action='store_true',help='Simulation only; never edits CSV approval status')
    args=parser.parse_args()
    snapshot=json.loads((plan.ROOT / args.snapshot).read_text())
    if not snapshot.get('complete'):
        raise RuntimeError('Incomplete queue snapshot; refusing capacity calculation')
    class Snapshot:
        def posts(self): return copy.deepcopy(snapshot['posts'])
        def channels(self): return copy.deepcopy(snapshot['channels'])
        def create(self,body): raise AssertionError('Dry run must never create posts')
    class Ledger:
        data=json.loads((plan.ROOT / publish.STATE_PATH).read_text())
        def save(self): raise AssertionError('Dry run must never save history')
    videos=video_library.validate()
    if args.assume_approved:
        for row in videos: row['approval_status']='APPROVED'
    print('DRY RUN: zero API calls, zero Buffer writes, zero approval changes.')
    print('Snapshot:',snapshot['captured_at'],'(capacity may change before activation)')
    print('Approvals:', 'ASSUMED FOR SIMULATION ONLY' if args.assume_approved else 'actual library approvals')
    for service,cid in publish.ALL_CHANNELS.items():
        print(service,'currently occupied:',publish.occupied(snapshot['posts'],cid))
    for line in rolling_queue.refill(Snapshot(),Ledger(),publish.validate_library(),videos,
                                    datetime.fromisoformat(args.date),False):
        print(line)

if __name__=='__main__': main()
