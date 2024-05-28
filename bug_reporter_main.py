# This is the actual script which runs on every Friday at 6PM and fetches all the bug tickets for that current week and sends a slack message for those ticket 
# To ensure that all the bug tickets for the current week are responded or not including the closed tickets also i.e which are in complete status.

#imports from Standard Library 
import requests
import datetime
import pprint
from dotenv import load_dotenv, find_dotenv
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import json
import schedule
from threading import Thread
from slack_sdk import WebClient #import for slack 
import os 
from emoji import emojize

#error handling when the .env file is not found
dotenv_path = find_dotenv()
load_result = load_dotenv()

# Check if the .env file was found in the system
if dotenv_path:
    load_result = load_dotenv(dotenv_path)
    print(f'File found at location {dotenv_path}')
    if load_result:
        print('Environment variable loaded successfully')
    else:
        print('Environment variable not loaded')
else:
    print(f'File not found')


# Constants 
CLICKUP_API_TOKEN = os.environ.get('CLICKUP_API_TOKEN')
#SLACK_WEBHOOK_URL = 'https://hooks.slack.com/triggers/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' #uncomment this #original webhook url for facets workspace 
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
CLICKUP_API_ENDPOINT = 'https://api.clickup.com/api/v2'
folder_id = '109448264'   #customer list folder id 
request_type_field_id = 'af553c42-561b-4260-93b0-ca2afa6b520f'                  
bug_id = '2c234b21-fb9a-49ad-bceb-0a342556e213'
existing_urls = set()
HEADERS = {
    'Authorization' : CLICKUP_API_TOKEN
}

# Function to schedule the report for sending every Friday at 6PM 
def schedule_report_of_bug_tickets():
    schedule.every().friday.at('18:00').do(run_report)
    while True:
        schedule.run_pending()
        time.sleep(60)

def safe_request(url, method='get', headers={}, params={}, retries=3, backoff_factor=0.5):  
    """Handle API requests with exponential backoff."""
    """
    Sends an HTTP request with retries and exponential backoff in case of errors or rate limits.

    Parameters:
    - url (str): The URL to which the request is sent.
    - method (str): HTTP method like 'get', 'post', etc.
    - headers (dict): HTTP headers to include in the request.
    - params (dict): URL parameters to append to the URL.
    - data (dict): Data to be sent as JSON payload.
    - retries (int): Number of retries if the request fails.
    - backoff_factor (float): Factor used to calculate the sleep time during retries.

    Returns:
    - JSON response data from the server if successful.
    Raises:
    - HTTPError: If a non-retryable HTTP error status is received.
    - RequestException: If retries are exhausted without a successful response.
    """
    for i in range(retries):
        try:
            response = requests.request(method, url, headers=headers, params=params, data={})
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                wait = int(response.headers.get('Retry-After', backoff_factor * (2 ** i)))
                print(f"Rate limit hit, retrying in {wait} seconds")
                time.sleep(wait)
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            if i < retries - 1:
                time.sleep(backoff_factor * (2 ** i))
            else:
                raise


def get_tasks(list_id): 
    """
    Fetches tasks from a specified ClickUp list using API requests with custom field filters.

    Parameters:
    - list_id (str): The unique identifier for the ClickUp list from which tasks are retrieved.
    
    Returns:
    - response (dict/json): The JSON response containing tasks from the specified list if the request is successful, or None if the request fails.

    Description:
    This function constructs an API request to ClickUp to fetch tasks from a specific list. 
    It includes filtering to only retrieve tasks that match certain custom field conditions i.e bug here.
    """   
    url = f'{CLICKUP_API_ENDPOINT}/list/{list_id}/task'
    custom_fields_filters = json.dumps([
        {"field_id": "af553c42-561b-4260-93b0-ca2afa6b520f", "operator":"=", "value": "2c234b21-fb9a-49ad-bceb-0a342556e213"}  #field id is reqquest type field id and value is bug id
    ])
    #added params to include the closed tickets
    params = {
        "include_closed": "true",
        "custom_fields": custom_fields_filters
    }
    response = safe_request(url, method='get', headers=HEADERS, params=params)
    if response is None:
        print(f"Failed to fetch tasks after retries")
        return []
    tickets = response.get('tasks', [])        
    processed_tickets = process_tickets(tickets)
    return processed_tickets

