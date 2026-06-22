# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe


def get_context(context):
	"""Context for tvms_changes page."""
	context.no_cache = 1
	return context
