"""Projection data is bounded and cannot become arbitrary SQL/Cypher programs."""
from unittest import TestCase
from app.stores.projections import Snapshot, canonical


class ProjectionSourceTests(TestCase):
    def source(self):
        return {'graph': 'dependencies', 'vertices': [{'key': 'a', 'label': 'Node', 'properties': {'zero': -0.0}},
            {'key': 'b', 'label': 'Other'}], 'edges': [{'source': 'a', 'target': 'b', 'label': 'LINK'}]}

    def test_canonical_hash_survives_jsonb_zero_normalization_and_key_order(self):
        source = self.source()
        first, checksum = canonical(source)
        source['vertices'][0]['properties']['zero'] = 0.0
        second, other = canonical(dict(reversed(list(source.items()))))
        self.assertEqual(checksum, other)
        self.assertEqual(first, second)
        self.assertEqual(len(checksum), 64)

    def test_foreign_endpoints_duplicate_keys_and_program_identifiers_are_rejected(self):
        sources = [
            {**self.source(), 'graph': 'public'},
            {**self.source(), 'graph': 'pg_reserved'},
            {**self.source(), 'vertices': [{'key': 'a', 'label': 'Node`); DROP SCHEMA public CASCADE; //'}]},
            {**self.source(), 'vertices': [{'key': 'a', 'label': 'Node'}, {'key': 'a', 'label': 'Node'}]},
            {**self.source(), 'edges': [{'source': 'a', 'target': 'foreign', 'label': 'LINK'}]},
            {**self.source(), 'state': 'deleted'},
        ]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(ValueError):
                Snapshot.model_validate(source)

    def test_nonfinite_numbers_and_reserved_property_names_are_rejected(self):
        for props in ({'cost': float('nan')}, {'large': 2**64}, {'__platform_source_key': 'spoof'}, {'bad': '\0'}):
            source = self.source()
            source['vertices'][0]['properties'] = props
            with self.subTest(properties=props), self.assertRaises(ValueError):
                canonical(source)
