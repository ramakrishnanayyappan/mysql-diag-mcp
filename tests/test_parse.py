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
