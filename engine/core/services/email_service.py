"""
Email Service
Handles sending emails (invoices, notifications, etc.)
"""
import logging
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Crypto Arth")

logger = logging.getLogger(__name__)


def send_invoice_email(
    to_email: str,
    user_name: str,
    user_mobile: str,
    payment_id: str,
    amount: float,
    gst_amount: float,
    total_amount: float,
    credits_added: int,
    payment_date: datetime
) -> bool:
    """
    Send invoice email after successful payment
    
    Args:
        to_email: Recipient email address
        user_name: User's name
        user_mobile: User's mobile number
        payment_id: Razorpay payment ID
        amount: Base amount (before GST)
        gst_amount: GST amount (18%)
        total_amount: Total amount paid (base + GST)
        credits_added: Credits added to account
        payment_date: Payment date and time
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Check if email is configured
        if not SMTP_USER or not SMTP_PASSWORD or not SMTP_FROM_EMAIL:
            logger.warning("Email service not configured. Skipping invoice email.")
            return False
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Payment Invoice - {payment_id}'
        msg['From'] = f'{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>'
        msg['To'] = to_email
        
        # Format payment date
        payment_date_str = payment_date.strftime('%d %B %Y, %I:%M %p') if payment_date else datetime.now().strftime('%d %B %Y, %I:%M %p')
        
        # Create HTML email body
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; }}
                .invoice-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
                .detail-row:last-child {{ border-bottom: none; }}
                .label {{ font-weight: 600; color: #6b7280; }}
                .value {{ color: #111827; font-weight: 500; }}
                .total {{ background: #10b981; color: white; padding: 15px; border-radius: 8px; margin-top: 20px; }}
                .footer {{ text-align: center; padding: 20px; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Payment Invoice</h1>
                    <p>Thank you for your purchase!</p>
                </div>
                <div class="content">
                    <p>Dear {user_name},</p>
                    <p>Your payment has been processed successfully. Please find the invoice details below:</p>
                    
                    <div class="invoice-details">
                        <div class="detail-row">
                            <span class="label">Name:</span>
                            <span class="value">{user_name}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Mobile:</span>
                            <span class="value">{user_mobile or 'N/A'}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Email:</span>
                            <span class="value">{to_email}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Payment ID:</span>
                            <span class="value">{payment_id}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Date & Time:</span>
                            <span class="value">{payment_date_str}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Base Amount:</span>
                            <span class="value">₹{amount:.2f}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">GST (18%):</span>
                            <span class="value">₹{gst_amount:.2f}</span>
                        </div>
                        <div class="total">
                            <div class="detail-row" style="border-bottom: none; color: white;">
                                <span style="font-size: 18px; font-weight: 700;">Total Payable:</span>
                                <span style="font-size: 18px; font-weight: 700;">₹{total_amount:.2f}</span>
                            </div>
                        </div>
                        <div class="detail-row" style="margin-top: 20px; padding-top: 20px; border-top: 2px solid #e5e7eb;">
                            <span class="label" style="font-size: 16px;">Credits Added:</span>
                            <span class="value" style="font-size: 16px; color: #10b981; font-weight: 700;">+{credits_added} Credits</span>
                        </div>
                    </div>
                    
                    <p style="margin-top: 30px;">Your credits have been added to your account and are ready to use.</p>
                    <p>Thank you for choosing Crypto Arth!</p>
                </div>
                <div class="footer">
                    <p>This is an automated email. Please do not reply.</p>
                    <p>&copy; {datetime.now().year} Crypto Arth. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version
        text_body = f"""
Payment Invoice

Dear {user_name},

Your payment has been processed successfully. Please find the invoice details below:

Name: {user_name}
Mobile: {user_mobile or 'N/A'}
Email: {to_email}
Payment ID: {payment_id}
Date & Time: {payment_date_str}

Base Amount: ₹{amount:.2f}
GST (18%): ₹{gst_amount:.2f}
Total Payable: ₹{total_amount:.2f}

Credits Added: +{credits_added} Credits

Your credits have been added to your account and are ready to use.

Thank you for choosing Crypto Arth!

---
This is an automated email. Please do not reply.
© {datetime.now().year} Crypto Arth. All rights reserved.
        """
        
        # Attach both versions
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Invoice email sent successfully to {to_email} for payment {payment_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending invoice email: {e}", exc_info=True)
        return False

