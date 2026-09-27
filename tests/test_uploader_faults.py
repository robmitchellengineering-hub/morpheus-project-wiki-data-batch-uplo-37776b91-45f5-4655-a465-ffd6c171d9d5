"""Behaviour tests for the uploader's known faults.

Run with:  python -m unittest discover -s tests -v
Standard library only (no pytest), so the build can run them with one step after
the requirements are installed.

Each test corresponds to a fault that shipped: a duplicate checker that raised
`AttributeError` on pandas 2.x and was never noticed, times and quantities written
as strings and rejected by Wikidata, an AI mapping call that reported a server
error as "no suggestions", and a self-test that skipped the app's two largest
modules.
"""
import importlib
import os
import sys
import unittest
from unittest import mock

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import diagnostics  # noqa: E402
from core import morpheus_connect  # noqa: E402
from core.duplicate_checker import find_duplicate_rows_within_batch  # noqa: E402
from core.reference_tables import DEFAULT_PROPERTIES, datatype_map  # noqa: E402
from core.uploader import _parse_time_value, _value_to_statement  # noqa: E402
from wikidataintegrator import wdi_core  # noqa: E402


class DuplicateRowsTest(unittest.TestCase):
    """Fault: `Index.groupby(...).apply(list)` is not pandas 2.x."""

    def setUp(self):
        self.df = pd.DataFrame({
            'name': ['Alpha', 'Alpha', 'Beta', 'Gamma'],
            'country': ['Q30', 'Q30', 'Q145', 'Q30'],
        })
        self.mapping = {'name': 'P31', 'country': 'P17'}

    def test_identical_rows_are_grouped(self):
        self.assertEqual(find_duplicate_rows_within_batch(self.df, self.mapping), [[0, 1]])

    def test_a_clean_frame_reports_nothing(self):
        clean = pd.DataFrame({'name': ['Alpha', 'Beta'], 'country': ['Q30', 'Q145']})
        self.assertEqual(find_duplicate_rows_within_batch(clean, self.mapping), [])

    def test_groups_are_original_index_labels_not_positions(self):
        indexed = self.df.set_index(pd.Index(['r1', 'r2', 'r3', 'r4']))
        self.assertEqual(find_duplicate_rows_within_batch(indexed, self.mapping), [['r1', 'r2']])

    def test_rows_with_a_missing_mapped_value_are_ignored(self):
        partial = pd.DataFrame({'name': ['Alpha', 'Alpha'], 'country': [None, None]})
        self.assertEqual(find_duplicate_rows_within_batch(partial, self.mapping), [])

    def test_no_mapped_columns_is_not_an_error(self):
        self.assertEqual(find_duplicate_rows_within_batch(self.df, {'name': None}), [])


