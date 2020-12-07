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


class BuildInfo:
    pass  ### forward declaration for type hinting


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
test_dir3 = test_dir1 + [
    "condor-8.9.9-20201114-Windows-x64.msi",
    "condor-8.9.9-20201114-Windows-x64.zip",
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
            BuildInfo(groupkey="8.9.9--Windows-x64.msi", builddate=exp_date),
            BuildInfo(groupkey="8.9.9--Windows-x64.zip", builddate=exp_date),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS7-stripped.tar.gz", builddate=exp_date),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS7-unstripped.tar.gz", builddate=exp_date),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS8-stripped.tar.gz", builddate=exp_date),
            BuildInfo(groupkey="8.9.9--x86_64_CentOS8-unstripped.tar.gz", builddate=exp_date),
            None,
            None,
        ]
        # fmt: on

        for idx, val in enumerate(test_dir1):
            self.assertEqual(expected[idx], BuildInfo.from_filename(val))


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
    """
    builddate = None
    groupkey = None

    def __init__(self, builddate: date, groupkey: str):
        self.builddate = builddate
        self.groupkey = groupkey

    @classmethod
    def from_filename(cls, filename: str) -> Optional[BuildInfo]:
        m = re.match(
            r"condor-(?P<pre>\d+[.]\d+[.]\d+-)(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?P<post>.+)",
            os.path.basename(filename),
        )
        if not m:
            return None
        builddate = date(
            int(m.group("year")), int(m.group("month")), int(m.group("day"))
        )
        groupkey = m.group("pre") + m.group("post")
        return cls(builddate=builddate, groupkey=groupkey)

    @classmethod
    def file_older_than_threshold(cls, filename: str, threshold: float) -> bool:
        return cls.from_filename(filename).older_than_threshold(threshold)

    def older_than_threshold(self, threshold: float) -> bool:
        threshold_date = date.today() - timedelta(days=threshold)
        return self.builddate < threshold_date

    def __lt__(self, other: BuildInfo):
        return (self.builddate, self.groupkey) < (other.builddate, other.groupkey)

    def __eq__(self, other: BuildInfo):
        return (self.builddate, self.groupkey) == (other.builddate, other.groupkey)

    def __gt__(self, other: BuildInfo):
        return (self.builddate, self.groupkey) > (other.builddate, other.groupkey)

    def __le__(self, other: BuildInfo):
        return (self.builddate, self.groupkey) <= (other.builddate, other.groupkey)

    def __ge__(self, other: BuildInfo):
        return (self.builddate, self.groupkey) >= (other.builddate, other.groupkey)

    def __ne__(self, other: BuildInfo):
        return (self.builddate, self.groupkey) != (other.builddate, other.groupkey)

    def __str__(self):
        return "(%s, %s)" % self.builddate, self.groupkey


class BuildsLists:
    def __init__(self):
        self.data = defaultdict(list)

    def add_build(self, buildinfo: BuildInfo):
        self.data[buildinfo.groupkey].append(buildinfo)

    def latest_by_key(self) -> Dict[str, BuildInfo]:
        ret = {}
        for key, buildslist in self.data.items():
            if not buildslist:
                continue
            ret[key] = sorted(buildslist)[-1]
        return ret


def main(argv):
    if len(argv) > 1 and argv[1] == "--self-test":
        return self_test()
    # EXECUTION BEGINS HERE
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
