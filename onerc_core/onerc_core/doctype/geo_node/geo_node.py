import frappe
from frappe.utils.nestedset import NestedSet


class GeoNode(NestedSet):
	nsm_parent_field = "parent_geo_node"

	def autoname(self):
		self.name = f"{self.geo_level}-{self.geo_node_name}"

	def before_save(self):
		self.set_ancestor_nodes()

	def set_ancestor_nodes(self):
		self.level_1_node = None
		self.level_2_node = None
		self.level_3_node = None

		if not self.parent_geo_node:
			return

		geo_level = frappe.get_doc("Geo Level", self.geo_level)
		order = geo_level.geo_level_order

		if order == 2:
			self.level_1_node = self.parent_geo_node

		elif order == 3:
			self.level_2_node = self.parent_geo_node
			parent = frappe.get_doc("Geo Node", self.parent_geo_node)
			if parent.parent_geo_node:
				self.level_1_node = parent.parent_geo_node

		elif order == 4:
			self.level_3_node = self.parent_geo_node
			parent = frappe.get_doc("Geo Node", self.parent_geo_node)
			if parent.parent_geo_node:
				self.level_2_node = parent.parent_geo_node
				grandparent = frappe.get_doc("Geo Node", parent.parent_geo_node)
				if grandparent.parent_geo_node:
					self.level_1_node = grandparent.parent_geo_node
