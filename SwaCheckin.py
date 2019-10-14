import sys
import argparse
import smtplib
import requests
import yaml
from datetime import datetime
from time import sleep
from os import getcwd

checkin_url= 'https://mobile.southwest.com/api/mobile-air-operations/v1/mobile-air-operations/page/check-in'
req_headers = {'Host': 'mobile.southwest.com', 'X-API-Key': 'l7xx0a43088fe6254712b10787646d1b298e'}

def main(argv):
    # SwaCheckin.py -c <confirmation #> -l <lastName> -f <firstName> [-e <email>]
    # or use: SwaCheckin.py --confirmation=<confirmation> --lastName=<lastName> --firstName=<firstName> [--email <email>]

    help_text=f"""Check in to SWA flights exactly 24 hours in advance. After check-in, an 
email is sent with an itinerary summary and URLs for all boarding passes in a reservation. 
An error email is sent if check-in fails. Reservations with multiple passengers will have 
all passengers checked in and included in the itinerary summary email. The name of any 
passenger in the reservation will work. SMTP configuration path - {getcwd()}/smtp.yml"""

    parser = argparse.ArgumentParser(description = help_text)
    rn = parser.add_argument_group('required named arguments')
    rn.add_argument('-c','--confirmation',help = 'Flight confirmation number (record locator)', required = True)
    rn.add_argument('-l','--lastname',help = 'Last name',required = True)
    rn.add_argument('-f','--firstname',help = 'First name',required = True)
    parser.add_argument('-e','--email',help = 'Recipient email address')
    return vars(parser.parse_args())
            
def retrieve_checkin_data(confirmation, last_name, first_name):
    url = f'{checkin_url}/confirmation'
    query = {'first-name': first_name, 'last-name': last_name}
    req = requests.get(url, headers=req_headers, params=query)
    return req.json()
    
def checkin(confirmation, last_name, first_name, checkin_token):
    req_data = {'firstName': first_name, 'lastName': last_name, 'recordLocator': confirmation,
                'checkInSessionToken': checkin_token}
    #request will take care of passing this data as JSON
    req = requests.post(checkin_url, headers=req_headers, json=req_data)
    return req.json()
    
def retrieve_boarding_pass(confirmation, last_name, first_name, traveler_id):
    url = f'{checkin_url}/retrieve-boarding-pass/confirmation'
    req_data = {'firstName': first_name, 'lastName': last_name, 'recordLocator': confirmation,
                'travelerID': [traveler_id]}
    req = requests.post(url, headers=req_headers, json=req_data)
    return req.json()

def email_config():
    with open(f'{getcwd()}/smtp.yml', 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as ex:
            print(ex)

def send_email(subject, text, recipient, email_config):
    FROM = email_config['from']
    TO = [recipient]
    SUBJECT = f"SWA check-in - {subject}"
    TEXT = text
    
    message = f"From: {FROM}\nTo: {', '.join(TO)}\nSubject: {SUBJECT}\n\n{TEXT}"
    
    try:
        server = smtplib.SMTP(email_config['address'], 587)
        server.ehlo()
        server.starttls()
        server.login(email_config['username'], email_config['password'])
        server.sendmail(FROM, TO, message)
        server.close()
        print(f"successfully sent email - {subject}")
    except Exception as ex:
        print(f"failed to send email - {subject}\n{str(ex)}")
              
if __name__ == "__main__":
    args = main(sys.argv[1:])
    confirmation = args['confirmation']
    last_name = args['lastname']
    first_name = args['firstname']
    email = args['email']

    # retry check-in if error response
    for i in range(15,0,-1):        
        ci_data_response = retrieve_checkin_data(confirmation, last_name, first_name)
        if 'code' in ci_data_response:
            print(f'Retries remaining: {str(i - 1)} -- Check-in error -- error body from SWA below.')
            print(ci_data_response['message'])            
            if not (i - 1):
                print('check-in failed')
                if email:
                    send_email('check-in failed', f'{confirmation} {last_name} {first_name}', email, email_config())
                sys.exit(1)
            sleep(0.5)
        else:
            break    
    checkin_token = ci_data_response['checkInSessionToken']
    
    checkin_response = checkin(confirmation, last_name, first_name, checkin_token)   
    
    boarding_pass_out = ''
    for passenger in checkin_response['checkInConfirmationPage']['flights'][0]['passengers']:
        b_pass_response = retrieve_boarding_pass(confirmation, last_name, first_name, passenger['travelerID'])
        boarding_pass_out += f'Boarding passes for {passenger["name"]} \n' 
        for b_pass in b_pass_response['checkInRetrieveBoardingPassPage']['mobileBoardingPassViewPage']['mobileBoardingPassView']:
            boarding_pass_out += (f'    Flight {b_pass["flightNumber"]} {b_pass["originAirportDescription"]} to '
                f'{b_pass["destinationAirportDescription"]} departing {b_pass["departureTime"]} '
                f'- boarding position {b_pass["boardingGroup"]} {b_pass["boardingPosition"]}'
                f'\n    Open on a mobile device: {b_pass["adaptiveLink"]}\n\n')
        boarding_pass_out += '\n\n'
        
    if email:
        send_email(confirmation, boarding_pass_out, email, email_config())
    print(boarding_pass_out)
