# -*- coding: utf-8 -*-
# Copyright (c) 2018, Alfahhad and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from hris.zk import ZK, const
from datetime import datetime, date
from struct import pack, unpack
from frappe.utils import cint, cstr, getdate, nowdate
import dateutil
class Device(Document):
	pass


@frappe.whitelist()
def test_conn(ip=None,port=None,comm_key=None,password=None):
	print("==================="+str(password))
	conn = None
	#zk = ZK(ip, port=int(port), timeout=5)
	zk = ZK(ip, port=int(port), password=0,timeout=20 , force_udp=True, ommit_ping=True)
	try:
		print('Connecting to device {0} on port {1}'.format(ip,port))
		conn = zk.connect()
		return 'success'
	except Exception as e:
		print("Process terminate : {}".format(e))
		return 'error'
	finally:
		if conn:
			conn.disconnect()

@frappe.whitelist()
def set_time(ip=None,port=None):
	conn = None
	zk = ZK(ip, port=int(port), timeout=5)
	try:
		conn = zk.connect()
		response = conn.set_time(str(datetime.now()))
		if response:
			return 'success'
	except Exception as e:
		print("Process terminate : {}".format(e))
		return 'error'
	finally:
		if conn:
			conn.disconnect()

def get_log_hourly():
	print("===========================Starting Get Log=============================")
	devices = frappe.db.sql("""
			select `name`,`ip`,`port` 
				from tabDevice
			""",as_dict=True)
	if devices:
		for device in devices:
			print("==========================="+str(device["name"])+"=============================")
			frappe.enqueue(get_log,timeout=600,ip=device["ip"],port=device["port"],device_name=device["name"])
			# get_log(device["ip"],device["port"],device["name"])

@frappe.whitelist()
def get_log(ip=None,port=None,device_name=None):
	conn = None
	zk = ZK(ip, port=int(port), timeout=5)
	# try:
	conn = zk.connect()
	response = conn.get_attendance()
	#print(response)
	for attendance in response :
		try:
			#print(attendance.uid)
			# print("attendance {0} time:{1} status {2}".format(attendance.user_id,attendance.timestamp,attendance.punch))
			timestamp = dateutil.parser.parse(str(attendance.timestamp))
			if getdate(timestamp).year != getdate(nowdate()).year:
				getdate(timestamp).year = getdate(nowdate()).year
			# timestamp = timestamp.date()
			print("User:==" + str(attendance.user_id) + "===timestamp:==(" + str(timestamp) + ")====status:==" + str(attendance.status) + "====punch:==" + str(attendance.punch) + "====uid:==" + str(attendance.uid))

			# if attendance.status == 0 :
			# 	status='Check In'
			# elif attendance.status == 1:
			# 	status = 'Check Out'
			# else:
			# 	status = 'Undefined'
			if attendance.punch == 0 :
				status='Check In'
			elif attendance.punch == 1:
				status = 'Check Out'
			else:
				status = 'Undefined'
			stored_attendance_log = frappe.db.get_value("Attendance Log",{"timestamp": attendance.timestamp,"user_id":attendance.user_id}, "*")
			if not stored_attendance_log:
				attendance_log = frappe.new_doc("Attendance Log")
				attendance_log.user_id = attendance.user_id
				attendance_log.uid = attendance.uid
				emp =  get_emp(attendance.user_id)
				if emp:
					attendance_log.employee = emp
				attendance_log.timestamp = timestamp # dateutil.parser.parse(str(attendance.timestamp))#  __decode_time(attendance.timestamp)
				attendance_log.data_retrieve__time = datetime.now()
				attendance_log.status = status
				attendance_log.device = device_name
				attendance_log.save()
		except Exception as e:
			doc = frappe.get_doc("Device",device_name)
			error = str(e) or "error"
			doc.errors = error # +"==="+str("attendance {0} time:{1} status {2}".format(str(attendance.user_id),str(attendance.timestamp),str(attendance.punch)))
			doc.save()
			frappe.db.commit()
	if response:
		return 'success'
	# except Exception as e:
	# 	# print("Process terminate : {0}".format(e))
	# 	return str("Process terminate : {0}").format(str(e))
	# finally:
	# 	if conn:
	# 		conn.disconnect()

