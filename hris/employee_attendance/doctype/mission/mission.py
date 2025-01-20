# -*- coding: utf-8 -*-
# Copyright (c) 2018, Alfahhad and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from erpnext.buying.doctype.supplier_scorecard.supplier_scorecard import daterange
# from erpnext.setup.doctype.employee.employee import OverlapError
from frappe.model.document import Document
from frappe.utils import cstr, getdate, nowdate, formatdate
from frappe import _

class OverlapError(frappe.ValidationError): pass

class Mission(Document):
	def on_submit(self):
		self.update_attendance()

	def on_cancel(self):
		self.del_attendance()

	def del_attendance(self):
		attendance = frappe.db.sql("""select name from `tabAttendance` where employee = %s\
			and (attendance_date between %s and %s) and docstatus < 2""",(self.employee, self.from_date, self.to_date), as_dict=1)

		status = "Mission"
		if attendance:
			for d in attendance:
				frappe.db.sql("""delete from `tabAttendance` where status = %s and name = %s""",(status, d.name))

	def update_attendance(self):
		attendance = frappe.db.sql("""select name from `tabAttendance` where employee = %s\
			and (attendance_date between %s and %s) and docstatus < 2""",(self.employee, self.from_date, self.to_date), as_dict=1)

		status = "Mission"
		if attendance:
			for d in attendance:
				frappe.db.sql("""update `tabAttendance` set status = %s , attend_time = NULL , leave_time=NULL, delay_minutes=0 where name = %s""",(status, d.name))

		else:
			for dt in daterange(getdate(self.from_date), getdate(self.to_date)):
				date = dt.strftime("%Y-%m-%d")
				doc = frappe.new_doc("Attendance")
				doc.employee = self.employee
				doc.attendance_date = date
				doc.status = status
				doc.attend_time = ""
				doc.leave_time = ""
				doc.insert(ignore_permissions=True)
				doc.submit()

	def validate(self):
		self.validate_dates()
		self.validate_dates_acorss_permission()
		self.validate_dates_acorss_rest()
		self.validate_mission_overlap()

	def validate_dates(self):
		if self.from_date and self.to_date and (getdate(self.to_date) < getdate(self.from_date)):
			frappe.throw(_("To date cannot be before from date"))

	def validate_dates_acorss_permission(self):
		def _get_permission_alloction_record(from_date,to_date):
			allocation = frappe.db.sql("""select name from `tabPermission`
				where employee=%s  and docstatus=1
				and for_date between %s and %s""", (self.employee, from_date,to_date))

			return allocation and allocation[0][0]

		permission_allocation_based = _get_permission_alloction_record(self.from_date,self.to_date)

		if permission_allocation_based:
			frappe.throw(_("Mission period cannot be inside Permission period"))

	def validate_dates_acorss_rest(self):
		def _get_rest_alloction_record(from_date,to_date):
			allocation = frappe.db.sql("""select name from `tabRest`
				where employee=%(employee)s  and docstatus=1
				AND (
				  (`from_date` <= %(to_date)s AND `to_date` >= %(from_date)s)
				  OR (`from_date` >= %(to_date)s AND `from_date` <= %(from_date)s AND `to_date` <= %(from_date)s)
				  OR (`to_date` <= %(from_date)s AND `to_date` >= %(to_date)s AND `from_date` <= %(to_date)s)
				  OR (from_date >= %(to_date)s AND from_date <= %(from_date)s)
					)				
				""",({"employee":self.employee, "from_date":from_date,"to_date":to_date}))

			return allocation and allocation[0][0]

		allocation_over_lap = _get_rest_alloction_record(self.from_date,self.to_date)

		if allocation_over_lap:
			frappe.throw(_("Mission period cannot be inside Rest period"))

	def validate_mission_overlap(self):
		if not self.name:
			# hack! if name is null, it could cause problems with !=
			self.name = "New Mission"

		for d in frappe.db.sql("""
			select
				name, from_date, to_date, employee_name,employee,mission_type
			from `tabMission`
			where employee = %(employee)s and docstatus < 2
			and to_date >= %(from_date)s and from_date <= %(to_date)s
			and name != %(name)s""", {
				"employee": self.employee,
				"from_date": self.from_date,
				"to_date": self.to_date,
				"name": self.name
			}, as_dict = 1):
			if d :
				self.throw_overlap_error(d)

	def throw_overlap_error(self, d):
		msg = _("Employee {0} has already applied for Mission between {1} and {2}").format(self.employee, formatdate(d['from_date']), formatdate(d['to_date'])) \
			+ """ <br><b><a href="#Form/Mission/{0}">{0}</a></b>""".format(d["name"])
		frappe.throw(msg, OverlapError)

@frappe.whitelist()
def get_events(start, end, filters=None):
	events = []
	from frappe.desk.reportview import get_filters_cond
	conditions = get_filters_cond("Mission", filters, [])
	add_mission(events, start, end, conditions)
	return events

def add_mission(events, start, end, match_conditions=None):
	query = """select `tabMission`.name, from_date, to_date, employee_name,
		employee,mission_type,color, `tabMission`.docstatus
		from `tabMission`
		INNER JOIN `tabMission Type` as mt 
		on `tabMission`.mission_type = mt.name
		where
		from_date <= %(end)s and to_date >= %(start)s <= to_date
		and `tabMission`.docstatus < 2 """
	if match_conditions:
		query += match_conditions

	for d in frappe.db.sql(query, {"start":start, "end": end}, as_dict=True):
		e = {
			"name": d.name,
			"doctype": "Mission",
			"from_date": d.from_date,
			"to_date": d.to_date,
			"title": cstr(d.employee_name),
			"mission_type":d.mission_type,
			"docstatus": d.docstatus,
			"color":d.color,
		}
		if e not in events:
			events.append(e)
