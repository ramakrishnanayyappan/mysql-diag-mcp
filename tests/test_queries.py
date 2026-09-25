import unittest

from mysql_diag_mcp import queries
from mysql_diag_mcp.capabilities import ServerCapabilities


def caps(version):
    return ServerCapabilities(version, ".".join(str(p) for p in version))


class LockWaitsSqlTests(unittest.TestCase):
    def test_below_8_0_uses_legacy(self):
        self.assertEqual(queries.lock_waits_sql(caps((5, 7, 44))), queries.LOCK_WAITS_LEGACY)

    def test_8_0_and_above_uses_data_locks(self):
        self.assertEqual(queries.lock_waits_sql(caps((8, 0, 0))), queries.LOCK_WAITS_8_0)
        self.assertEqual(queries.lock_waits_sql(caps((8, 4, 2))), queries.LOCK_WAITS_8_0)


class ReplicaStatusSqlTests(unittest.TestCase):
    def test_below_8_0_22_uses_slave_status(self):
        self.assertEqual(queries.replica_status_sql(caps((5, 7, 44))), queries.REPLICA_STATUS_LEGACY)
        self.assertEqual(queries.replica_status_sql(caps((8, 0, 21))), queries.REPLICA_STATUS_LEGACY)

    def test_8_0_22_and_above_uses_replica_status(self):
        self.assertEqual(queries.replica_status_sql(caps((8, 0, 22))), queries.REPLICA_STATUS_8_0)
        self.assertEqual(queries.replica_status_sql(caps((8, 4, 0))), queries.REPLICA_STATUS_8_0)


class ReplicaTopologySqlTests(unittest.TestCase):
    def test_below_8_0_22_uses_slave_hosts(self):
        self.assertEqual(queries.replica_topology_sql(caps((5, 7, 44))), queries.REPLICA_TOPOLOGY_LEGACY)
        self.assertEqual(queries.replica_topology_sql(caps((8, 0, 21))), queries.REPLICA_TOPOLOGY_LEGACY)

    def test_8_0_22_and_above_uses_replicas(self):
        self.assertEqual(queries.replica_topology_sql(caps((8, 0, 22))), queries.REPLICA_TOPOLOGY_8_0)
        self.assertEqual(queries.replica_topology_sql(caps((8, 4, 0))), queries.REPLICA_TOPOLOGY_8_0)


if __name__ == "__main__":
    unittest.main()
