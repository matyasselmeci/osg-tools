#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily condor build pruner


"""
from collections import defaultdict, namedtuple
from datetime import date, timedelta
import glob
import re
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# local imports here

# To run unit tests, run with --self-test


#######################################################################
# Unit testing {{{
import unittest

# dir with only one set of binaries
test_dir1 = [
    "condor-8.9.9-20201014-Windows-x64.msi",
    "condor-8.9.9-20201014-Windows-x64.zip",
    "condor-8.9.9-20201014-x86_64_CentOS7-stripped.tar.gz",
    "condor-8.9.9-20201014-x86_64_CentOS7-unstripped.tar.gz",
    "condor-8.9.9-20201014-x86_64_CentOS8-stripped.tar.gz",
    "condor-8.9.9-20201014-x86_64_CentOS8-unstripped.tar.gz",
    "sha256sum.txt",
    "sha256sum.txt.gpg",
]

# also including a newer set of binaries
test_dir2 = test_dir1 + [
    "condor-8.9.9-20201114-Windows-x64.msi",
    "condor-8.9.9-20201114-Windows-x64.zip",
    "condor-8.9.9-20201114-x86_64_CentOS7-stripped.tar.gz",
    "condor-8.9.9-20201114-x86_64_CentOS7-unstripped.tar.gz",
    "condor-8.9.9-20201114-x86_64_CentOS8-stripped.tar.gz",
    "condor-8.9.9-20201114-x86_64_CentOS8-unstripped.tar.gz",
]

# also including a subset of newer binaries
test_dir3 = test_dir2 + [
    "condor-8.9.9-20201115-Windows-x64.msi",
    "condor-8.9.9-20201115-Windows-x64.zip",
]


class TestSelf(unittest.TestCase):
    def setUp(self):
        return

    def tearDown(self):
        return

    def test_BuildInfo_from_file(self):
        exp_date = date(2020, 10, 14)
        # fmt: off
        expected = [
            BuildInfo(groupkey="8.9.9--Windows-x64.msi", builddate=exp_date, filename="condor-8.9.9-20201014-Windows-x64.msi"),
            BuildInfo(groupkey="8.9.9--Windows-x64.zip", builddate=exp_date, filename="condor-8.9.9-20201014-Windows-x64.zip"),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS7-stripped.tar.gz", builddate=exp_date, filename="condor-8.9.9-20201014-x86_64_CentOS7-stripped.tar.gz"),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS7-unstripped.tar.gz", builddate=exp_date, filename="condor-8.9.9-20201014-x86_64_CentOS7-unstripped.tar.gz"),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS8-stripped.tar.gz", builddate=exp_date, filename="condor-8.9.9-20201014-x86_64_CentOS8-stripped.tar.gz"),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS8-unstripped.tar.gz", builddate=exp_date, filename="condor-8.9.9-20201014-x86_64_CentOS8-unstripped.tar.gz"),
            None,
            None,
        ]
        # fmt: on

        for idx, val in enumerate(test_dir1):
            self.assertEqual(expected[idx], BuildInfo.from_filename(val))

    def test_BuildLists1(self):
        bl = BuildLists()
        for fn in test_dir1:
            bl.add_build(BuildInfo.from_filename(fn))
        self.assertEqual(len(bl.data), 6)

    def test_BuildLists2(self):
        bl = BuildLists()
        for fn in test_dir2:
            bl.add_build(BuildInfo.from_filename(fn))
        self.assertEqual(len(bl.data), 6)

    def test_BuildLists3(self):
        bl = BuildLists()
        for fn in test_dir3:
            bl.add_build(BuildInfo.from_filename(fn))
        self.assertEqual(len(bl.data), 6)

    def test_nonlatest(self):
        bl = BuildLists()
        for fn in test_dir3:
            bl.add_build(BuildInfo.from_filename(fn))
        nonlatest = bl.non_latest_by_key()
        self.assertIn("8.9.9--x86_64_CentOS7-stripped.tar.gz", nonlatest)
        self.assertEqual(
            nonlatest["8.9.9--x86_64_CentOS7-stripped.tar.gz"][0].builddate,
            date(2020, 10, 14),
        )

    def test_older_than_threshold(self):
        self.assertTrue(
            BuildInfo.from_filename(
                "condor-8.9.9-20201014-Windows-x64.msi"
            ).older_than_threshold(threshold=30.0, today=date(2020, 11, 14))
        )
        self.assertFalse(
            BuildInfo.from_filename(
                "condor-8.9.9-20201014-Windows-x64.msi"
            ).older_than_threshold(threshold=60.0, today=date(2020, 11, 14))
        )


def self_test():
    """Run the unit tests"""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSelf)
    return not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


# }}}
#######################################################################


class BuildInfo:
    """Contains the information for a build, extracted from the file name.
    - builddate: build date as datetime.date object
    - groupkey: everything else from the filename: version, platform, arch, stripped/unstripped, format, etc.
    - filename: the filename itself
    """

    builddate = None
    groupkey = None
    filename = None

    def __init__(self, builddate: date, groupkey: str, filename: str):
        self.builddate = builddate
        self.groupkey = groupkey
        self.filename = filename

    @classmethod
    def from_filename(cls, filename: str) -> Optional["BuildInfo"]:
        m = re.search(
            r"condor-(?P<pre>\d+[.]\d+[.]\d+-)(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?P<post>.+)",
            os.path.basename(filename),
        )
        if not m:
            return None
        builddate = date(
            int(m.group("year")), int(m.group("month")), int(m.group("day"))
        )
        groupkey = m.group("pre") + m.group("post")
        return cls(builddate=builddate, groupkey=groupkey, filename=filename)

    def older_than_threshold(self, threshold: float, today: date = None) -> bool:
        if not today:
            today = date.today()
        threshold_date = today - timedelta(days=threshold)
        return self.builddate < threshold_date

    def __lt__(self, other: "BuildInfo"):
        return (self.builddate, self.groupkey) < (other.builddate, other.groupkey)

    def __eq__(self, other: "BuildInfo"):
        return (self.builddate, self.groupkey) == (other.builddate, other.groupkey)

    def __gt__(self, other: "BuildInfo"):
        return (self.builddate, self.groupkey) > (other.builddate, other.groupkey)

    def __le__(self, other: "BuildInfo"):
        return (self.builddate, self.groupkey) <= (other.builddate, other.groupkey)

    def __ge__(self, other: "BuildInfo"):
        return (self.builddate, self.groupkey) >= (other.builddate, other.groupkey)

    def __ne__(self, other: "BuildInfo"):
        return (self.builddate, self.groupkey) != (other.builddate, other.groupkey)

    def __repr__(self):
        return "BuildInfo(%s, %s)" % (self.builddate, self.groupkey)

    def __hash__(self):
        return hash(repr(self))


class BuildLists:
    def __init__(self):
        # can't use a set because buildinfo is unhashable
        self.data = defaultdict(list)

    def add_build(self, buildinfo: BuildInfo):
        if buildinfo:
            self.data[buildinfo.groupkey].append(buildinfo)

    def non_latest_by_key(self) -> Dict[str, List[BuildInfo]]:
        ret = {}
        for key, buildslist in self.data.items():
            if not buildslist:
                continue
            ret[key] = sorted(buildslist)[:-1]
        return ret


def main(argv):
    if len(argv) > 1 and argv[1] == "--self-test":
        return self_test()
    # EXECUTION BEGINS HERE
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
