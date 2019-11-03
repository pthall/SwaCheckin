# SwaCheckin.py -c <confirmation #> -l <lastName> -f <firstName> [-e <email>]
# or use: SwaCheckin.py --confirmation=<confirmation> --lastName=<lastName> --firstName=<firstName> [--email <email>]

import sys
import argparse
import smtplib
import requests
import yaml
import pytz
import dateutil.parser
import ntplib
from datetime import datetime
from datetime import timedelta
from time import sleep
from os import path

CHECKIN_URL = 'https://mobile.southwest.com/api/mobile-air-operations/v1/mobile-air-operations/page/check-in'
REQ_HEADERS = {'Host': 'mobile.southwest.com', 'X-API-Key': 'l7xx0a43088fe6254712b10787646d1b298e'}


def main(argv):
    help_text = f"""Check in to SWA flights exactly 24 hours in advance. After check-in, an 
email is sent with an itinerary summary and URLs for all boarding passes in a reservation. 
An error email is sent if check-in fails. Reservations with multiple passengers will have 
all passengers checked in and included in the itinerary summary email. The name of any 
passenger in the reservation will work. For roundtrip reservations, all outbound and 
return flights will be queued for check-in. 
SMTP configuration path - {path.dirname(path.realpath(__file__))}/smtp.yml"""

    parser = argparse.ArgumentParser(description=help_text)
    rn = parser.add_argument_group('required named arguments')
    rn.add_argument('-c', '--confirmation', help='Flight confirmation number (record locator)', required=True)
    rn.add_argument('-l', '--lastname', help='Last name', required=True)
    rn.add_argument('-f', '--firstname', help='First name', required=True)
    parser.add_argument('-e', '--email', help='Recipient email address')
    return vars(parser.parse_args())


# API request for reservation summary; not dependent on check-in eligibility
def retrieve_reservation(confirmation, last_name, first_name):
    url = f'https://mobile.southwest.com/api/mobile-air-booking/v1/mobile-air-booking/page/view-reservation/{confirmation}'
    query = {'first-name': first_name, 'last-name': last_name}
    req = requests.get(url, headers=REQ_HEADERS, params=query)
    return req.json()


# 'checkInSessionToken' key is included in API response
# only when reservation is eligible for check-in
def retrieve_checkin_data(confirmation, last_name, first_name):
    url = f'{CHECKIN_URL}/{confirmation}'
    query = {'first-name': first_name, 'last-name': last_name}
    req = requests.get(url, headers=REQ_HEADERS, params=query)
    return req.json()


# ['checkInConfirmationPage']['flights'][0]['passengers'][0]['travelerID']
# in API response needed to retrieve boarding pass(es)
def checkin(confirmation, last_name, first_name, checkin_token):
    req_data = {'firstName': first_name, 'lastName': last_name, 'recordLocator': confirmation,
                'checkInSessionToken': checkin_token}
    # request will take care of passing this data as JSON
    req = requests.post(CHECKIN_URL, headers=REQ_HEADERS, json=req_data)
    return req.json()


# ['checkInRetrieveBoardingPassPage']['mobileBoardingPassViewPage']
# ['mobileBoardingPassView'][0] contains the boarding pass
def retrieve_boarding_pass(confirmation, last_name, first_name, traveler_id):
    url = f'{CHECKIN_URL}/retrieve-boarding-pass/{confirmation}'
    req_data = {'firstName': first_name, 'lastName': last_name, 'recordLocator': confirmation,
                'travelerID': [traveler_id]}
    req = requests.post(url, headers=REQ_HEADERS, json=req_data)
    return req.json()


