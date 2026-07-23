"""
cMeta tests

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import unittest
from cmeta.utils.names import parse_cmeta_name, restore_cmeta_name

class TestParseCmetaName(unittest.TestCase):
    def test_alias_only(self):
        result = parse_cmeta_name("my-alias")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"alias": "my-alias"})

    def test_uid_only(self):
        result = parse_cmeta_name("1234567890abcdef")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"uid": "1234567890abcdef"})

    def test_alias_and_uid(self):
        result = parse_cmeta_name("my-alias,1234567890abcdef")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"alias": "my-alias", "uid": "1234567890abcdef"})

    def test_alias_with_comma(self):
        result = parse_cmeta_name("my,alias, 1234567890abcdef")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"alias": "my,alias", "uid": "1234567890abcdef"})

    def test_whitespace(self):
        result = parse_cmeta_name("  my-alias  ,  1234567890abcdef  ")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"alias": "my-alias", "uid": "1234567890abcdef"})

    def test_empty(self):
        result = parse_cmeta_name("")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {})

    def test_none(self):
        result = parse_cmeta_name(None)
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {})

    # Extra tests for key parameter
    def test_key_artifact(self):
        result = parse_cmeta_name("artifact-alias, 1234567890abcdef", key="artifact")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"artifact_alias": "artifact-alias", "artifact_uid": "1234567890abcdef"})

    def test_key_repo(self):
        result = parse_cmeta_name("repo-alias, 1234567890abcdef", key="repo")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"repo_alias": "repo-alias", "repo_uid": "1234567890abcdef"})

    def test_key_category(self):
        result = parse_cmeta_name("category-alias, 1234567890abcdef", key="category")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"category_alias": "category-alias", "category_uid": "1234567890abcdef"})

    def test_key_none(self):
        result = parse_cmeta_name("category-alias, 1234567890abcdef", key=None)
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], {"alias": "category-alias", "uid": "1234567890abcdef"})

    def test_restore_alias_only(self):
        result = restore_cmeta_name({"alias": "myalias"})
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], "myalias")

    def test_restore_uid_only(self):
        result = restore_cmeta_name({"uid": "abcd1234abcd1234"})
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], "abcd1234abcd1234")

    def test_restore_alias_uid(self):
        result = restore_cmeta_name({"alias": "myalias", "uid": "abcd1234abcd1234"})
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], "myalias,abcd1234abcd1234")

    def test_restore_with_key(self):
        result = restore_cmeta_name({"artifact_alias": "myalias", "artifact_uid": "abcd1234abcd1234"}, key="artifact")
        self.assertEqual(result['return'], 0)
        self.assertEqual(result['name'], "myalias,abcd1234abcd1234")

if __name__ == "__main__":
    unittest.main()