def process_tickets(tickets):
    """
    Processes a list of tickets by filtering based on creation date and enriching each ticket with additional data.
    
    Parameters:
    - tickets (list): A list of ticket dictionaries, each representing a task fetched from an API.

    Returns:
    - list: A list of tickets that were created within the current week and meet certain criteria.
    """
    current_week_tickets = []  #list to store the current week bug tickets 
    now = datetime.datetime.now(datetime.timezone.utc)   #checks the current date and time 
    #check the start of the current week 
    start_of_week = now - datetime.timedelta(days=now.weekday())   #start of the week i.e Monday now.weekdays() returns the day of week in integer Monday as 0 and Sunday as 6. By subtracting now with the timedelta it gives the most recent Monday.This gives the start of the current week 
    print(f'Start of the week: {start_of_week}')
    end_of_week = start_of_week + datetime.timedelta(days=4)       #end of the week i.e Friday .This operation will give the most recent end of the week i.e Friday as days=4
    print(f'End of week: {end_of_week}')
    #iterates through each tickets in the list
    for ticket in tickets:
        if isinstance(ticket['date_created'], datetime.datetime):
            date_created = ticket['date_created']
        else:
            date_created = datetime.datetime.fromtimestamp(int(ticket['date_created']) /1000 , tz=datetime.timezone.utc)
        formatted_date_created = date_created.strftime('%Y-%m-%d %H:%M:%S')
        ticket['date_created'] = formatted_date_created
        is_current_week = is_within_current_week(date_created, start_of_week, end_of_week)
        if is_current_week:
            ticket_data(ticket)
            if status_and_priority(ticket):
                current_week_tickets.append(ticket)
    return current_week_tickets
  

def is_within_current_week(date_created, start_of_week, end_of_week):
    """
    Determines if the ticket was created within the current week.
    """
    return start_of_week <= date_created <= end_of_week

def ticket_data(ticket):
    """
    Enriches ticket data with resolution, PR link, assignee name, and tags.
    """
    ticket['resolution'] = get_custom_field(ticket, 'Resolution', 'No Resolution provided')
    ticket['prlink'] = get_custom_field(ticket, 'PR Link', 'No PR Link attached')
    assignees = ticket.get('assignees', [])
    ticket['assignee_name'] = assignees[0].get('username', 'Unassigned') if assignees else 'Unassigned'
    tags = ticket.get('tags', [])
    ticket['tag_name'] = tags[0].get('name', 'No tags') if tags else 'No tags'


def get_custom_field(ticket, field_name, default_value):
    """
    Retrieves the value of a specific custom field from a ticket's data structure. If the specified
    field is not found, a default value is returned.

    Parameters:
    - ticket (dict): The ticket dictionary containing potentially nested data including custom fields.
    - field_name (str): The name of the custom field to retrieve.
    - default_value (any): The default value to return if the custom field is not found.

    Returns:
    - The value of the custom field if found, otherwise the default value.

    This function iterates over the list of custom fields in a ticket, checks if the desired field 
    name matches the current field in the loop, and returns the field's value if found. If the loop 
    completes without finding the field, the default value is returned.
    """
    for field in ticket.get('custom_fields', []):
        if field.get('name') == field_name:
            return field.get('value', default_value)
        return default_value
    
def status_and_priority(ticket):
    """
    Evaluates whether a ticket meets specific criteria based on its status and priority to determine if it should be included in further processing.

    Parameters:
    - ticket (dict): The ticket dictionary containing status and priority information.

    Returns:
    - bool: True if the ticket meets the inclusion criteria, False otherwise.

    This function checks the status and priority of a ticket against predefined acceptable values.
    A ticket is included if its status is one of ['custom', 'done', 'open', 'closed'] and its
    priority is one of ['urgent', 'high', 'normal', 'low']. This helps filter tickets for 
    processing based on relevant business rules or operational requirements.
    """
    status_type = ticket.get('status', {}).get('type', '').lower()
    priority_type = ticket.get('priority', {}).get('priority', '').lower()
    return status_type in ['custom', 'done', 'open', 'closed'] and priority_type in ['urgent', 'high', 'normal', 'low']

def get_lists(folder_id):
    """
    Fetches all lists from a specified ClickUp folder using the ClickUp API.

    Parameters:
    - folder_id (str): The unique identifier for the ClickUp folder from which to fetch the lists.

    Returns:
    - list: A list of dictionaries, each representing a list within the specified folder. Returns an empty list if the fetch fails or if there are no lists.

    The function sends a GET request to the ClickUp API to retrieve all lists associated with the specified folder ID.
    It handles the response by checking the HTTP status code. If the response is successful (HTTP 200), it extracts
    and returns the 'lists' data from the JSON response. If the response is not successful, or if no lists data is 
    available, it returns an empty list.
    """
    response = requests.get(f'{CLICKUP_API_ENDPOINT}/folder/{folder_id}/list', headers=HEADERS)
    if response.status_code == 200:
        return response.json().get('lists', [])
    return []

