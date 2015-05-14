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

from ducktape.tests.test import Test
from ducktape.tests.test import TestContext

import importlib
import inspect
import os
import re


class LoaderException(Exception):
    pass


class TestLoader(object):
    """Class used to discover and load tests."""
    DEFAULT_TEST_FILE_PATTERN = "(^test_.*\.py$)|(^.*_test\.py$)"
    DEFAULT_TEST_METHOD_PATTERN = "(^run$)|(^test_.*$)|(^.*_test$)"

    def __init__(self, session_context):
        self.session_context = session_context
        self.logger = session_context.logger

    def parse_discovery_symbol(self, discovery_symbol):
        """Parse command-line argument into a tuple (directory, module.py, class_name).

        :raise LoaderException if it can't be parsed
        """
        directory = os.path.abspath(os.path.dirname(discovery_symbol))
        base = os.path.basename(discovery_symbol)

        if base.find("::") >= 0:
            parts = base.split("::")
            if len(parts) == 1:
                module, cls_name = parts[0], ""
            elif len(parts) == 2:
                module, cls_name = parts
            else:
                raise LoaderException("Invalid discovery symbol: " + discovery_symbol)
        else:
            module, cls_name = base, ""

        return tuple([directory, module, cls_name])

    def discover(self, test_discovery_symbols, pattern=DEFAULT_TEST_FILE_PATTERN):
        """Recurse through packages in file hierarchy starting at base_dir, and return a list of all found test classes.

        - Discover modules that 'look like' a test. By default, this means the filename is "test_*" or "*_test.py"
        - Discover test classes within each test module. A test class is a subclass of Test which is a leaf
          (i.e. it has no subclasses).

        :type test_discovery_symbols: list
        :type pattern: str
        :rtype: list
        """
        testable_units = []
        assert type(test_discovery_symbols) == list, "Expected test_discovery_symbols to be a list."
        for symbol in test_discovery_symbols:
            directory, module_name, cls_name = self.parse_discovery_symbol(symbol)

            # Check validity
            path = os.path.join(directory, module_name)
            if not os.path.exists(path):
                raise LoaderException("Path {} does not exist".format(path))

            if os.path.isfile(path):
                test_files = [os.path.abspath(path)]
            else:
                test_files = self.find_test_files(path, pattern)
            test_modules = self.import_modules(test_files)

            # pull test_classes out of test_modules
            test_classes_from_symbol = []
            for module in test_modules:
                try:
                    test_classes_from_symbol.extend(self.get_test_classes(module))
                except Exception as e:
                    self.logger.debug("Error getting test classes from module: " + e.message)

            if len(cls_name) > 0:
                # We only want to run a specific test class
                test_classes_from_symbol = [test for test in test_classes_from_symbol if test.__name__ == cls_name]
                if len(test_classes_from_symbol) == 0:
                    raise LoaderException("Could not find any tests corresponding to the symbol " + symbol)

                if len(test_classes_from_symbol) > 1:
                    raise LoaderException("Somehow there are multiple tests corresponding to the symbol " + symbol)

            # drill into test classes, discover test methods, and create testable units
            for t_class in test_classes_from_symbol:
                test_methods = self.find_test_methods(t_class)
                if len(test_methods) > 0:
                    testable_units.extend([self.create_test_case(t_class, m_name) for m_name in test_methods])
                else:
                    # If no "test method" in the base class, assume there is a run
                    # method higher in the hierarchy
                    testable_units.extend([self.create_test_case(t_class, "run")])

        self.logger.debug("Discovered these tests: " + str(testable_units))
        return testable_units

    def find_test_methods(self, t_class):
        """Find methods in the test class which look like tests"""
        test_method_names = []
        for attr_name in t_class.__dict__:
            attr_obj = t_class.__dict__[attr_name]
            if self.is_test_method(attr_obj):
                test_method_names.append(attr_name)

        return test_method_names

    def create_test_case(self, test_class, method_name="run"):
        """Create test context object and instantiate test class.

        :type test_class: ducktape.tests.test.Test.__class__
        :type session_context: ducktape.tests.session.SessionContext
        :rtype test_class
        """

        test_context = TestContext(self.session_context, test_class.__module__, test_class, method_name)
        return test_class(test_context)

    def find_test_files(self, base_dir, pattern=DEFAULT_TEST_FILE_PATTERN):
        """Return a list of files underneath base_dir that look like test files.
        The returned file names are absolute paths to the files in question.

        :type base_dir: str
        :type pattern: str
        :rtype: list
        """
        test_files = []

        for pwd, dirs, files in os.walk(base_dir):
            if "__init__.py" not in files:
                # Not a package - ignore this directory
                continue
            for f in files:
                file_path = os.path.abspath(os.path.join(pwd, f))
                if self.is_test_file(file_path, pattern):
                    test_files.append(file_path)

        return test_files

    def import_modules(self, file_list):
        """Attempt to import modules in the file list.
        Assume all files in the list are absolute paths ending in '.py'

        Return all imported modules.

        :type file_list: list
        :rtype: list
        """
        module_list = []

        for f in file_list:
            if f[-3:] != ".py" or not os.path.isabs(f):
                raise Exception("Expected absolute path ending in '.py' but got " + f)

            # Try all possible module imports for given file
            path_pieces = f[:-3].split("/")  # Strip off '.py' before splitting
            while len(path_pieces) > 0:
                module_name = '.'.join(path_pieces)
                # Try to import the current file as a module
                try:
                    module_list.append(importlib.import_module(module_name))
                    self.logger.debug("Successfully imported " + module_name)
                    break  # no need to keep trying
                except Exception as e:
                    self.logger.debug("Could not import " + module_name + ": " + e.message)
                    self.logger.debug(
                        "   But it's ok: at most one import should work per module, so import failures are expected.")
                    continue
                finally:
                    path_pieces = path_pieces[1:]

        return module_list

    def get_test_classes(self, module):
        """Return list of all test classes in the module object."""
        module_objects = module.__dict__.values()
        return [c for c in module_objects if self.is_test_class(c)]

    def is_test_method(self, obj, pattern=DEFAULT_TEST_METHOD_PATTERN):
        """A test method is any callable object with a name matching the test name pattern.
        By default, a test method is "run", or "test_*" or "*_test"
        """
        if not hasattr(obj, "__name__"):
            return False

        method_name = obj.__name__
        return hasattr(obj, "__call__") and re.match(pattern, method_name) is not None

    def is_test_file(self, file_name, pattern=DEFAULT_TEST_FILE_PATTERN):
        """By default, a test file looks like test_*.py or *_test.py"""
        return re.match(pattern, os.path.basename(file_name)) is not None

    def is_test_class(self, obj):
        """An object is a test class if it's a leafy subclass of Test.
        """
        return inspect.isclass(obj) and issubclass(obj, Test) and len(obj.__subclasses__()) == 0
