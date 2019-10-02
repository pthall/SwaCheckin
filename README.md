# SwaCheckin
```usage: SwaCheckin.py [-h] -c CONFIRMATION -l LASTNAME -f FIRSTNAME [-e EMAIL]

Check in to SWA flights exactly 24 hours in advance. Use cron or another job
scheduler to schedule execution. After check-in, an email is sent with an
itinerary summary and URLs for all boarding passes in a reservation. An error
email is sent if check-in fails. Reservations with multiple passengers will
have all passengers checked in and included in the itinerary summary email.
The name of any passenger in the reservation will work. No emails will be
sent if the email parameter is not specified. Provide SMTP settings in
smtp.yml - see example_smtp.yml 

optional arguments:
  -h, --help            show this help message and exit
  -e EMAIL, --email EMAIL
                        Recipient email address

required named arguments:
  -c CONFIRMATION, --confirmation CONFIRMATION
                        Flight confirmation number.
  -l LASTNAME, --lastname LASTNAME
                        Last name
  -f FIRSTNAME, --firstname FIRSTNAME
                        First name
