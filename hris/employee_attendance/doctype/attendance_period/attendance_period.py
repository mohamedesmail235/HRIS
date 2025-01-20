# -*- coding: utf-8 -*-
# Copyright (c) 2018, Alfahhad and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _

class AttendancePeriod(Document):

	def validate(self):
		max_limit_for_attend = frappe.db.get_single_value("Attendances Settings", "max_limit_for_attendance", cache=False) or 0
		if self.attendance_type == "Shift":
			if int(self.attendance_permissibility) > int(max_limit_for_attend):
				frappe.throw(_("Attendance Permissibility can not exceed Max Limit For Attend in settings"))


@frappe.whitelist()
def get_events(start, end, filters=None):
	events = []
	from frappe.desk.reportview import get_filters_cond
	conditions = get_filters_cond("Mission", filters, [])
	add_attendance_period(events, start, end, conditions)
	return events

def add_attendance_period(events, start, end, match_conditions=None):
	query = """select `tabAttendance Period`.name, start_date, end_date, 
		attendance_type,color, docstatus
		from `tabAttendance Period`
		where
		start_date <= %(end)s and end_date >= %(start)s <= end_date
		and `tabAttendance Period`.docstatus < 2 """
	if match_conditions:
		query += match_conditions

	for d in frappe.db.sql(query, {"start":start, "end": end}, as_dict=True):
		e = {
			"name": d.name,
			"doctype": "Attendance Period",
			"from_date": d.from_date,
			"to_date": d.to_date,
			"title": str(d.name),
			"attendance_type":d.attendance_type,
			"docstatus": d.docstatus,
			"color":d.color,
		}
		if e not in events:
			events.append(e)
