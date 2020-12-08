#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily condor build pruner


"""
from collections import defaultdict
from datetime import date, timedelta
import itertools
import re
import os
import shutil
import subprocess
import sys
from typing import Dict, Iterable, List, Optional

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
    "condor-8.9.9-20201215-Windows-x64.msi",
    "condor-8.9.9-20201215-Windows-x64.zip",
]


class TestSelf(unittest.TestCase):
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
        bl = BuildLists(BuildInfo.from_filename(fn) for fn in test_dir1)
        self.assertEqual(len(bl.data), 6)

    def test_BuildLists2(self):
        bl = BuildLists(BuildInfo.from_filename(fn) for fn in test_dir2)
        self.assertEqual(len(bl.data), 6)

    def test_BuildLists3(self):
        bl = BuildLists(BuildInfo.from_filename(fn) for fn in test_dir3)
        self.assertEqual(len(bl.data), 6)

    def test_nonlatest(self):
        bl = BuildLists(BuildInfo.from_filename(fn) for fn in test_dir3)
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
            ).older_than_threshold(threshold_days=30.0, today=date(2020, 11, 14))
        )
        self.assertFalse(
            BuildInfo.from_filename(
                "condor-8.9.9-20201014-Windows-x64.msi"
            ).older_than_threshold(threshold_days=60.0, today=date(2020, 11, 14))
        )

    def test_deletion_candidates(self):
        bl = BuildLists()
        for fn in test_dir3:
            bl.add_build(BuildInfo.from_filename(fn))
        candidates1 = bl.deletion_candidates(threshold_days=30.0, today=date(2020, 12, 15))
        candidates2 = bl.deletion_candidates(threshold_days=30.0, today=date(2020, 11, 15))
        self.assertEqual(len(candidates1), 8)
        self.assertEqual(len(candidates2), 6)
        for candidates in candidates1, candidates2:
            self.assertNotIn("condor-8.9.9-20201215-Windows-x64.msi", candidates)
            self.assertNotIn("condor-8.9.9-20201114-x86_64_CentOS7-unstripped.tar.gz", candidates)
            self.assertIn("condor-8.9.9-20201014-x86_64_CentOS7-unstripped.tar.gz", candidates)



def self_test():
    """Run the unit tests"""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSelf)
    return not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


# }}}
#######################################################################

TODAY = date.today()
PRUNE_EXTENSIONS = [".tar.gz", ".tar.bz2", ".tar.xz", ".rpm", ".deb", ".zip", ".msi"]


class BuildInfo:
    """Contains the information for a build, extracted from the file name.
    - builddate: build date as datetime.date object
    - groupkey: everything else from the filename: version, platform, arch, stripped/unstripped, format, etc.
    - filename: the filename itself

    Generally you should use the from_filename() factory method, which can return None
    if the filename is in the wrong format for a build.
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
        """Factory method; parse the filename to get the info.  Will return None if
        the filename doesn't look like a build, i.e. wrong extension, or can't be
        parsed.

        """
        for extension in PRUNE_EXTENSIONS:
            if filename.endswith(extension):
                break
        else:
            return None
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

    def older_than_threshold(self, threshold_days: float, today=TODAY) -> bool:
        threshold_date = today - timedelta(days=threshold_days)
        return self.builddate < threshold_date

    def __eq__(self, other: "BuildInfo"):
        return (self.builddate, self.groupkey) == (other.builddate, other.groupkey)

    def __repr__(self):
        return "BuildInfo(%s, %s)" % (self.builddate, self.groupkey)

    def __hash__(self):
        return hash(repr(self))


class BuildLists:
    def __init__(self, builds: Optional[Iterable] = None):
        builds = builds or []
        self.data = defaultdict(set)
        self.add_builds(builds)

    def add_build(self, buildinfo: BuildInfo):
        if buildinfo:
            self.data[buildinfo.groupkey].add(buildinfo)

    def add_builds(self, builds: Iterable[BuildInfo]):
        for it in builds:
            self.add_build(it)

    def non_latest_by_key(self) -> Dict[str, List[BuildInfo]]:
        ret = {}
        for key, buildslist in self.data.items():
            if not buildslist:
                continue
            ret[key] = sorted(buildslist, key=lambda x: (x.builddate, x.groupkey))[:-1]
        return ret

    def deletion_candidates(self, threshold_days: float, today=TODAY) -> List[str]:
        all_nonlatest = itertools.chain.from_iterable(self.non_latest_by_key().values())
        return [build.filename for build in all_nonlatest if build.older_than_threshold(threshold_days=threshold_days, today=today)]


def main(argv):
    if len(argv) > 1 and argv[1] == "--self-test":
        return self_test()
    # EXECUTION BEGINS HERE
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
