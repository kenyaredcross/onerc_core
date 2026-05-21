import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def update_organization_settings(**kwargs):
	"""
	Update organization settings in National Society Settings.
	"""

	try:
		settings = frappe.get_single("National Society Settings")

		# Update fields that are provided
		if kwargs.get("organization_name"):
			settings.organization_name = kwargs.get("organization_name")
		if kwargs.get("organization_short_name"):
			settings.organization_short_name = kwargs.get("organization_short_name")
		if kwargs.get("logo"):
			settings.logo = kwargs.get("logo")

		settings.save()
		frappe.db.commit()

		return {
			"success": True,
			"message": _("Organization settings updated successfully")
		}

	except Exception as e:
		frappe.log_error(f"Error updating organization settings: {str(e)}")
		return {
			"success": False,
			"message": _("Failed to update organization settings"),
			"error": str(e)
		}


@frappe.whitelist(allow_guest=True)
def get_organization_settings():
	"""
	Get organization settings from National Society Settings.
	Returns organization name, logo, colors, and other branding info.
	"""
	try:
		# National Society Settings is a single DocType
		if not frappe.db.exists("DocType", "National Society Settings"):
			return {
				"organization_name": None,
				"organization_short_name": None,
				"logo": None,
				"primary_color": None,
				"secondary_color": None,
				"accent_color": None,
			}

		settings = frappe.get_single("National Society Settings")

		return {
			"organization_name": settings.organization_name,
			"organization_short_name": settings.organization_short_name,
			"logo": settings.logo,
			"primary_color": settings.primary_color,
			"secondary_color": settings.secondary_color,
			"accent_color": settings.accent_color,
			"background": settings.background,
			"country": settings.country,
			"primary_language": settings.primary_language,
			"official_website": settings.official_website,
			"telephone": settings.telephone,
			"physical_address": settings.physical_address,
		}

	except Exception as e:
		frappe.log_error(f"Error fetching organization settings: {str(e)}")
		# Return None values if settings don't exist
		return {
			"organization_name": None,
			"organization_short_name": None,
			"logo": None,
			"primary_color": None,
			"secondary_color": None,
			"accent_color": None,
		}
