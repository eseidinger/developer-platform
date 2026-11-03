from unittest import TestCase
from uuid import uuid4

from app.stores import catalog
from app.stores.hugegraph_access import authorize


class HugeGraphAccessTests(TestCase):
    def setUp(self):
        self.lease = {"resource_id": str(uuid4()), "mode": "read-only"}
        self.prefix = "/graphs/" + catalog.identifier(self.lease["resource_id"])

    def test_reader_is_limited_to_its_graph_data_and_schema(self):
        for method, path in [
            (b"GET", self.prefix + "/graph/vertices"),
            (b"GET", self.prefix + "/graph/edges?limit=10"),
            (b"GET", self.prefix + "/schema/propertykeys"),
            (b"GET", self.prefix + "/schema/vertexlabels/person"),
        ]:
            with self.subTest(method=method, path=path):
                authorize(method, path.encode(), self.lease)

    def test_reader_and_writer_cannot_reach_other_graphs_or_admin_apis(self):
        denied = [
            (b"GET", "/graphs"),
            (b"GET", "/graphs/hugegraph/graph/vertices"),
            (b"GET", self.prefix),
            (b"GET", self.prefix + "/conf"),
            (b"GET", self.prefix + "/graph/vertices/../edges"),
            (b"GET", self.prefix + "/graph/vertices%2fother"),
            (b"GET", self.prefix + "/graph/vertices%252fother"),
            (b"GET", self.prefix + "/graph//vertices"),
            (b"GET", "/graphspaces/DEFAULT" + self.prefix + "/graph/vertices"),
            (b"POST", self.prefix + "/gremlin"),
            (b"POST", self.prefix + "/tasks"),
            (b"GET", "/auth/groups"),
            (b"GET", self.prefix + "/schema/propertykeys/x/rebuild"),
        ]
        for mode in ("read-only", "read-write"):
            self.lease["mode"] = mode
            for method, path in denied:
                with (
                    self.subTest(mode=mode, method=method, path=path),
                    self.assertRaises(ValueError),
                ):
                    authorize(method, path.encode(), self.lease)

    def test_writer_can_change_data_and_schema_but_reader_cannot(self):
        for method, path in [
            (b"POST", self.prefix + "/graph/vertices"),
            (b"PUT", self.prefix + "/graph/vertices/1"),
            (b"DELETE", self.prefix + "/graph/edges/1"),
            (b"POST", self.prefix + "/schema/propertykeys"),
            (b"DELETE", self.prefix + "/schema/indexlabels/by_name"),
        ]:
            with self.subTest(method=method, path=path):
                with self.assertRaises(ValueError):
                    authorize(method, path.encode(), self.lease)
                self.lease["mode"] = "read-write"
                authorize(method, path.encode(), self.lease)
                self.lease["mode"] = "read-only"
