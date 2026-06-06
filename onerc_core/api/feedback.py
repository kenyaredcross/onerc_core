import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def get_feedback_types():
	"""Return all feedback types available for submission"""
	return frappe.get_all(
		"Feedback Type",
		fields=["name", "title", "description"],
		order_by="title asc",
	)


@frappe.whitelist(allow_guest=True)
def submit_feedback(feedback_type, message, subject=None, email=None):
	"""Create a new Feedback record"""
	if not message or not message.strip():
		frappe.throw(_("Message is required."))

	if not frappe.db.exists("Feedback Type", feedback_type):
		frappe.throw(_("Invalid feedback type."))

	doc = frappe.new_doc("Feedback")
	doc.feedback_type = feedback_type
	doc.message = message.strip()
	doc.subject = (subject or "").strip()

	if frappe.session.user and frappe.session.user != "Guest":
		doc.submitted_by = frappe.session.user
	elif email:
		doc.email = email

	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_feedback_list(status=None, feedback_type=None, page=1, page_size=20):
	"""Return a paginated list of feedback records"""
	frappe.only_for(["System Manager", "HQ Admin", "EOC Agent"])

	page = max(1, int(page))
	page_size = min(100, max(1, int(page_size)))

	filters = {}
	if status:
		allowed_statuses = ("Open", "Reviewed", "Resolved", "Closed")
		if status not in allowed_statuses:
			frappe.throw(_("Invalid status filter."))
		filters["status"] = status
	if feedback_type:
		filters["feedback_type"] = feedback_type

	total = frappe.db.count("Feedback", filters=filters)
	items = frappe.get_all(
		"Feedback",
		filters=filters,
		fields=[
			"name", "subject", "feedback_type", "status",
			"submitted_by", "full_name", "email",
			"submission_date", "reviewed_by", "reviewed_on",
		],
		order_by="submission_date desc",
		limit_start=(page - 1) * page_size,
		limit_page_length=page_size,
	)

	return {"total": total, "page": page, "page_size": page_size, "items": items}


@frappe.whitelist()
def update_feedback(name, status, reviewer_notes=None):
	"""Update the status of a Feedback record"""
	frappe.only_for(["System Manager", "HQ Admin"])

	allowed_statuses = ("Reviewed", "Resolved", "Closed")
	if status not in allowed_statuses:
		frappe.throw(
			_("Invalid status. Allowed values: {0}").format(", ".join(allowed_statuses))
		)

	doc = frappe.get_doc("Feedback", name)
	doc.status = status
	doc.reviewed_by = frappe.session.user
	doc.reviewed_on = frappe.utils.now_datetime()
	if reviewer_notes is not None:
		doc.reviewer_notes = reviewer_notes

	doc.save()
	frappe.db.commit()

	return {"name": doc.name, "status": doc.status}
