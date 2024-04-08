#normal previous code without get_task():

import requests
import datetime
import pprint
#from dotenv import load_env
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import json
import schedule
from threading import Thread
from slack_sdk import WebClient #import for slack 

#constants/global variables 
CLICKUP_API_TOKEN = 'pk_73223342_17LY9UC6TE84D6P5MF2ALXU5W8UT6LHA'
#SLACK_WEBHOOK_URL = 'https://hooks.slack.com/triggers/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' #uncomment this #original webhook url for facets workspace 
SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/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'
CLICKUP_API_ENDPOINT = 'https://api.clickup.com/api/v2'
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive','https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/spreadsheets.readonly']
creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
client = gspread.authorize(creds)
folder_id = '109448264'   #customer list folder id 
existing_urls = set()
HEADERS = {
    'Authorization' : CLICKUP_API_TOKEN
}
#Function to schedule the report for sending every Friday at 6PM 
def schedule_report_of_bug_tickets():
    schedule.every().friday.at('18:00').do(run_report)
    while True:
        schedule.run_pending()
        time.sleep(60)

#Function to check whether the ticket is a bug or not 
def is_bug_based_on_comments(comments,priority_type):  #priority type is added here 
    bot_comment_count = 0                    #initialize the bot comment count to 0
    for comment in comments:                 #iterate through each commets
        if comment['user']['id'] == -1:      #checks if the id of the comment is -1
            bot_comment_count +=1            #if it is -1 increase the bot_comment_count
    if (priority_type == 'urgent' and  bot_comment_count >=3) or (priority_type == 'high' and bot_comment_count>=2):                 #checks if the comment is greater than equal to 2
    #if true consider it as a bug based on comment  
        return True
    else:
        return False 

def get_task(task_id):
    response = requests.get(f'{CLICKUP_API_ENDPOINT}/task/{task_id}',headers=HEADERS)
    if response.status_code == 200:
        print(f'Fetching the task {task_id}')
        task_data = response.json()
        return task_data
    else:
        print(f'Failed to fetch the task data')
        return None

    

#Function to fetch the tasks from each list and filters the task based on priority, status, bug ticket based on comment
#and checks if the ticket falls in the current week then add those ticket to a list called current_week_tickets list 
def get_tasks(list_id): #list_name
    response = requests.get(f'{CLICKUP_API_ENDPOINT}/list/{list_id}/task', headers=HEADERS)
    if response.status_code != 200:
        print(f"Failed to fetch tasks")
        return []
    tickets = response.json().get('tasks', [])
    current_week_tickets = []  #list to store the current week bug tickets 
    #now = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
    #now = datetime.datetime(tz=timezone('Asia/Kolkata'))
    now = datetime.datetime.now(datetime.timezone.utc)   #checks the current date and time 
    #check the start of the current week 
    start_of_week = now - datetime.timedelta(days=now.weekday())   #start of the week i.e Monday now.weekdays() returns the day of week in integer Monday as 0 and Sunday as 6. By subtracting now with the timedelta it gives the most recent Monday.This gives the start of the current week 
    end_of_week = start_of_week + datetime.timedelta(days=4)       #end of the week i.e Friday .This operation will give the most recent end of the week i.e Friday as days=4
    #iterates through each tickets in the list
    for ticket in tickets:
        task_url = ticket.get('url')    
        task_id = ticket.get('id')
        #detailed_task = get_task(task_id)   #new line added
        #check the resolution is provided or not in the ticket 
        
        has_pr_link = False  #remove these two lines also 1    #intend from here
        #pr_link_value = 'No PR Link is attached' #2
        has_resolution = False   
        #resolution_value = 'No Resolution provided' #default when no value is provided 
        #Attempts to find the resolution field and update the resolution value if found 
        custom_fields = ticket.get('custom_fields')
        for field in ticket.get('custom_fields', []):
        #added pr link remove it after testing from here 
            if field.get('name') == 'PR Link':
                pr_link_value = field.get('value', 'No PR Link is attached')
                has_pr_link = True
                #break
        #if has_pr_link:
            #print(f'PR Link for ticket: {task_url} {pr_link_value}')
        #else:
            #print(f'PR Link for the ticket is not present : {task_url}')
            #ticket['prlink'] = pr_link_value #till here 
            elif field.get('name') == 'Resolution':
                resolution_value = field.get('value', 'No Resolution provided')
                has_resolution = True
                #break   #uncomment this 
        if has_resolution:
            print(f'Resolution for ticket : {task_url} : {resolution_value}')
        else:
            print(f'Failed to fetch the resolution for ticket : {task_url}')
        ticket['resolution'] = resolution_value
        if has_pr_link:
            print(f'PR Link for the ticket: {task_url} {pr_link_value}')
        else:
            print(f'PR Link for the ticet is not present')
        ticket['prlink'] = pr_link_value
        #gets the status of each ticket and remove any extra space from the status field and convert it to lowercase 
        status = ticket.get('status', {}).get('status', '').lower().replace(" ","")   #remove from here 
        status_type = ticket.get('status', {}).get('type')
        print(status_type)
        priority = ticket.get('priority', {})
        priority_type = priority.get('priority', '').lower() if priority and isinstance else 'none'
        date_created = datetime.datetime.fromtimestamp(int(ticket['date_created']) /1000 , tz=datetime.timezone.utc) #do not remove this
        formatted_date_created = date_created.strftime('%Y-%m-%d %H:%M:%S')
        ticket['date_created'] = formatted_date_created
        #Fetching assignee name from the tasks 
        assignees = ticket.get('assignees', [])
        if assignees:
            assignee_name = assignees[0].get('username', 'Unassigned')
            ticket['assignee_name'] = assignee_name
            print(f'Assignee for the task {task_url} {assignee_name}')
        else:
            print(f'Task is unassigned')
        #Fetching tags from the tasks 
        tags = ticket.get('tags', [])
        if tags:
            tag_name = tags[0].get('name', 'No tags')
        else:
            tag_name = 'No tags'
        ticket['tag_name'] = tag_name
        print(tag_name)
        print(formatted_date_created)
        #checks the ticket statuses and priority 
        #if status in ['open', 'pending(ack)','inprogress', 'planned', 'asdesigned', 'needscustomerresponse', 'duplicate', 'complete', 'externallimitation','invalid', 'customersidefix' ,'prraised' , 'prmerged', 'releasepending' , 'blocked'] and priority_type in ['urgent','high','normal','low']: #till here
        #if priority_type in ['urgent','high','normal','low']:
        if status_type in ['custom', 'done','open','closed'] and priority_type in ['urgent', 'high', 'normal','low']:
        #checks if the ticket is created withinn the current week 
            if start_of_week <= date_created <= end_of_week:
                comments = get_comments(task_id)
                if is_bug_based_on_comments(comments, priority_type):    #add priority type in function call 
                    print(f'Date created falls within the current week : IS BUG {task_url}')
                    current_week_tickets.append(ticket)
                    # pprint.pprint(ticket)
                else:
                    print(f'Ticket created within the current week but is NOT BUG : {task_url}')
                    continue
            else:
                print(f'Date created is outside of the current week: {task_url}')
                continue
    return current_week_tickets   #till here

