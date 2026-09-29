"""Test package for uniparser2.

Making this a real package (every subdirectory has an ``__init__.py``) buys two concrete things:
1. module names are fully qualified such as ``tests.ops.test_basic``, so same-named test files in
   different directories cannot shadow each other;
2. mypy's ``module = ["tests.*"]`` override only matches fully qualified names.
"""
