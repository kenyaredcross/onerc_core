import frappe


@frappe.whitelist(allow_guest=True)
def get_geo_levels():
	return frappe.get_all(
		"Geo Level",
		filters={"is_active": 1},
		fields=["name", "geo_level_name", "geo_level_key", "geo_level_order", "is_lowest_level"],
		order_by="geo_level_order asc"
	)


@frappe.whitelist(allow_guest=True)
def get_geo_nodes(geo_level=None, parent_geo_node=None, search=None):
	filters = {"is_active": 1}
	if geo_level:
		filters["geo_level"] = geo_level
	if parent_geo_node:
		filters["parent_geo_node"] = parent_geo_node

	or_filters = None
	if search:
		or_filters = [
			["geo_node_name", "like", f"%{search}%"],
			["geo_code", "like", f"%{search}%"]
		]

	return frappe.get_all(
		"Geo Node",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "geo_node_name", "geo_level", "geo_code",
				"parent_geo_node", "level_1_node", "level_2_node", "level_3_node",
				"latitude", "longitude"],
		order_by="geo_node_name asc",
		limit=200
	)


@frappe.whitelist(allow_guest=True)
def verify_member(vol_id):
	volunteer = frappe.db.get_value(
		"Volunteer",
		vol_id,
		["full_name", "photo", "volunteer_status"],
		as_dict=True
	)
	if not volunteer:
		return {"status": "not_found"}

	member = frappe.db.get_value(
		"OneRC Member",
		{"volunteer": vol_id},
		["name", "member_name"],
		as_dict=True
	)
	if not member:
		return {"status": "not_a_member", "name": volunteer.full_name}

	subscription = frappe.db.get_value(
		"OneRC Member Subscription",
		{"member": member.name, "status": ["in", ["Active", "Expired"]]},
		["name", "plan", "status", "from_date", "to_date"],
		as_dict=True,
		order_by="to_date desc"
	)
	if not subscription:
		return {"status": "no_subscription", "name": volunteer.full_name}

	return {
		"status": subscription.status,
		"name": volunteer.full_name,
		"photo": volunteer.photo,
		"plan": subscription.plan,
		"from_date": str(subscription.from_date),
		"to_date": str(subscription.to_date),
		"vol_id": vol_id
	}
