# Copyright (c) 2026, Kenya Red Cross Society and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist(allow_guest=True)
def get_articles(
	article_type=None,
	category=None,
	pillar=None,
	is_featured=None,
	limit=None,
	offset=0,
	include_drafts=0
) -> list[dict]:
	"""
	Get published articles with optional filtering and pagination.

	Args:
		article_type: Filter by article type
		category: Filter by category
		pillar: Filter by pillar (Leadership, Branch Development, etc.)
		is_featured: Filter featured articles (1 or 0)
		limit: Number of articles to return
		offset: Starting position for pagination
		include_drafts: Include articles that are Published but not submitted (default: 0)
	"""
	# Build filters - only require status="Published" if include_drafts is enabled
	if int(include_drafts):
		filters = {"status": "Published"}
	else:
		filters = {"status": "Published", "docstatus": 1}

	if article_type:
		filters["article_type"] = article_type
	if category:
		filters["category"] = category
	if pillar:
		filters["pillar"] = pillar
	if is_featured is not None:
		filters["is_featured"] = int(is_featured)

	# Get articles with essential fields
	articles = frappe.get_all(
		"Article",
		filters=filters,
		fields=[
			"name", "title", "slug", "subtitle",
			"summary", "body", "cover_image",
			"article_type", "category",
			"author", "published_on", "read_time",
			"is_featured", "sort_order", "view_count"
		],
		order_by="is_featured desc, published_on desc",
		limit_start=int(offset) if offset else 0,
		limit_page_length=int(limit) if limit else None
	)

	return articles


@frappe.whitelist(allow_guest=True)
def get_article(slug: str) -> dict:
	"""
	Get a single article by slug and increment its view count.
	"""
	name = frappe.db.get_value("Article", {"slug": slug, "status": "Published", "docstatus": 1})
	if not name:
		frappe.throw("Article not found", frappe.DoesNotExistError)

	article = frappe.get_doc("Article", name)

	# Increment view count
	frappe.db.set_value("Article", name, "view_count", article.view_count + 1, update_modified=False)
	frappe.db.commit()

	return article.as_dict()


@frappe.whitelist(methods=["POST"])
def create_article(**kwargs) -> dict:
	kwargs["doctype"] = "Article"
	kwargs.setdefault("author", frappe.session.user)
	doc = frappe.get_doc(kwargs)
	doc.insert()
	return doc.as_dict()


@frappe.whitelist(allow_guest=True)
def get_categories() -> list[dict]:
	"""
	Get all active article categories.
	"""
	categories = frappe.get_all(
		"Localisation Category",
		fields=["name", "category_name", "description"],
		filters={"is_active": 1},
		order_by="category_name asc"
	)
	return categories
