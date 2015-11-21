#!/usr/bin/env python
import unittest
import logging
import sys
import os
import copy

import time
here = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(here, '..'))
from flickrsmartsync.sync import Sync
logger = logging.getLogger("flickrsmartsync")
logger.setLevel(logging.WARNING)

fakestat = os.stat(__file__)
fakeid = 45


class FakeLocal:
    files = {}
    def __init__(self):
        self.files.clear()
        self.files.update({here + os.sep + "dirname": [("file1.jpg", fakestat), ("file2.avi", fakestat)]})
    
    def build_photo_sets(self, specific_path, exts):
        return self.files


class FakeRemote:
    def __init__(self):
        self.photo_sets_map = {"dirname": "12345"}
        self.files = {"12345": {"file3.jpg": 23, "file4.avi": 23}}

    def get_photo_sets(self):
        return self.photo_sets_map

    @staticmethod
    def get_custom_set_title(path):
        return path.split('/').pop()

    def get_photos_in_set(self, folder, get_url=False):
        return self.files[self.photo_sets_map[folder]]

    def upload(self, _, photo, folder):
        self.files[self.photo_sets_map[folder]][photo] = fakeid
        return fakeid

    @staticmethod
    def download(_, path):
        FakeLocal.files.values()[0].append((os.path.basename(path), fakestat))


class SyncTest(unittest.TestCase):
    maxDiff=None

    def setUp(self):
        class Args:
            sync_path=here+os.sep
            custom_set=None
            ignore_images=False
            ignore_videos=False
            ignore_ext=None
            is_windows=False
            download="."
            sync_from="all"

        self.local = FakeLocal()
        self.remote = FakeRemote()
        self.sync = Sync(Args(), self.local, self.remote)

    def tearDown(self):
        pass

    def test_upload(self):
        expected = FakeRemote().files
        for f, s in self.local.files.values()[0]:
            expected.values()[0][f] = fakeid
        self.sync.upload()
        self.assertEquals(self.remote.files, expected)

    def test_download(self):
        expected = copy.deepcopy(FakeLocal().files)
        expected.values()[0] += [(x, fakestat) for x in self.remote.files.values()[0]]
        self.sync.download()
        self.assertEquals(self.local.files, expected)

    def test_sync(self):
        expected_r = FakeRemote().files
        for f, s in self.local.files.values()[0]:
            expected_r.values()[0][f] = fakeid
        expected_l = copy.deepcopy(FakeLocal().files)
        expected_l.values()[0] += [(x, fakestat) for x in self.remote.files.values()[0]]
        self.sync.sync()
        self.assertEquals(self.remote.files, expected_r)
        self.assertEquals(self.local.files, expected_l)
        
if __name__ == '__main__':
    logging.debug('Started test case')
    unittest.main(verbosity=2)      