# parse SMTP config file
def email_config():
    with open(f'{path.dirname(path.realpath(__file__))}/smtp.yml', 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as ex:
            print(ex)


# send templated emails
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


# print flight status; return only flights to be checked in
def flight_info_status_filter(flight_info):
    print("\n---- list of all flights and their check-in eligibility ----")
    filtered_info = []
    for flight in flight_info:
        print(f"{flight['header']} - {flight['departureInfo']}\n{flight['title']}")
        departure_date = dateutil.parser.parse(flight['departureDateTime'])
        time_delta = departure_date - datetime.now().astimezone(pytz.timezone("UTC")) - timedelta(seconds=seconds_offset)
        if time_delta <= timedelta(days=1) and time_delta >= timedelta(seconds=0):
            print(f"departure in {time_delta} -- check-in will occur in a moment\n")
            filtered_info.append(flight)
        elif time_delta > timedelta(days=1):
            print(f"check-in will occur at {departure_date - timedelta(days=1)} -- {time_delta - timedelta(days=1)} from now\n")
            filtered_info.append(flight)
        else:
            print("this flight won't be checked in\n")
    return filtered_info


# start check-in and return response
def start_checkin(flight):
    # retry retrieve check-in if error response
    for i in range(15, 0, -1):
        ci_data_response = retrieve_checkin_data(confirmation, last_name, first_name)
        # code key only present on an error
        if 'code' in ci_data_response:
            print(f'Retries remaining: {str(i - 1)} -- Check-in error -- error body from SWA below.')
            print(ci_data_response['message'])
            if not (i - 1):
                print('check-in failed')
                if email:
                    send_email('check-in failed', f'{confirmation} {last_name} {first_name}', email, email_config())
                break
            sleep(0.5)
        else:
            # return check-in response
            return checkin(confirmation, last_name, first_name, ci_data_response['checkInSessionToken'])


# get boarding pass(es) text for passenger
def boarding_pass_text(passenger):
    b_pass_response = retrieve_boarding_pass(confirmation, last_name, first_name, passenger['travelerID'])
    boarding_pass_text = f'Boarding passes for {passenger["name"]} \n'
    for b_pass in b_pass_response['checkInRetrieveBoardingPassPage']['mobileBoardingPassViewPage']['mobileBoardingPassView']:
        boarding_pass_text += (
            f'    Flight {b_pass["flightNumber"]} {b_pass["originAirportDescription"]} to '
            f'{b_pass["destinationAirportDescription"]} departing {b_pass["departureTime"]} '
            f'- boarding position {b_pass["boardingGroup"]} {b_pass["boardingPosition"]}'
            f'\n    Open on a mobile device: {b_pass["adaptiveLink"]}\n\n')
    return boarding_pass_text


# return seconds offset between NTP time and local system time
# positive value indicates system time is behind
def ntp_offset():
    return ntplib.NTPClient().request('pool.ntp.org').offset


if __name__ == "__main__":
    args = main(sys.argv[1:])
    confirmation = args['confirmation']
    last_name = args['lastname']
    first_name = args['firstname']
    email = args['email']

    resv_response = retrieve_reservation(confirmation, last_name, first_name)
    if 'code' in resv_response:
        print(f'error retrieving reservation -- error body from SWA below.')
        print(resv_response['message'])
        if email:
            send_email('reservation not found', f'{confirmation} {last_name} {first_name}', email, email_config())
        sys.exit(1)

    seconds_offset = ntp_offset()
    print(f'NTP offset of {seconds_offset} seconds now in effect')

    filtered_flights = flight_info_status_filter(resv_response['viewReservationViewPage']['shareDetails']['flightInfo'])

    if(len(filtered_flights)):
        for flight in filtered_flights:
            print("\n---- check-in queue status ----")
            print(f"{flight['header']} - {flight['departureInfo']}\n{flight['title']}")
            departure_date = dateutil.parser.parse(flight['departureDateTime'])
            time_delta = departure_date - datetime.now().astimezone(pytz.timezone("UTC")) - timedelta(seconds=seconds_offset)
            if time_delta <= timedelta(days=1) and time_delta >= timedelta(seconds=0):
                print(f"departure in {time_delta} -- starting check-in\n")
                checkin_response = start_checkin(flight)
            elif time_delta > timedelta(days=1):
                print(f"check-in will occur at {departure_date - timedelta(days=1)} -- {time_delta - timedelta(days=1)} from now\n")
                sleep(time_delta.total_seconds() - timedelta(days=1).total_seconds())
                checkin_response = start_checkin(flight)
            else:
                print("error: this flight doesn't look eligible for check-in")

            boarding_pass_out = ''
            for passenger in checkin_response['checkInConfirmationPage']['flights'][0]['passengers']:
                boarding_pass_out += boarding_pass_text(passenger)

            if email:
                send_email(confirmation, boarding_pass_out, email, email_config())
            print(boarding_pass_out)
