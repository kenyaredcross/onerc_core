# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Keep the existing person value while giving citizenship its explicit name."""
	if not frappe.db.table_exists("Red Profile"):
		return

	columns = set(frappe.db.get_table_columns("Red Profile"))

	if "nationality" in columns and "country_of_citizenship" not in columns:
		# This is a pre-model-sync patch: the JSON already names the new field but
		# Frappe's current metadata still names the old one. `rename_field()` is
		# explicitly post-sync and cannot resolve the new field here, while the
		# database operation is exactly the transition this moment needs.
		frappe.db.rename_column("Red Profile", "nationality", "country_of_citizenship")
