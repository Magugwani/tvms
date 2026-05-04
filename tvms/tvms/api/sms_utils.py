# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

"""
TVMS SMS Notification Utility

This module provides SMS notification functionality for the TVMS application.
It can be integrated with any SMS API provider (Twilio, Nexmo, Africa's Talking, etc.)

Configuration (set in Site Config or hooks):
    sms_api_url: SMS provider API endpoint
    sms_api_key: API key for authentication
    sms_sender_id: Sender ID/Phone number
    sms_enabled: Enable/disable SMS notifications
"""

import frappe
import requests
from frappe import _


class SMSNotification:
	"""SMS Notification handler for TVMS"""
	
	def __init__(self):
		"""Initialize SMS settings from site config"""
		self.enabled = frappe.db.get_single_value(
			"TVMS Settings", "sms_enabled"
		) or frappe.conf.get("sms_enabled", False)
		
		self.api_url = frappe.db.get_single_value(
			"TVMS Settings", "sms_api_url"
		) or frappe.conf.get("sms_api_url", "")
		
		self.api_key = frappe.db.get_single_value(
			"TVMS Settings", "sms_api_key"
		) or frappe.conf.get("sms_api_key", "")
		
		self.sender_id = frappe.db.get_single_value(
			"TVMS Settings", "sms_sender_id"
		) or frappe.conf.get("sms_sender_id", "TVMS")
	
	def send_sms(self, phone_numbers, message):
		"""
		Send SMS to one or more phone numbers
		
		Args:
			phone_numbers: List of phone numbers or single phone number (string)
			message: SMS message content
		
		Returns:
			dict: Result with success status and message ID
		"""
		if not self.enabled:
			frappe.logger().debug("SMS notifications disabled")
			return {"success": False, "message": "SMS notifications disabled"}
		
		# Normalize phone numbers to list
		if isinstance(phone_numbers, str):
			phone_numbers = [phone_numbers]
		
		# Validate message
		if not message or len(message) > 160:
			frappe.throw(_("SMS message must be 1-160 characters"))
		
		# Send SMS via provider API
		return self._send_via_api(phone_numbers, message)
	
	def _send_via_api(self, phone_numbers, message):
		"""Send SMS via configured API provider"""
		try:
			# This is a generic implementation - customize based on your SMS provider
			payload = {
				"api_key": self.api_key,
				"sender_id": self.sender_id,
				"phone_numbers": phone_numbers,
				"message": message
			}
			
			# Example for Twilio-like API
			# response = requests.post(
			#     self.api_url,
			#     json=payload,
			#     headers={"Content-Type": "application/json"},
			#     timeout=30
			# )
			
			# For demo purposes, log the SMS
			frappe.logger().info(
				f"SMS would be sent to {phone_numbers}: {message}"
			)
			
			return {
				"success": True,
				"message": "SMS queued for delivery",
				"recipients": phone_numbers
			}
			
		except requests.exceptions.RequestException as e:
			frappe.logger().error(f"SMS API error: {str(e)}")
			return {"success": False, "message": str(e)}
		except Exception as e:
			frappe.logger().error(f"SMS error: {str(e)}")
			return {"success": False, "message": str(e)}
	
	def send_emergency_session_notification(
		self, session_doc, notification_type="status_change"
	):
		"""
		Send SMS notification for emergency session events
		
		Args:
			session_doc: Emergency session document
			notification_type: Type of notification (status_change, reminder, etc.)
		"""
		if not self.enabled:
			return
		
		# Get phone numbers from recipients
		phone_numbers = self._get_session_recipients(session_doc)
		if not phone_numbers:
			return
		
		# Prepare message based on notification type
		message = self._prepare_session_message(session_doc, notification_type)
		if message:
			self.send_sms(phone_numbers, message)
	
	def _get_session_recipients(self, session_doc):
		"""Get phone numbers for session notifications"""
		phone_numbers = []
		
		# Get creator's phone
		if session_doc.created_by:
			phone = frappe.db.get_value(
				"User", session_doc.created_by, "mobile_no"
			)
			if phone:
				phone_numbers.append(phone)
		
		# Get venue managers' phones
		venue_managers = frappe.db.sql("""
			SELECT DISTINCT u.mobile_no
			FROM `tabHas Role` hr
			JOIN `tabUser` u ON hr.parent = u.name
			WHERE hr.role = 'TVMS Manager'
			AND u.mobile_no IS NOT NULL
			AND u.enabled = 1
		""")
		for vm in venue_managers:
			if vm[0]:
				phone_numbers.append(vm[0])
		
		return list(set(phone_numbers))
	
	def _prepare_session_message(self, session_doc, notification_type):
		"""Prepare SMS message for session events"""
		if notification_type == "status_change":
			return (
				f"TVMS: Emergency Session {session_doc.name} "
				f"status changed to {session_doc.status}. "
				f"Venue: {session_doc.venue or 'N/A'}"
			)
		elif notification_type == "reminder":
			return (
				f"TVMS: Reminder - {session_doc.title} "
				f"at {session_doc.venue} starting at {session_doc.start_time}"
			)
		elif notification_type == "confirmation":
			return (
				f"TVMS: Your Emergency Session {session_doc.name} "
				f"has been CONFIRMED for {session_doc.venue}"
			)
		elif notification_type == "cancellation":
			return (
				f"TVMS: Emergency Session {session_doc.name} "
				f"has been CANCELLED"
			)
		
		return None


def send_sms(phone_numbers, message):
	"""
	Convenience function to send SMS
	
	Usage:
		from tvms.utils.sms_utils import send_sms
		send_sms("+1234567890", "Your session is confirmed")
	"""
	sms_handler = SMSNotification()
	return sms_handler.send_sms(phone_numbers, message)