class DatatypeTest(unittest.TestCase):
    """Fault: every value that was not an item, URL or coordinate became a string."""

    def test_a_declared_time_becomes_a_time_statement(self):
        stmt = _value_to_statement('P571', '1900', 'time')
        self.assertIsInstance(stmt, wdi_core.WDTime)
        self.assertEqual(stmt.value[0], '+1900-01-01T00:00:00Z')
        self.assertEqual(stmt.value[2], 9)  # year precision

    def test_time_precision_follows_how_much_of_the_date_is_given(self):
        self.assertEqual(_value_to_statement('P571', '1900', 'time').value[2], 9)
        self.assertEqual(_value_to_statement('P571', '1900-05', 'time').value[2], 10)
        day = _value_to_statement('P571', '1900-05-17', 'time')
        self.assertEqual(day.value[0], '+1900-05-17T00:00:00Z')
        self.assertEqual(day.value[2], 11)

    def test_a_year_read_out_of_excel_as_a_float_still_works(self):
        stmt = _value_to_statement('P571', 1900.0, 'time')
        self.assertIsInstance(stmt, wdi_core.WDTime)
        self.assertEqual(stmt.value[0], '+1900-01-01T00:00:00Z')

    def test_an_already_wikidata_shaped_time_passes_through(self):
        stmt = _value_to_statement('P571', '+1900-05-17T00:00:00Z', 'time')
        self.assertEqual(stmt.value[0], '+1900-05-17T00:00:00Z')

    def test_a_declared_quantity_becomes_a_quantity_statement(self):
        stmt = _value_to_statement('P1082', '2850', 'quantity')
        self.assertIsInstance(stmt, wdi_core.WDQuantity)
        self.assertEqual(stmt.value[0], '+2850')

    def test_a_quantity_from_excel_does_not_become_a_float_string(self):
        stmt = _value_to_statement('P1082', '2850.0', 'quantity')
        self.assertEqual(stmt.value[0], '+2850')

    def test_other_declared_datatypes(self):
        self.assertIsInstance(_value_to_statement('P18', 'Example.jpg', 'commonsMedia'), wdi_core.WDCommonsMedia)
        self.assertIsInstance(_value_to_statement('P856', 'https://example.org', 'url'), wdi_core.WDUrl)
        self.assertIsInstance(_value_to_statement('P31', 'Q5', 'wikibase-item'), wdi_core.WDItemID)
        self.assertIsInstance(_value_to_statement('P123', 'abc-1', 'external-id'), wdi_core.WDExternalID)
        self.assertIsInstance(_value_to_statement('P1476', 'A title', 'string'), wdi_core.WDString)

    def test_a_coordinate_declared_on_any_property_is_still_a_coordinate(self):
        stmt = _value_to_statement('P1259', '51.5,-0.12', 'globe-coordinate')
        self.assertIsInstance(stmt, wdi_core.WDGlobeCoordinate)

    def test_an_unusable_time_falls_back_rather_than_dropping_the_value(self):
        stmt = _value_to_statement('P571', 'sometime in spring', 'time')
        self.assertIsInstance(stmt, wdi_core.WDString)

    def test_without_a_datatype_the_old_inference_still_holds(self):
        # Tables predating the `datatype` column must keep working.
        self.assertIsInstance(_value_to_statement('P31', 'Q5'), wdi_core.WDItemID)
        self.assertIsInstance(_value_to_statement('P856', 'https://example.org'), wdi_core.WDUrl)
        self.assertIsInstance(_value_to_statement('P1476', 'A title'), wdi_core.WDString)
        self.assertIsInstance(_value_to_statement('P625', '51.5,-0.12'), wdi_core.WDGlobeCoordinate)

    def test_empty_values_produce_nothing(self):
        for value in ('', None, float('nan')):
            self.assertIsNone(_value_to_statement('P571', value, 'time'))

    def test_parse_time_value_rejects_a_non_date(self):
        self.assertIsNone(_parse_time_value('not a date'))


class ReferenceTableTest(unittest.TestCase):

    def test_the_default_table_declares_a_datatype_for_every_property(self):
        for row in DEFAULT_PROPERTIES:
            self.assertIn('datatype', row, row)
            self.assertTrue(row['datatype'], row)

    def test_the_declared_types_match_wikidata_for_the_known_traps(self):
        by_id = {r['property_id']: r['datatype'] for r in DEFAULT_PROPERTIES}
        self.assertEqual(by_id['P571'], 'time')          # inception
        self.assertEqual(by_id['P1082'] if 'P1082' in by_id else 'quantity', 'quantity')

    def test_datatype_map_reads_the_column(self):
        df = pd.DataFrame([{'property_id': 'P571', 'label': 'inception', 'datatype': 'time'}])
        self.assertEqual(datatype_map(df), {'P571': 'time'})

    def test_datatype_map_is_empty_for_a_table_without_the_column(self):
        df = pd.DataFrame([{'property_id': 'P571', 'label': 'inception'}])
        self.assertEqual(datatype_map(df), {})

    def test_datatype_map_ignores_blank_cells(self):
        df = pd.DataFrame([
            {'property_id': 'P571', 'datatype': 'time'},
            {'property_id': 'P17', 'datatype': ''},
            {'property_id': '', 'datatype': 'string'},
        ])
        self.assertEqual(datatype_map(df), {'P571': 'time'})


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} Server Error")
            err.response = self
            raise err

    def json(self):
        return self._payload


