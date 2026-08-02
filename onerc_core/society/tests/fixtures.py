# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Society settings fixtures.

National Society Settings is a Single with mandatory fields, and on a site where
nobody has opened the form it is only partly populated. So `configure()` always
writes them — otherwise every test that touches settings would fail on a
MandatoryError that has nothing to do with what it is testing.

Child tables are set explicitly on every call, never appended to, so one test
cannot inherit another's terminology or toggles.
"""

import frappe

SETTINGS_DOCTYPE = "National Society Settings"

# What `configure()` always writes and `reset()` never clears. The four
# identity fields are here because they are mandatory; `logo` is here because
# the dark-logo fallback needs something to fall back to. The logo is *not*
# mandatory — a society must be able to set its currency and phone rules before
# anybody has a picture to upload — so nothing may infer requiredness from this
# dict. `test_national_society_settings` asserts the blank case directly.
BASELINE = {
	"organization_name": "Test National Society",
	"organization_short_name": "TNS",
	"country": "Kenya",
	"primary_language": "en",
	"logo": "/files/test-society-logo.png",
}


def configure(**overrides):
	"""Populate the settings single and return it.

	IntegrationTestCase rolls back at class teardown, so this does not leak
	beyond the test run.
	"""
	doc = frappe.get_doc(SETTINGS_DOCTYPE)
	doc.update(BASELINE)

	# Cleared unless a test asks for them, so state cannot carry between tests.
	doc.set("terminology", [])
	doc.set("feature_toggles", [])

	doc.update(overrides)
	doc.save()

	return doc


def reset() -> None:
	"""Return the single to its mandatory fields, clearing everything else.

	The list of what to clear is derived from the doctype meta, not enumerated
	here. An enumerated list rots: the first version of this missed the colour
	tokens, and one test's theme leaked into another's assertion about unset
	ones. A field added to the doctype later is cleared without anyone
	remembering to come back here.
	"""
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	cleared = {}

	for field in meta.fields:
		if field.fieldname in BASELINE:
			continue

		# Tables are checked first: they appear in no_value_fields too, so the
		# other order would skip them and leak child rows between tests.
		if field.fieldtype in frappe.model.table_fields:
			cleared[field.fieldname] = []
		elif field.fieldtype not in frappe.model.no_value_fields:
			cleared[field.fieldname] = None

	configure(**cleared)