def get_tickets_from_customer_lists(folder_id):
    """
    Retrieves and processes tickets from all lists within a specified ClickUp folder.

    Parameters:
    - folder_id (str): The unique identifier for the ClickUp folder from which to fetch lists and their tickets.

    Description:
    This function first retrieves all lists within the specified folder. It then iterates through each list,
    fetching tickets, enriching them with additional data, and collecting tickets that meet specific criteria
    (e.g., being created within the current week). The tickets are also tagged with the name of the list they came from
    for better identification and traceability in subsequent processing or reporting.

    The function handles the aggregation of tickets from multiple lists and manages communication with Slack
    by sending a summary message of all relevant tickets. It concludes by clearing any temporary collections
    to free up resources and avoid potential data leaks between executions.
    """
    lists = get_lists(folder_id)
    all_current_week_bug_tickets = []
    for list_item in lists:
        list_name = list_item.get('name')
        list_id = list_item.get('id')
        print(f'Fetching tickets from the list {list_name}')
        current_week_tickets = get_tasks(list_id)
        for ticket in current_week_tickets:
            ticket['list_name'] = list_name
        all_current_week_bug_tickets.extend(current_week_tickets)
        pprint.pprint(all_current_week_bug_tickets)
    send_weekly_message_to_slack(all_current_week_bug_tickets)
    all_current_week_bug_tickets.clear()
    current_week_tickets.clear()
    

#Function to send the weekly message to slack 
def send_weekly_message_to_slack(bug_tickets):
    """
    Sends a formatted message to Slack summarizing the bug tickets collected over the current week.

    Parameters:
    - bug_tickets (list of dict): A list of dictionaries, each representing a bug ticket that has been processed and deemed relevant for the current week.

    Process:
    - The function first checks if there are any bug tickets to report. If the list is empty, it prints a message indicating no tickets were found and returns.
    - Constructs a base message which is a prompt to check the status of bug tickets. This message uses an emoji for visual emphasis.
    - Iterates over each ticket in the provided list, appending detailed information about each ticket to the message. This includes the customer from which the ticket originated, the ticket's name, URL, the date it was created, and its resolution status.
    - After constructing the complete message, it attempts to send this message to Slack using the `send_message_slack` function.
    - Prints a success message if the message was sent successfully, otherwise, it logs a failure message.

    Note:
    - This function assumes that the `send_message_slack` function is defined elsewhere in the codebase and is responsible for handling the actual communication with Slack's API.
    - The use of `emojize` suggests that the message includes emojis, which are intended to make the alert more noticeable or to enhance readability in the Slack environment.
    """
    if not bug_tickets:
        print(f'No bug ticket for the week.')
        return
    #construct the base message and then append the ticket name url etc in the next line 
    message = f'Check if all the Bug tickets for current week are responded and closed: \n'
               
    #iterates through each tickets from the list which is made of bug tickets of the current week  
    for ticket in bug_tickets:
        message+= f'From Customer: {ticket['list_name']} Ticket: {ticket['name']} URL: {ticket['url']} Date: {ticket['date_created']}, Resolution: {ticket.get('resolution', 'No Resolution Provided')}\n'
    print(message)
    if send_message_slack(message):
        print(f'Message sent to slack successfully')  
    else:
        print(f'Failed to send message to slack')


def send_message_slack(message):
    """
    Sends a specified message to a Slack channel using a predefined webhook URL.

    Parameters:
    - message (str): The message content that will be sent to Slack.

    Returns:
    - int: The HTTP status code returned by the Slack API, indicating the success or failure of the message delivery.

    Process:
    - Constructs a payload dictionary with the message text.
    - Sets up the necessary headers for a JSON content type to ensure proper data handling by the API.
    - Sends the message to Slack using an HTTP GET request to the predefined Slack webhook URL, which is configured to accept messages.
    - Returns the HTTP status code from the response, which can be used to determine if the message was successfully posted or if there was an error.

    Note:
    - The function assumes that the `SLACK_WEBHOOK_URL` variable is globally defined and correctly set to a valid Slack webhook URL.
    - This function uses an HTTP GET request with payload, which is unconventional for sending data. Typically, Slack webhooks expect an HTTP POST request. If there are issues with message delivery, check if changing to a POST request resolves them.
    """
    payload = {
        'text' : f'{message}'  
    }
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.get(SLACK_WEBHOOK_URL, json=payload , headers=headers)
    return response.status_code


def run_report():
    get_tickets_from_customer_lists(folder_id)
    
if __name__ == '__main__':
    run_report()   #remove this as it is for testing purpose 
    #Thread(target=schedule_report_of_bug_tickets).start()     #Uncomment this so that the script is scheduled to be run on every Friday at 6PM
    