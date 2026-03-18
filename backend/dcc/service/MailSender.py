import win32com.client
import pythoncom
import os

def html_to_text(html_file_path):
    with open(html_file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()

    return html_content

def replace_all_keys(text, replacements):
    for key, value in replacements.items():
        text = text.replace(key, value)  
    return text

def SendMail(title, body, to, cc="", bcc=""):
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail_item = outlook.CreateItem(0)
    
    mail_item.Subject = title

    mail_item.To = to
    mail_item.CC = cc
    mail_item.BCC = bcc

    mail_item.HTMLBody = body
    mail_item.Send()

