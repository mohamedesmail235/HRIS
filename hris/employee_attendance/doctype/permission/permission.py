# -*- coding: utf-8 -*-
# Copyright (c) 2018, Alfahhad and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
# from erpnext.setup.doctype.employee.employee import OverlapError
# from hrms.hr.doctype.employee_attendance_tool.employee_attendance_tool import check_assigned_period
from frappe.model.document import Document
from frappe.utils import getdate, to_timedelta, time_diff_in_seconds, flt, format_time
from frappe import _

class OverlapError(frappe.ValidationError): pass

class Permission(Document):
	def validate(self):
	#	self.validate_dates()
		#self.validate_dates_acorss_mission()
	#	self.validate_dates_rest_mission()
	#	self.validate_attendance_period()
		if self.to_time and self.from_time:
			self.validate_permission_overlap()

	def validate_permission_overlap(self):
		if not self.name:
			# hack! if name is null, it could cause problems with !=
			self.name = "New Permission"

		for d in frappe.db.sql("""
			select
				name, from_time, to_time, employee_name,employee
			from `tabPermission`
			where employee = %(employee)s and docstatus < 2
			and for_date = %(for_date)s
			and to_time >= %(from_time)s and from_time <= %(to_time)s
			and name != %(name)s""", {
				"employee": self.employee,
				"for_date": self.for_date,
				"from_time": self.from_time,
				"to_time": self.to_time,
				"name": self.name
			}, as_dict = 1):
			if d :
				self.throw_overlap_error(d)

	def throw_overlap_error(self, d):
		msg = _("Employee {0} has already applied for Permission between {1} and {2}").format(self.employee, format_time(d['from_time']), format_time(d['to_time'])) \
			+ """ <br><b><a href="#Form/Permission/{0}">{0}</a></b>""".format(d["name"])
		frappe.throw(msg, OverlapError)

	def validate_dates(self):
		if  (self.to_time and self.from_time) and (to_timedelta(self.to_time) <= to_timedelta(self.from_time)):
			frappe.throw(_("To time cannot be before or equal from time"))

		permission_based_on = frappe.db.get_single_value("Attendances Settings", "permission_based_on", cache=False)
		if permission_based_on == "Number Of Permissions Per Month":
			no_of_permissions = frappe.db.get_single_value("Attendances Settings", "no_of_permissions", cache=False)
			if flt(no_of_permissions) < 1.0:
					frappe.throw(_("There is not enough permission balance for Permission Type {0}").format(permission_based_on))

		elif permission_based_on == "Minutes Per Month":
			current_permission_time = round(time_diff_in_seconds(self.to_time, self.from_time) /60.0,2)
			if flt(self.permission_balance) < current_permission_time:
				frappe.throw(_("You have assigned {0} Minutes current permission balance {1}").format(current_permission_time,self.permission_balance))

	def validate_dates_acorss_mission(self):
		def _get_mission_alloction_record(date):
			allocation = frappe.db.sql("""select name from `tabMission`
				where employee=%s  and docstatus=1
				and %s between from_date and to_date""", (self.employee, date))

			return allocation and allocation[0][0]

		allocation_based_on_for_date = _get_mission_alloction_record(self.for_date)

		if allocation_based_on_for_date:
			frappe.throw(_("Permission period cannot be inside Mission period"))

	def validate_dates_rest_mission(self):
		def _get_rest_alloction_record(date):
			allocation = frappe.db.sql("""select name from `tabRest`
				where employee=%s  and docstatus=1
				and %s between from_date and to_date""", (self.employee, date))

			return allocation and allocation[0][0]

		allocation_based_on_for_date = _get_rest_alloction_record(self.for_date)

		if allocation_based_on_for_date:
			frappe.throw(_("Permission period cannot be inside Rest period"))

	#def validate_attendance_period(self):
	#	dict_period = self.check_assigned_period(self.employee,self.for_date)
	#	if not dict_period:
	#		frappe.throw(_("Employee not assigned to period at this Date"))
	#	else:
	#		if (self.from_time and self.to_time):
	#			if dict_period["start_time"] > to_timedelta(self.from_time):
	#				frappe.throw(_("From Time can't be less than period Start Time {0}".format(dict_period["start_time"])))
#
#				if dict_period["end_time"] < to_timedelta(self.to_time):
#					frappe.throw(_("To Time can't exceed period End Time {0} ".format(dict_period["end_time"])))

	def check_assigned_period(self,employee_name, curr_single_date):
		data_Dic = frappe.db.sql(
			"""
			select AD.attendance_period , AD.start_date , AD.end_date end_date, 
			AP.start_date Pstart_date, AP.end_date Pend_date,AP.start_time,AP.end_time, 
			AP.attendance_permissibility, AP.leave_permissibility, AP.attendance_type, 
			AP.night_shift, AP.hours_per_month, AP.hours_per_day
				from `tabAttendance Data` AD
				INNER JOIN 
				`tabAttendance Period` AP
				on AD.attendance_period = AP.`name`
				and AD.parent=%s
				and %s between AD.start_date and ifnull(AD.end_date,CURDATE())
			"""
			, (employee_name, curr_single_date), as_dict=1, debug=False
		)

		if data_Dic != []:
			return data_Dic[0]

		return data_Dic

@frappe.whitelist()
def get_permission_balance(employee, for_date):
	permission_time = 0
	permission_based_on = frappe.db.get_single_value("Attendances Settings", "permission_based_on", cache=False)

	permission_taken = get_permission_allocation_records(employee, for_date)
	if permission_based_on == "Number Of Permissions Per Month":
		no_of_permissions = frappe.db.get_single_value("Attendances Settings", "no_of_permissions", cache=False)
		return {permission_based_on:flt(no_of_permissions) - flt(len(permission_taken))}
	elif permission_based_on == "Minutes Per Month":
		permission_minutes = frappe.db.get_single_value("Attendances Settings", "permission_minutes", cache=False)
		for item in permission_taken:
			permission_time +=flt(item['permission_time'])
		return {permission_based_on:flt(permission_minutes) - flt(permission_time)}


def get_permission_allocation_records(employee, from_date):
	permission_records = frappe.db.sql("""
		select TIMESTAMPDIFF(minute,from_time,to_time) permission_time
		from `tabPermission`
		where employee='{0}'
		and MONTH(for_date) ={1}
		and docstatus = 1
		""".format(employee,getdate(from_date).month), as_dict=1)

	return permission_records

@frappe.whitelist()
def get_events(start, end, filters=None):
	events = []
	from frappe.desk.reportview import get_filters_cond
	conditions = get_filters_cond("Permission", filters, [])
	add_permission(events, start, end, conditions)
	return events

def add_permission(events, start, end, match_conditions=None):
	query = """select `tabPermission`.name, for_date, employee_name,
		employee,permission_type, `tabPermission`.docstatus
		from `tabPermission`
		where
		for_date between %(end)s and  %(start)s 
		and `tabPermission`.docstatus < 2 """
	if match_conditions:
		query += match_conditions

	for d in frappe.db.sql(query, {"start":start, "end": end}, as_dict=True):
		e = {
			"name": d.name,
			"doctype": "Mission",
			"for_date": d.for_date,
			"title": str(d.employee_name),
			"permission_type":d.permission_type,
			"docstatus": d.docstatus
		}
		if e not in events:
			events.append(e)
