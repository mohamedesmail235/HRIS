# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
#create contract for existing employee
from __future__ import unicode_literals
import frappe,erpnext
import datetime
import calendar
from frappe import _
from frappe.utils.data import date_diff,add_days,cint,add_months,flt,getdate
from hrms.hr.utils import validate_dates, validate_overlap, get_leave_period
from dateutil.relativedelta import relativedelta
from frappe.model.document import Document
import json
from calendar import monthrange
from hris.utils.utils import get_dates_diff, get_month_days


class Employeecontract(Document):
	def __init__(self, *args, **kwargs):
		super(Employeecontract, self).__init__(*args, **kwargs)
		self.whitelisted_globals = {
			"int": int,
			"float": float,
			"long": int,
			"round": round,
			"date": datetime.date,
			"getdate": getdate
		}
	def validate(self):
		# self.validate_dates()
		self.get_slalary_structure_details()

	def on_submit(self):
		self.create_salary_structure_assignment()
		#self.make_leave_allocation()
	def create_salary_structure_assignment(self):
		doc = frappe.new_doc("Salary Structure Assignment")
		doc.employee = self.employee
		doc.salary_structure = self.salary_structure
		doc.from_date = self.contract_start_date
		doc.docstatus = 0
		doc.save()
		frappe.db.commit()

	def validate_dates(self):
		check = validate_contract_date(self.employee, self.cntract_start_date)
		if not check :
			frappe.throw(("You can not add tow contract to this active employee contract."))

	def get_slalary_structure_details(self):
		self.earnings = []
		self.deductions = []

		if not self.salary_structure:
			return
		salary_structure_doc = frappe.get_doc('Salary Structure', self.salary_structure)

		for item in salary_structure_doc.get('earnings'):
			self.append("earnings", {
				"salary_component":item.salary_component,
				"parenttype":"Employee contract",
				"abbr":item.abbr,
				"amount":item.amount,
				"year_to_date":item.year_to_date,
				"additional_salary":item.additional_salary,
				"additional_salary":item.statistical_component,
				"depends_on_payment_days":item.depends_on_payment_days,
				"exempted_from_income_tax":item.exempted_from_income_tax,
				"is_tax_applicable":item.is_tax_applicable,
				"is_flexible_benefit":item.is_flexible_benefit,
				"variable_based_on_taxable_salary":item.variable_based_on_taxable_salary,
				"do_not_include_in_total":item.do_not_include_in_total,
				"deduct_full_tax_on_selected_payroll_date":item.deduct_full_tax_on_selected_payroll_date,
				"condition":item.condition,
				"amount_based_on_formula":item.amount_based_on_formula,
				"formula":item.formula,
				"default_amount":item.default_amount,
				"additional_amount":item.additional_amount,
				"tax_on_flexible_benefit":item.tax_on_flexible_benefit,
				"tax_on_additional_salary":item.tax_on_additional_salary,
				"is_recurring_additional_salary":item.is_recurring_additional_salary
			})

		for item in salary_structure_doc.get('deductions'):
			self.append("deductions", {
				"salary_component":item.salary_component,
				"parenttype":"Employee contract",
				"abbr":item.abbr,
				"amount":item.amount,
				"year_to_date":item.year_to_date,
				"additional_salary":item.additional_salary,
				"additional_salary":item.statistical_component,
				"depends_on_payment_days":item.depends_on_payment_days,
				"exempted_from_income_tax":item.exempted_from_income_tax,
				"is_tax_applicable":item.is_tax_applicable,
				"is_flexible_benefit":item.is_flexible_benefit,
				"variable_based_on_taxable_salary":item.variable_based_on_taxable_salary,
				"do_not_include_in_total":item.do_not_include_in_total,
				"deduct_full_tax_on_selected_payroll_date":item.deduct_full_tax_on_selected_payroll_date,
				"condition":item.condition,
				"amount_based_on_formula":item.amount_based_on_formula,
				"formula":item.formula,
				"default_amount":item.default_amount,
				"additional_amount":item.additional_amount,
				"tax_on_flexible_benefit":item.tax_on_flexible_benefit,
				"tax_on_additional_salary":item.tax_on_additional_salary,
				"is_recurring_additional_salary":item.is_recurring_additional_salary
			})

	def on_cancel(self):
		# self.delete_leave_allocation()
		# frappe.db.sql('''
		# DELETE FROM `tabSalary Structure Assignment` WHERE employee ='%s'
		# '''%self.employee)
		# frappe.db.commit()
		# res = frappe.db.sql('''
		# DELETE FROM `tabSalary Structure` WHERE parent ='%s'
		# '''%self.name)
		# frappe.db.commit()
		frappe.msgprint("Cancelled")

	def make_leave_allocation(self):

		curr_allocation = self.check_current_allocation()
		self.create_leave_allocation(curr_allocation, self.yearly_vacation, self.data_7)

	def check_current_allocation(self):
		curr_allocation = frappe.db.sql("""
			SELECT `name`,  
				total_leaves_allocated,	to_date, new_leaves_allocated,
				employee, leave_type, from_date, leave_period
				FROM
				`tabLeave Allocation`
				WHERE
				`tabLeave Allocation`.employee = %s
					and leave_type = %s
					and (%s between from_date and to_date or %s between from_date and to_date )
		""", (self.employee,"Casual Leave", self.contract_start_date, self.contratc_end_date), as_dict=True)
		if curr_allocation:
			curr_allocation = curr_allocation[0]
			to_date = self.contract_start_date
			frappe.db.sql("""
						update `tabLeave Allocation`
							set to_date=%s
							where name=%s
					""", (to_date, curr_allocation["name"]))
			return curr_allocation

	def create_leave_allocation(self, curr_allocation, yearly_vacation, contract_duration):
		allocation = frappe.new_doc("Leave Allocation")

		if curr_allocation:
			allocation.leave_period = curr_allocation["leave_period"]
		else:
			leave_period = get_leave_period(self.contract_start_date, self.contratc_end_date, frappe.db.get_value("Employee",self.employee,"company"))
			if leave_period:
				allocation.leave_period = leave_period[0]["name"]
			else:
				frappe.throw(_("please add new leave period"))


		allocation.employee = self.employee
		allocation.employee_name = self.employee_full_name
		allocation.leave_type = "Casual Leave"
		allocation.from_date = self.contract_start_date
		allocation.to_date = add_months(self.contract_start_date, cint(self.data_7))
		allocation.new_leaves_allocated = cint(self.yearly_vacation) * (flt(self.data_7)/12)
		allocation.total_leaves_allocated =  cint(self.yearly_vacation) * (flt(self.data_7)/12)
		allocation.employee_contract = self.name
		allocation.description = "created by back from leave {0} ".format(self.name)

		allocation.save(ignore_permissions=True)
		allocation.submit()

		return allocation

	def delete_leave_allocation(self):
		frappe.db.sql("""
			delete from 
				`tabLeave Allocation`
				where employee_contract = %s
		""",(self.name))

	@frappe.whitelist()
	def update_yearly_vacation(self):
		leave_days_no = 0
		data = frappe.get_list("Leave Category",filters={'parent':self.employee_leave_category},fields=['years_from','years_to','leave_days_no'],order_by="idx desc")
		if data:
			service_details = self.get_years_of_service()
			if len(data) > 1:
				for item in data:
					if flt(item["years_to"]) >= cint(service_details["years"]) >= flt(item["years_from"]):
						self.yearly_vacation = flt(item["leave_days_no"])
						leave_days_no = flt(item["leave_days_no"])
			else:
				self.yearly_vacation = flt(data[0]["leave_days_no"])
				leave_days_no = flt(data[0]["leave_days_no"])

			if not flt(self.yearly_vacation) > 0:
				frappe.throw(_("يرجي مراجعة فئات أجازات الموظفين"))

		return leave_days_no
	def get_years_of_service(self):
		date_of_joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")
		if (not date_of_joining):
			frappe.throw("Please set date of joining")
		deducted_days = frappe.db.get_value("Deduct Days from Service Period",
											{"name": self.employee, "type": "Service Period"}, "number_of_days") or 0

		service_details = get_dates_diff(add_days(date_of_joining, deducted_days), add_days(getdate(), 1))
		# frappe.msgprint("service_details==================="+str(service_details))
		return service_details

@frappe.whitelist()
def validate_contract_date(employee , start_date):
	date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
	# date = datetime.date.today()
	grant_date    = datetime.datetime.today() - relativedelta(months =+ 2)
	if date < grant_date :
		frappe.msgprint("Unvalid Contract date !")
		return False
	res = frappe.db.sql('''
	SELECT   contratc_end_date  FROM `tabEmployee contract` WHERE employee ='%s' and docstatus = 1
	'''%employee, as_dict=1)


	for i in res:
		if  i.contratc_end_date >  date.date()  :
				return False
		else :
			return True
	return True

@frappe.whitelist()
def get_contract_end_date(duration , start_date,  employee ):
	date        = datetime.datetime.strptime(start_date, "%Y-%m-%d")
	end_date    = date + relativedelta(months =+ int(duration))
	check_dates = validate_contract_date(employee , start_date)
	if check_dates :
		return(end_date.date() )
	else :
		frappe.msgprint("You can not add tow contract to this active employee contract")
	return(end_date.date() )

@frappe.whitelist()
def v_integer(number):
	try :
		int(number)
		return("1")
	except:
		return("0")


