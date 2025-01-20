// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.views.calendar["Permission"] = {
	field_map: {
		"start": "for_date",
		"id": "name",
		"title": "title",
		"permission_type" : "permission_type"
	},
	options: {
		header: {
			left: 'prev,next today',
			center: 'title',
			right: 'month'
		}
	},
	get_events_method:"attendances.attendances.doctype.permission.permission.get_events"

}