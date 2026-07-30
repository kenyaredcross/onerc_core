# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Identity fixtures.

Satellites live in other apps, and the apps that will own them do not exist yet.
So these tests stand a core doctype in for one: a ToDo plays the part of a
Volunteer record. That is not a shortcut — it is the point. Core must be able to
index and reconcile a satellite it knows nothing about, and a satellite it could
not possibly have been written against proves it.

Providers and capability resolvers are exposed here as module-level functions
with real dotted paths, because that is what a hook holds in production. Tests
stage what a provider should say, then register its path — so the framework's
own `frappe.get_attr` resolution is under test too, not bypassed.
"""

import frappe

TEST_PREFIX = "ID-TEST"

# The stand-in satellite. Any doctype would do, which is the property under test.
SATELLITE_DOCTYPE = "ToDo"

_MODULE = "onerc_core.identity.tests.fixtures"

PROVIDER_PATHS = {
	"first": f"{_MODULE}.provide_first",
	"second": f"{_MODULE}.provide_second",
	"broken": f"{_MODULE}.provide_broken",
	"malformed": f"{_MODULE}.provide_malformed",
}

RESOLVER_GRANT = f"{_MODULE}.resolve_grant"
RESOLVER_DENY = f"{_MODULE}.resolve_deny"

_staged: dict[str, dict] = {}


def make_affiliation_type(
	key: str,
	label: str | None = None,
	*,
	requires_gated_read: bool = False,
	gating_capability: str | None = None,
	is_active: bool = True,
) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Affiliation Type",
			"affiliation_type_key": f"{TEST_PREFIX}-{key}",
			"affiliation_type_name": label or key.title(),
			"requires_gated_read": int(requires_gated_read),
			"gating_capability": gating_capability,
			"is_active": int(is_active),
		}
	)
	doc.insert()

	return doc.name


def make_profile(first_name: str = "Asha", last_name: str = "Wanjiru", **kwargs) -> str:
	slug = f"{first_name}.{last_name}".lower()
	doc = frappe.get_doc(
		{
			"doctype": "Red Profile",
			"first_name": first_name,
			"last_name": last_name,
			"email": kwargs.pop("email", f"{slug}.{frappe.generate_hash(length=6)}@example.test"),
			**kwargs,
		}
	)
	doc.insert()

	return doc.name


def make_satellite(subject: str = "Volunteer record") -> str:
	"""Create a stand-in satellite record for an affiliation to point at."""
	doc = frappe.get_doc({"doctype": SATELLITE_DOCTYPE, "description": f"{TEST_PREFIX} {subject}"})
	doc.insert()

	return doc.name


def stage_provider(slot: str, reference_doctypes: list[str], affiliations: list[dict] | None = None) -> str:
	"""Say what a provider will declare, and return its dotted path."""
	_staged[slot] = {
		"reference_doctypes": list(reference_doctypes),
		"affiliations": list(affiliations or []),
	}

	return PROVIDER_PATHS[slot]


def clear_staged() -> None:
	_staged.clear()


def provide_first(profile: str) -> dict:
	return _staged["first"]


def provide_second(profile: str) -> dict:
	return _staged["second"]


def provide_broken(profile: str) -> dict:
	raise RuntimeError("satellite app is broken")


def provide_malformed(profile: str):
	return ["not", "a", "dict"]


def resolve_grant(user: str, capability: str) -> bool:
	return True


def resolve_deny(user: str, capability: str) -> bool:
	return False


def reset() -> None:
	"""Drop fixture rows left behind by a run that committed."""
	clear_staged()

	for profile in frappe.get_all("Red Profile", filters={"email": ("like", "%@example.test")}, pluck="name"):
		frappe.delete_doc("Red Profile", profile, force=True)

	for affiliation_type in frappe.get_all(
		"Affiliation Type", filters={"name": ("like", f"{TEST_PREFIX}-%")}, pluck="name"
	):
		frappe.delete_doc("Affiliation Type", affiliation_type, force=True)

	for satellite in frappe.get_all(
		SATELLITE_DOCTYPE, filters={"description": ("like", f"{TEST_PREFIX}%")}, pluck="name"
	):
		frappe.delete_doc(SATELLITE_DOCTYPE, satellite, force=True)
