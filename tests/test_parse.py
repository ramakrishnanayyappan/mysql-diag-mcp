import unittest

from mysql_diag_mcp.parse import parse_innodb_status, parse_tsv, pick_keys, status_map, truncate_field


class TsvTests(unittest.TestCase):
    def test_headers_and_rows(self):
        text = "Id\tUser\tInfo\n1\tapp\tSELECT 1\n2\tzabbix\tSHOW STATUS"
        parsed = parse_tsv(text, max_rows=200)
        self.assertEqual(parsed["columns"], ["Id", "User", "Info"])
        self.assertEqual(parsed["row_count"], 2)
        self.assertFalse(parsed["truncated"])
        self.assertEqual(parsed["rows"][1]["User"], "zabbix")

    def test_extra_tabs_join_last_column(self):
        text = "a\tb\nx\ty\tz"
        parsed = parse_tsv(text, max_rows=10)
        self.assertEqual(parsed["rows"][0]["b"], "y\tz")

    def test_max_rows_truncates(self):
        text = "n\n" + "\n".join(str(i) for i in range(5))
        parsed = parse_tsv(text, max_rows=2)
        self.assertEqual(parsed["row_count"], 2)
        self.assertTrue(parsed["truncated"])
        self.assertEqual(parsed["source_row_count"], 5)

    def test_truncate_field(self):
        rows = [{"Info": "a" * 20}]
        truncate_field(rows, "Info", 8)
        self.assertTrue(rows[0]["Info"].startswith("aaaaaaaa"))
        self.assertIn("truncated", rows[0]["Info"])

    def test_unescapes_embedded_newline_in_field(self):
        # mysql --batch (without --raw) escapes a literal newline within a field
        # as the two characters backslash-n, keeping the row on one output line.
        text = "Id\tInfo\n1\tSELECT 1\\nFROM dual"
        parsed = parse_tsv(text, max_rows=200)
        self.assertEqual(parsed["row_count"], 1)
        self.assertEqual(parsed["rows"][0]["Info"], "SELECT 1\nFROM dual")

    def test_unescapes_tab_and_backslash(self):
        text = "Id\tInfo\n1\ta\\tb\\\\c"
        parsed = parse_tsv(text, max_rows=200)
        self.assertEqual(parsed["rows"][0]["Info"], "a\tb\\c")

    def test_multiline_status_blob_stays_one_row(self):
        # Regression: SHOW ENGINE INNODB STATUS returns one row whose Status
        # column is hundreds of lines of text; --raw would have split it into
        # bogus extra rows since embedded newlines were not escaped.
        text = "Type\tName\tStatus\nInnoDB\t\tLINE1\\nLINE2\\nLINE3"
        parsed = parse_tsv(text, max_rows=200)
        self.assertEqual(parsed["row_count"], 1)
        self.assertEqual(parsed["rows"][0]["Status"], "LINE1\nLINE2\nLINE3")


class InnodbTests(unittest.TestCase):
    def test_sections_and_history_list(self):
        blob = """
=====================================
BACKGROUND THREAD
----------
srv_master_thread loops: 1
----------
SEMAPHORES
----------
OS WAIT ARRAY INFO: reservation count 9
----------
TRANSACTIONS
----------
Trx id counter 123
Purge done for trx's n:o < 100
History list length 4242
LIST OF TRANSACTIONS FOR EACH SESSION:
---TRANSACTION 99, not started
----------
BUFFER POOL AND MEMORY
----------
Total large memory allocated 1000
""".strip()
        parsed = parse_innodb_status(blob, section_limit=8000)
        self.assertEqual(parsed["history_list_length"], 4242)
        self.assertIn("TRANSACTIONS", parsed["sections"])
        self.assertIn("SEMAPHORES", parsed["sections"])
        self.assertNotIn("BACKGROUND THREAD", parsed["sections"])


class StatusMapTests(unittest.TestCase):
    def test_pick_keys_case_insensitive(self):
        rows = [
            {"Variable_name": "Threads_running", "Value": "12"},
            {"Variable_name": "Questions", "Value": "100"},
        ]
        picked = pick_keys(status_map(rows), ("Threads_running", "Slow_queries"))
        self.assertEqual(picked, {"Threads_running": "12"})


if __name__ == "__main__":
    unittest.main()
