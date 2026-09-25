import unittest

from mysql_diag_mcp.explain import ExplainRejected, validate_explain_sql


class ExplainGuardTests(unittest.TestCase):
    def test_select_ok(self):
        self.assertEqual(
            validate_explain_sql("SELECT id FROM orders WHERE id = 1"),
            "SELECT id FROM orders WHERE id = 1",
        )

    def test_show_ok_trailing_semicolon(self):
        self.assertEqual(validate_explain_sql("SHOW TABLES;"), "SHOW TABLES")

    def test_rejects_empty(self):
        with self.assertRaises(ExplainRejected):
            validate_explain_sql("  ")

    def test_rejects_stacked(self):
        with self.assertRaises(ExplainRejected):
            validate_explain_sql("SELECT 1; DROP TABLE t")

    def test_rejects_dml(self):
        with self.assertRaises(ExplainRejected):
            validate_explain_sql("UPDATE orders SET x = 1")

    def test_rejects_outfile(self):
        with self.assertRaises(ExplainRejected):
            validate_explain_sql("SELECT * FROM t INTO OUTFILE '/tmp/x'")

    def test_rejects_comments(self):
        with self.assertRaises(ExplainRejected):
            validate_explain_sql("SELECT 1 -- comment")


if __name__ == "__main__":
    unittest.main()
