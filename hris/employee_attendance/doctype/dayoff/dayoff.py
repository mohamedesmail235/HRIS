# Copyright (c) 2022, MiM and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, formatdate, get_datetime, getdate, nowdate
from erpnext.buying.doctype.supplier_scorecard.supplier_scorecard import daterange

class DayOff(Document):
	pass

	# def on_submit(self):
	# 	for dt in daterange(getdate(self.from_date), getdate(self.to_date)):
	# 		date = dt.strftime("%Y-%m-%d")
	# 		doc = frappe.new_doc("Attendance")
	# 		doc.employee = self.employee
	# 		doc.attendance_date = date
	# 		doc.status = "DayOff"
	# 		doc.attend_time = ""
	# 		doc.leave_time = ""
	# 		doc.insert(ignore_permissions=True)
	# 		doc.submit()

@frappe.whitelist()
def get_events(start, end, filters=None):
	events = []

	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user})

	if not employee:
		return events

	from frappe.desk.reportview import get_filters_cond
	conditions = get_filters_cond("DayOff", filters, [])
	add_dayoff(events, start, end, conditions=conditions)
	return events

def add_dayoff(events, start, end, conditions=None):
	query = """select name, posting_date, employee
		from `tabDayOff` where
		posting_date between %(from_date)s and %(to_date)s
		and docstatus < 2"""
	if conditions:
		query += conditions

	for d in frappe.db.sql(query, {"from_date":start, "to_date":end}, as_dict=True):
		e = {
			"name": d.name,
			"doctype": "DayOff",
			"start": d.posting_date,
			"end": d.posting_date,
			"title": cstr(d.employee),
			"docstatus": d.docstatus
		}
		if e not in events:
			events.append(e)

