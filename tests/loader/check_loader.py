# Copyright 2015 Confluent Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ducktape.tests.loader import TestLoader, LoaderException
from ducktape.tests.session import SessionContext

from tests.mock import MockArgs
from tests.loader.resources.loader_test_directory.test_a import TestA

import os
import os.path
import tempfile
import pytest


def discover_dir():
    """Return the absolute path to the directory to use with discovery tests."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "loader_test_directory")


class CheckTestLoader(object):
    def setup_method(self, method):
        tmp = tempfile.mkdtemp()
        session_dir = os.path.join(tmp, "test_dir")
        os.mkdir(session_dir)
        self.SESSION_CONTEXT = SessionContext("test_session", session_dir, None, MockArgs())

    def check_find_test_method(self):
        """Check that discovery finds correct methods within a test class"""
        loader = TestLoader(self.SESSION_CONTEXT)
        test_method_names = loader.find_test_methods(TestA)
        assert len(test_method_names) == 2

    def check_test_loader_with_directory(self):
        """Check discovery on a directory."""
        loader = TestLoader(self.SESSION_CONTEXT)
        test_classes = loader.discover([discover_dir()])
        assert len(test_classes) == 6

    def check_test_loader_with_file(self):
        """Check discovery on a file. """
        loader = TestLoader(self.SESSION_CONTEXT)
        test_classes = loader.discover([os.path.join(discover_dir(), "test_a.py")])
        assert len(test_classes) == 2

    def check_test_loader_multiple_files(self):
        loader = TestLoader(self.SESSION_CONTEXT)
        test_classes = loader.discover([
            os.path.join(discover_dir(), "test_a.py"),
            os.path.join(discover_dir(), "test_b.py")

        ])
        assert len(test_classes) == 5

    def check_test_loader_with_nonexistent_file(self):
        """Check discovery on a starting path that doesn't exist throws an"""
        with pytest.raises(LoaderException):
            loader = TestLoader(self.SESSION_CONTEXT)
            test_classes = loader.discover([os.path.join(discover_dir(), "file_that_does_not_exist.py")])

    def check_test_loader_with_class(self):
        """Check test discovery with discover class syntax."""
        loader = TestLoader(self.SESSION_CONTEXT)
        test_classes = loader.discover([os.path.join(discover_dir(), "test_b.py::TestBB")])
        assert len(test_classes) == 2

        # Sanity check, test that it discovers two tests if it searches the whole module
        test_classes = loader.discover([os.path.join(discover_dir(), "test_b.py")])
        assert len(test_classes) == 3