class MorpheusMappingErrorTest(unittest.TestCase):
    """Fault: HTTP failures reached the operator as 'did not return suggestions'."""

    def test_a_server_error_is_named(self):
        with mock.patch.object(morpheus_connect.requests, 'post',
                               return_value=_FakeResponse(500, text='OUTPUT_TRUNCATED')):
            result = morpheus_connect.suggest_mappings_with_morpheus(['a'], [['1']], 'dvc_token')
        self.assertEqual(result.mappings, [])
        self.assertIn('500', result.error)
        self.assertIn('OUTPUT_TRUNCATED', result.error)

    def test_a_connection_failure_is_named(self):
        with mock.patch.object(morpheus_connect.requests, 'post',
                               side_effect=requests.ConnectionError('name resolution failed')):
            result = morpheus_connect.suggest_mappings_with_morpheus(['a'], [['1']], 'dvc_token')
        self.assertEqual(result.mappings, [])
        self.assertIn('Could not reach Morpheus', result.error)
        self.assertIn('ConnectionError', result.error)

    def test_a_successful_call_reports_no_error(self):
        payload = {'mappings': [{'column': 'a', 'label': 'inception'}]}
        with mock.patch.object(morpheus_connect.requests, 'post', return_value=_FakeResponse(200, payload)):
            result = morpheus_connect.suggest_mappings_with_morpheus(['a'], [['1']], 'dvc_token')
        self.assertEqual(result.mappings, [{'column': 'a', 'label': 'inception'}])
        self.assertIsNone(result.error)

    def test_without_a_token_it_says_so(self):
        result = morpheus_connect.suggest_mappings_with_morpheus(['a'], [['1']], None)
        self.assertEqual(result.mappings, [])
        self.assertIn('Not connected', result.error)

    def test_it_never_raises(self):
        for failure in (RuntimeError('boom'), ValueError('bad'), requests.Timeout('slow')):
            with mock.patch.object(morpheus_connect.requests, 'post', side_effect=failure):
                result = morpheus_connect.suggest_mappings_with_morpheus(['a'], [['1']], 'dvc_token')
            self.assertEqual(result.mappings, [])
            self.assertTrue(result.error)


class DiagnosticCoverageTest(unittest.TestCase):
    """Fault: the self-test skipped the two largest modules in the app."""

    def _modules_the_self_test_imports(self):
        asked = []
        real = importlib.import_module

        def spy(name, *args, **kwargs):
            asked.append(name)
            return real(name, *args, **kwargs)

        with mock.patch.object(importlib, 'import_module', side_effect=spy):
            diagnostics._run_import_tests()
        return set(asked)

    def test_every_shipped_module_is_import_tested(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        expected = set()
        for package in ('core', 'ui'):
            for entry in os.listdir(os.path.join(root, package)):
                if entry.endswith('.py') and entry != '__init__.py':
                    expected.add(f"{package}.{entry[:-3]}")
        # diagnostics is the thing doing the testing; everything else must be covered.
        expected.discard('core.diagnostics')
        missing = expected - self._modules_the_self_test_imports()
        self.assertEqual(missing, set(), f"self-test does not import: {sorted(missing)}")

    def test_the_two_largest_modules_are_named_explicitly(self):
        # Named directly as well, so the intent survives a refactor of the scan above.
        imported = self._modules_the_self_test_imports()
        self.assertIn('core.commons_uploader', imported)
        self.assertIn('ui.commons_upload_dialog', imported)


if __name__ == '__main__':
    unittest.main(verbosity=2)
