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
			"article_type", "category", "status", "docstatus",
			"author", "published_on", "read_time",
			"is_featured", "sort_order", "view_count",
			"like_count", "comment_count"
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


@frappe.whitelist()
def toggle_like(article_slug: str) -> dict:
	"""
	Toggle like status for an article. Creates or removes like record.
	Returns the new like status and updated like count.
	"""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Please login to like articles", frappe.PermissionError)

	# Get article name from slug
	article_name = frappe.db.get_value("Article", {"slug": article_slug, "status": "Published", "docstatus": 1})
	if not article_name:
		frappe.throw("Article not found", frappe.DoesNotExistError)

	# Check if user already liked this article
	existing_like = frappe.db.exists("Article Like", {"article": article_name, "user": user})

	# Get current like count
	current_like_count = frappe.db.get_value("Article", article_name, "like_count") or 0

	if existing_like:
		# Unlike: remove the like record
		frappe.delete_doc("Article Like", existing_like, ignore_permissions=True)
		liked = False

		# Decrement like count using db.set_value to avoid validation
		new_count = max(0, current_like_count - 1)
		frappe.db.set_value("Article", article_name, "like_count", new_count, update_modified=False)
	else:
		# Like: create a new like record
		like_doc = frappe.get_doc({
			"doctype": "Article Like",
			"article": article_name,
			"user": user
		})
		like_doc.insert(ignore_permissions=True)
		liked = True

		# Increment like count using db.set_value to avoid validation
		new_count = current_like_count + 1
		frappe.db.set_value("Article", article_name, "like_count", new_count, update_modified=False)

	frappe.db.commit()

	return {
		"liked": liked,
		"like_count": new_count
	}


@frappe.whitelist(allow_guest=True)
def get_article_engagement(article_slug: str) -> dict:
	"""
	Get engagement metrics (likes, comments) for an article.
	"""
	article_name = frappe.db.get_value("Article", {"slug": article_slug, "status": "Published", "docstatus": 1})
	if not article_name:
		frappe.throw("Article not found", frappe.DoesNotExistError)

	article = frappe.get_doc("Article", article_name)

	# Check if current user liked this article
	liked = False
	if frappe.session.user != "Guest":
		liked = frappe.db.exists("Article Like", {"article": article_name, "user": frappe.session.user}) is not None

	# Get actual comment count from Comment doctype
	comment_count = frappe.db.count("Comment", filters={
		"reference_doctype": "Article",
		"reference_name": article_name,
		"comment_type": "Comment"
	})

	return {
		"like_count": article.like_count or 0,
		"comment_count": comment_count,
		"liked": liked
	}
