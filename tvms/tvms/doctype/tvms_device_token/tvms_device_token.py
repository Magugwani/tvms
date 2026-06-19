{
 "actions": [],
 "allow_rename": 0,
 "autoname": "format:TVMS-DEV-{####}",
 "creation": "2026-06-18 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "section_basic",
  "user",
  "platform",
  "device_name",
  "column_break_1",
  "active",
  "registered_at",
  "last_used",
  "section_token",
  "token"
 ],
 "fields": [
  {
   "fieldname": "section_basic",
   "fieldtype": "Section Break",
   "label": "Device"
  },
  {
   "fieldname": "user",
   "fieldtype": "Link",
   "options": "User",
   "label": "User",
   "reqd": 1,
   "in_list_view": 1,
   "in_standard_filter": 1
  },
  {
   "fieldname": "platform",
   "fieldtype": "Select",
   "options": "android\nios\nweb",
   "label": "Platform",
   "default": "android",
   "in_list_view": 1,
   "in_standard_filter": 1
  },
  {
   "fieldname": "device_name",
   "fieldtype": "Data",
   "label": "Device Label",
   "description": "Optional — e.g. 'Pixel 7', 'iPhone 14'"
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "default": "1",
   "fieldname": "active",
   "fieldtype": "Check",
   "label": "Active",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "description": "Automatically set to 0 when FCM reports the token as invalid"
  },
  {
   "fieldname": "registered_at",
   "fieldtype": "Datetime",
   "label": "Registered At",
   "read_only": 1
  },
  {
   "fieldname": "last_used",
   "fieldtype": "Datetime",
   "label": "Last Used",
   "read_only": 1,
   "description": "Updated each time a push is successfully delivered"
  },
  {
   "fieldname": "section_token",
   "fieldtype": "Section Break",
   "label": "Token",
   "collapsible": 1
  },
  {
   "fieldname": "token",
   "fieldtype": "Long Text",
   "label": "FCM/APNs Token",
   "reqd": 1,
   "description": "The device's push registration token. Do not edit manually — set via the register_device_token API."
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-06-18 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "tvms",
 "name": "TVMS Device Token",
 "naming_rule": "Expression",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1, "delete": 1, "email": 1, "export": 1, "print": 1,
   "read": 1, "report": 1, "role": "System Manager", "share": 1, "write": 1
  },
  {
   "create": 1, "delete": 1, "email": 1, "export": 1, "print": 1,
   "read": 1, "report": 1, "role": "Administrator", "share": 1, "write": 1
  }
 ],
 "row_format": "Dynamic",
 "rows_threshold_for_grid_search": 20,
 "sort_field": "last_used",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}