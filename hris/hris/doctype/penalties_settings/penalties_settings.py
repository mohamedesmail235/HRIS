# -*- coding: utf-8 -*-
# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import getdate
from frappe import  _
from frappe.model.document import Document
from frappe.desk.reportview import get_match_cond, get_filters_cond
class PenaltiesSettings(Document):

	def validate(self):
		self.check_existing(self.name)
		
	def check_existing(self,current_penalty):
		ret_exist = frappe.db.sql("""select penalty_type from `tabPenalties Settings`
			where docstatus != 2
			and penalty_type = %s
			and `name` <> %s
			and
				(
					(%s  BETWEEN from_date and IFNULL(to_date,NOW()))
				or  (%s  BETWEEN from_date and IFNULL(to_date,NOW()))

				or  (from_date  BETWEEN %s and %s)
				or  (to_date  BETWEEN %s and %s)
				
				or to_date is NULL
				)
			""",(self.penalty_type,current_penalty,self.from_date, getdate(self.to_date)\
			   ,self.from_date, getdate(self.to_date) \
			   ,self.from_date, getdate(self.to_date)	
			   )
			   )
		
		if ret_exist:
			frappe.throw(_("<center>penalty type of this name <BR> {0} <BR> already created for this period</center>").format(self.penalty_type))
		else:
			times = []
			for penalty in self.get('penalties_data'):
				times.append(penalty.times)
				if(times.count(penalty.times) > 1):
					frappe.throw(_(
						"<center>penalty time of this name <BR> {0} <BR> already created for this setting</center>").format(penalty.times))

@frappe.whitelist()
def get_salary_components(doctype, txt, searchfield, start, page_len, filters):
	conditions = []
	return frappe.db.sql("""select name, salary_component from `tabSalary Component`
			where type in('Earning','Base')
				and docstatus < 2
				and ({key} like %(txt)s
					or salary_component like %(txt)s)
				{fcond} {mcond}
			order by
				if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
				if(locate(%(_txt)s, salary_component), locate(%(_txt)s, salary_component), 99999),

				name, salary_component
			limit %(start)s, %(page_len)s""".format(**{
				'key': searchfield,
				'fcond': get_filters_cond(doctype, filters, conditions),
				'mcond': get_match_cond(doctype)
				}), {
				 'txt': "%%%s%%" % txt,
				 '_txt': txt.replace("%", ""),
				 'start': start,
				 'page_len': page_len
			})


