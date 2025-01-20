# -*- coding: utf-8 -*-
# Copyright (c) 2018, Alfahhad and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from hris.employee_attendance.doctype.device.device import get_log
from frappe.model.document import Document

class AttendanceLog(Document):
	pass

def get_att_log():
	for device in frappe.db.get_all("Device",fields=["name", "ip","port"]):
		print ("==>",device.ip,device.port,device.name)
		get_log(device.ip,device.port,device.name)