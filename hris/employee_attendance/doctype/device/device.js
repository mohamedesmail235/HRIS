// Copyright (c) 2018, Alfahhad and contributors
// For license information, please see license.txt

frappe.provide("attendances.device");

frappe.ui.form.on('Device', {
    refresh: function (frm) {

        frm.add_custom_button(__('Get Log'),
            function () {
                return cur_frm.call({
                    method: "get_log",
                    async: false,
                    args: {
                        ip: cur_frm.doc.ip,
                        port: cur_frm.doc.port,
                        device_name: cur_frm.doc.name,
                        comm_key: cur_frm.doc.comm_key,
                        password: cur_frm.doc.password
                    },
                    callback: function (r) {
                        if (r.message === 'success') {
                            frappe.show_alert('Successfully Stored Attendance Records on db')
                        } else {
                            msgprint(r.message)
                        }
                    }
                });
            }
        );

        frm.add_custom_button(__('Set Time'),
            function () {
                return cur_frm.call({
                    method: "set_time",
                    args: {
                        ip: cur_frm.doc.ip, port: cur_frm.doc.port,
                        comm_key: cur_frm.doc.comm_key,
                        password: cur_frm.doc.password
                    },
                    callback: function (r) {
                        if (r.message === 'success') {
                            frappe.show_alert('Success')
                        } else {
                            msgprint('Error during set time')
                        }
                    }
                });
            }
        );
        frm.add_custom_button(__('Test Connection'),
            function () {
                return cur_frm.call({
                    method: "test_conn",
                    async: false,
                    args: {
                        ip: cur_frm.doc.ip, port: cur_frm.doc.port,
                        comm_key: cur_frm.doc.comm_key,
                        password: cur_frm.doc.password
                    },
                    callback: function (r) {
                        console.log(r);
                        if (r.message === 'success') {
                            frappe.show_alert('Success')
                        } else {
                            msgprint('Can not connect')
                        }
                    }
                });
            }
        );
        //****************************More Functionality**********************
        frm.add_custom_button(__('Clear Log'),
            function () {
                return cur_frm.call({
                    method: "clear_log",
                    async: false,
                    args: {
                        ip: cur_frm.doc.ip, port: cur_frm.doc.port, device_name: cur_frm.doc.name,
                        comm_key: cur_frm.doc.comm_key,
                        password: cur_frm.doc.password
                    },
                    callback: function (r) {
                        if (r.message === 'success') {
                            frappe.show_alert('Successfully Clear All Attendance Records on db')
                        } else {
                            msgprint('Error')
                        }
                    }
                });
            }
        );

        frm.add_custom_button(__('Clear Data'),
            function () {
                return cur_frm.call({
                    method: "clear_data",
                    async: false,
                    args: {ip: cur_frm.doc.ip, port: cur_frm.doc.port, device_name: cur_frm.doc.name},
                    callback: function (r) {
                        if (r.message === 'success') {
                            frappe.show_alert('Successfully Clear All Data')
                        } else {
                            msgprint('Error')
                        }
                    }
                });
            }
        );

        frm.add_custom_button(__('Power Off'),
            function () {
                return cur_frm.call({
                    method: "poweroff",
                    async: false,
                    args: {
                        ip: cur_frm.doc.ip, port: cur_frm.doc.port, device_name: cur_frm.doc.name,
                        comm_key: cur_frm.doc.comm_key,
                        password: cur_frm.doc.password
                    },
                    callback: function (r) {
                        if (r.message === 'success') {
                            frappe.show_alert('Successfully poweroff the device')
                        } else {
                            msgprint('Error')
                        }
                    }
                });
            }
        );

        frm.add_custom_button(__('Restart'),
            function () {
                return cur_frm.call({
                    method: "restart",
                    async: false,
                    args: {ip: cur_frm.doc.ip, port: cur_frm.doc.port, device_name: cur_frm.doc.name},
                    callback: function (r) {
                        if (r.message === 'success') {
                            frappe.show_alert('Successfully restart for the device')
                        } else {
                            msgprint('Error')
                        }
                    }
                });
            }
        );

        frm.add_custom_button(__('Get Users'),
            function () {
                return cur_frm.call({
                    method: "get_users",
                    async: false,
                    args: {
                        ip: cur_frm.doc.ip, port: cur_frm.doc.port, device_name: cur_frm.doc.name,
                        comm_key: cur_frm.doc.comm_key,
                        password: cur_frm.doc.password
                    },
                    callback: function (r) {
                        if (!r.exc) {
                            var childTable = cur_frm.add_child("project_item_list");
                            for (i = 0; i < r.message.length; i++) {
                                childTable.fieldname = "Text"
                                cur_frm.refresh_fields("project_item_list");
                            }
                            if (r.message === 'success') {
                                refresh_field("users");
                                frappe.show_alert('Successfully get users from the device')
                            } else {
                                msgprint('Error')
                            }
                            /*if(r.message.length>0){

                                for(let i=0;i<r.message.length;i++){
                                    pass
                                    //cur_frm.fields_dict['users'].wrapper
                                    //var row = frappe.model.add_child(cur_frm.doc,'Device','users');
                                }

                            }*/
                        }
                    }
                })
            }
        );
    }
});