def get_emp(user_id):
	try:
		emp_name = frappe.db.get_value("Employee",{"attendance_device_id": user_id}, "name")
		return emp_name
	except frappe.LinkValidationError:
		return False

#*****************************More Functionality***********************************#
@frappe.whitelist()
def clear_log(ip=None,port=None):
	conn = None
	zk = ZK(ip, port=int(port), timeout=5)
	try:
		conn = zk.connect()
		response = conn.clear_attendance()
		if response:
			return 'success'
	except Exception as e:
		print("Process terminate : {}".format(e))
		return 'error'
	finally:
		if conn:
			conn.disconnect()

@frappe.whitelist()
def clear_data(ip=None,port=None):
	conn = None
	zk = ZK(ip, port=int(port), timeout=5)
	try:
		conn = zk.connect()
		response = conn.clear_data()
		if response:
			return 'success'
	except Exception as e:
		print("Process terminate : {}".format(e))
		return 'error'
	finally:
		if conn:
			conn.disconnect()

@frappe.whitelist()
def poweroff(ip=None,port=None):
	conn = None
	zk = ZK(ip, port=int(port), timeout=5)
	try:
		conn = zk.connect()
		response = conn.poweroff()
		if response:
			return 'success'
	except Exception as e:
		print("Process terminate : {}".format(e))
		return 'error'
	finally:
		if conn:
			conn.disconnect()

@frappe.whitelist()
def restart(ip=None,port=None):
	conn = None
	zk = ZK(ip, port=int(port), timeout=5)
	try:
		conn = zk.connect()
		response = conn.restart()
		if response:
			return 'success'
	except Exception as e:
		print("Process terminate : {}".format(e))
		return 'error'
	finally:
		if conn:
			conn.disconnect()

@frappe.whitelist()
def get_users(device_name,ip=None,port=None):
	conn = None
	zk = ZK(ip, port=int(port), timeout=5)
	try:
		conn = zk.connect()
		users = conn.get_users()
		#from frappe.custom.doctype.custom_field.custom_field import create_custom_field,add_custom_field
		# create_custom_field('Device Users',
		# 					{
		# 						"fieldname": 'user_name',
		# 						"label": 'Name',
		# 						"fieldtype": 'Data',
		# 					})
		#doc = frappe.get_doc(device_name)
		#frappe.msgprint(doc)
		for user in users:
			#print("user {0} Name:{1} Password {2}".format(user.user_id,user.name,user.password))
			privilege = 'User'
			if user.privilege == const.USER_ADMIN:
				privilege = 'Admin'
			print('- UID #{0}'.format(user.uid))
			print('  Name       : {0}'.format(user.name))
			print('  Privilege  : {0}'.format(privilege))
			print('  Password   : {0}'.format(user.password))
			print('  Group ID   : {0}'.format(user.group_id))
			print('  User  ID   : {0}'.format(user.user_id))

			#row = Document.append('users', {})
			#row.user_id = user.user_id
			# doc.append("Device Users", {
			# 	"user_id": user.user_id,
			# 	"name1": user.name
			# })
			# doc.insert()

			# stored_users = frappe.db.get_value("Device Users", {"user_id": user.user_id}, "*")
			# frappe.msgprint(stored_users)
			# if not stored_users:
			# 	user_log = frappe.new_doc("Device Users")
			# 	user_log.user_id = user.user_id
			# 	user_log.name1 = user.name
			# 	user_log.password = user.password
			# 	user_log.group_id = user.group_id
			# 	user_log.card = user.card
			# 	user_log.privilege = user.privilege
			# 	user_log.save()

		if users:
			return 'success'
		zk.enable_device()
	except Exception as e:
		print("Process terminate : {}".format(e))
		return 'error'
	finally:
		if zk.is_connect:
			zk.disconnect()


def __decode_time(t):
	"""
    Decode a timestamp retrieved from the timeclock

    copied from zkemsdk.c - DecodeTime
    """

	t = unpack("<I", t)[0]
	second = t % 60
	t = t // 60

	minute = t % 60
	t = t // 60

	hour = t % 24
	t = t // 24

	day = t % 31 + 1
	t = t // 31

	month = t % 12 + 1
	t = t // 12

	year = t + 2000

	d = datetime(year, month, day, hour, minute, second)

	return d