#fetches the comment from each task 
def get_comments(task_id):
    comment_response = requests.get(f'{CLICKUP_API_ENDPOINT}/task/{task_id}/comment', headers=HEADERS)
    if comment_response.status_code == 200:
        comments = comment_response.json().get('comments', [])
        return comments
    else:
        return []
    

def get_lists(folder_id):
    response = requests.get(f'{CLICKUP_API_ENDPOINT}/folder/{folder_id}/list', headers=HEADERS)
    if response.status_code == 200:
        return response.json().get('lists', [])
    return []

def get_tickets_from_customer_lists(folder_id):
    lists = get_lists(folder_id)
    all_current_week_bug_tickets = []
    for list_item in lists:
        list_name = list_item.get('name')
        list_id = list_item.get('id')
        print(f'Fetching tickets from the list {list_name}')
        current_week_tickets = get_tasks(list_id)
        all_current_week_bug_tickets.extend(current_week_tickets)
        pprint.pprint(all_current_week_bug_tickets)
    send_weekly_report_for_sheet(all_current_week_bug_tickets)  #uncomment this 
    send_weekly_message_to_slack(all_current_week_bug_tickets)
    all_current_week_bug_tickets.clear()
    current_week_tickets.clear()
        # for ticket in tickets:
        #     task_id = ticket.get('id')
        #     task_name = ticket.get('name')
        #     task_url = ticket.get('url')
        #     status = ticket.get('status', {}).get('status', '').lower().replace(" ","")
        #     priority = ticket.get('priority', {})
        #     priority_type = priority.get('priority', '').lower() if priority and isinstance else 'none'
        #     if status in ['open', 'pending(ack)', 'planned', 'asdesigned','needcustomerresponse','duplicate','externallimitation','invalid','customersidefix', 'blocked','complete'] and priority_type in ['urgent','high','normal','low']:
        #         comments = get_comments(task_id)
        #         if is_bug_based_on_comments(comments):
        #             print(f'Bug ticket found {task_url}')
        #             bug_tickets.append(f'Ticket: {task_name} : URL; {task_url}')
    # if bug_tickets:
    #     message = f'Weekly bug report:\n' + '\n'.join(bug_tickets)
    #     print(message)
def send_weekly_report_for_sheet(bug_tickets):
    global scope, creds,client
    if not bug_tickets:
        print(f'No bug tickets found for this week!!!')
        return
    sheet = client.open('Weekly_Bug_Report').sheet1
    # all_records = sheet.get_all_records()
    # header_for_url = 'URL'
    all_values = sheet.get_all_values()
    #if len(all_values) == 0:
    headers = ["TASK NAME", "URL", "STATUS","PRIORITY", "DATE CREATED", "RESOLUTION", "ASSIGNEE_NAME", "TAGS","REQUEST TYPE", "PR LINK"]
    if not all_values or all_values[0] != headers:
        sheet.insert_row(headers,1)
    else:
        print(f'Header is already added no need to add header')
    #existing_urls = set(row[1] for row in all_values if len(row) > 1)  #this line is added remove this 
    existing_urls = set()
    for row in all_values:
        if len(row) > 1:
            url = row[1]
            existing_urls.add(url)
    # if len(all_values) == 0:
    #     headers = ["TASK NAME","URL","STATUS","PRIORITY"]
    #     sheet.insert_row(headers,1)
    # else:
    #     print(f'Header is already added no need to add header')
    for ticket in bug_tickets:
        if ticket['url'] not in existing_urls:
            row = [ticket['name'], ticket['url'], ticket['status']['status'], ticket['priority']['priority'],ticket['date_created'], ticket.get('resolution', 'no value provided'),ticket.get('assignee_name', 'Unassigned'), ticket['tag_name'], 'Bug', ticket['prlink']]
            sheet.append_row(row)
            print(f'Data for ticket : {ticket['url']} has been added to sheet')
            existing_urls.add(ticket['url'])
        else:
            print(f'Data for ticket : {ticket['url']} already exists in the sheet')   
    #     message += f'Ticket:{ticket["name"]} URL: {ticket['url']}\n'  
    # print(message)
    print(f'Data has been added to sheets')
    
    

#Function to send the weekly message to slack 
def send_weekly_message_to_slack(bug_tickets):
    if not bug_tickets:
        print(f'No bug ticket for the week.')
        return
    #construct the base message and then append the ticket name url etc in the next line 
    message = 'Bug tickets for current week:\n' 
    #iterates through each tickets from the list which is made of bug tickets of the current week  
    for ticket in bug_tickets:
        message+= f'Ticket: {ticket['name']} URL: {ticket['url']} Date: {ticket['date_created']}, Resolution: {ticket.get('resolution', 'No Resolution Provided')}\n'
    print(message)
    if send_message_slack(message):
        print(f'Mesage sent to slack successfully')  #uncomment this to work 
    else:
        print(f'Failed to send message to slack')

#Function to send message to slack 

def send_message_slack(message):
    payload = {
        'text' : f'{message}'    #uncomment this 
    }
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.get(SLACK_WEBHOOK_URL, json=payload , headers=headers)
    return response.status_code



# def analyze_bug_ticket_data():
#     sheet = client.open('Weekly_Bug_Report').sheet1
#     records = sheet.get_all_values()
#     headers = records[0]
#     data_row = records[1:]
#     print(records)    #for debugging
#     total_bugs = len(records)
#     priority_distribution = {'urgent':0,'high':0,'normal':0,'low':0}
#     status_distribution = {} #to be filled dynamically based on data 
#     records = []
#     for row in data_row:
#         record = {headers[i]: row[i] for i in range(len(headers))}
#         records.append(record)
#     for record in records:
#         priority = record.get('PRIORITY', 'N/A')
#         if priority in priority_distribution:
#             priority_distribution[priority] +=1
#         status = record.get('STATUS', 'N/A')
#         status_distribution[status] = status_distribution.get(status,0) + 1
#         status_percentage = {k: v / total_bugs * 100 for k, v in status_distribution.items()}
#         print(f"Total Bugs: {total_bugs}")
#         print(f"Priority Distribution: {priority_distribution}")
#         print(f"Status Percentage: {status_percentage}")
# analyze_bug_ticket_data()

def run_report():
    get_tickets_from_customer_lists(folder_id)
    

run_report()   #remove this as it is for testing purpose 

#Thread(target=schedule_report_of_bug_tickets).start()  #uncomment this 


# tickets = response.json().get('tasks', [])
    # for ticket in tickets:
    #     task_id = ticket.get('id')
    #     print(task_id)
    #     task_name = ticket.get('name')
    #     print(task_name)
    #     task_url = ticket.get('url')
    #     status_type = ticket.get('status', {}).get('status', '').lower().replace(" ", "")
    #     priority = ticket.get('priority', {})
    #     priority_type = priority.get('priority', '').lower() if priority and isinstance else 'none'
    #     if status_type in ['open', 'pending(ack)','planned','inprogress', 'asdesigned', 'needcustomerresponse'] and priority_type in ['urgent', 'high', 'normal', 'low']:
    #         print(status_type, priority_type)
    #         comment_response = requests.get(f'{CLICKUP_API_ENDPOINT}/task/86cu1qkv4/comment' , headers=HEADERS)
    #         if comment_response.status_code == 200:
    #             comments =  comment_response.json().get('comments', [])
    #             if is_bug_based_on_comments(comments):
    #                 print(f'Bug ticket found: {task_url}')
    #             # pprint.pprint(comments)