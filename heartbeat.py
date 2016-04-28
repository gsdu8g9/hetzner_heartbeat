import os
import re
import sys
import syslog
import signal
import smtplib
import time
import subprocess
import ConfigParser
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

# Check that our dependencies are installed
try:
    import requests
except:
    sys.exit("ERROR: python-requests not found. Please make sure it is installed.")

try:
    cmd_exists = lambda x: any(os.access(os.path.join(path, x), os.X_OK) for path in os.environ["PATH"].split(os.pathsep))
    cmd_exists('fping')
except:
    sys.exit("ERROR: Couldn't find fping. Please make sure it is installed.\n")

# Load the configuration and logging facility
try:
    config = ConfigParser.ConfigParser()
    config.readfp(open('heartbeat.cfg'))
    syslog.openlog("Heartbeat", logoption=syslog.LOG_PID)
    debug = config.getboolean('debug', 'debug')
    if debug:
        print("Debug mode is active!")
except:
    sys.exit("ERROR: Couldn't load the configuration file.\n")

failover_ip = config.get('heartbeat', 'failover_ip')
timeout = config.get('heartbeat', 'timeout')
count = config.get('heartbeat', 'count')
tries = config.get('heartbeat', 'tries')
pidfile = config.get('heartbeat', 'pidfile')
interval = config.getint('heartbeat', 'interval')
servers = config.get('heartbeat', 'servers').replace(" ", "").split(",")
username = config.get('authentication', 'username')
password = config.get('authentication', 'password')
base_url = config.get('authentication', 'base_url')
origin_email = config.get('email', 'origin_email')
smtp_server = config.get('email', 'smtp_server')
smtp_username = config.get('email', 'smtp_username')
smtp_password = config.get('email', 'smtp_password')
smtp_port = config.getint('email', 'smtp_port')
smtp_tls = config.getboolean('email', 'tls')
smtp_recipient = config.get('email', 'recipient')


def handle_death(signum, frame):
    """Handle kill/death signals from the system."""
    syslog.syslog("ERROR: Process tripped over a banana and died.")
    sys.exit(1)

try:
    for sig in (signal.SIGABRT, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle_death)
except:
    syslog.syslog("ERROR: Couldn't load signal handler.")
    sys.exit(1)


def create_pid():
    """Create PID file for this process."""
    pid = str(os.getpid())
    if os.path.isfile(pidfile):
        print("Process {} already exists".format(pidfile))
        sys.exit()
    else:
        open(pidfile, 'w').write(pid)


def send_email(msg_text):
    """Send a notification email.

    Send a notification email to a predefined recepit in the configuration
    so any actions in the heartbeat are notified.
    """
    try:
        # Build the message
        msg = MIMEMultipart()
        if debug:
            msg['Subject'] = "[DEBUG] Failover IP notification"
        else:
            msg['Subject'] = "Failover IP notification"
        msg['From'] = origin_email
        msg['To'] = smtp_recipient
        msg.attach(MIMEText(msg_text))

        # Establish the connection
        conn = smtplib.SMTP(smtp_server, smtp_port)
        conn.set_debuglevel(True)
        conn.ehlo()
        if smtp_tls:
            conn.starttls()
        conn.login(smtp_username, smtp_password)

        # Send the actual email
        conn.sendmail(origin_email, smtp_recipient, msg.as_string())
        conn.quit()
    except Exception as e:
        print(e)
        print("ERROR: There was an error while sending the email.")


def check_current_ip(failover_ip):
    """Check the current failover ip.

    This will request the current active ip for the failover ip address. If the
    response is 200 (OK) it will return the active ip to be processed later,
    otherwise we consider the request failed.

    Args:
        failover_ip (str): Failover IP address as a string.
    """
    r = requests.get(base_url + failover_ip, auth=(username, password))
    if r.status_code == 200:
        active_ip = r.json()['failover']['active_server_ip']
        if debug:
            send_email("[DEBUG] Current active IP for {} is {}".format(failover_ip, active_ip))
        return active_ip
    else:
        send_email("ERROR: Couldn't get the active server ip.")


def set_new_ip(failed_ip):
    """Set new active IP afor the Failover IP.

    This function will get the current active ip from the failover ip (the one
    that ping has reported as failing) as set it as the last in the list of
    active ips to set. Then we grab the new first itmen of the list and keep
    trying.
    """
    # Move the failed ip to the last position
    servers.insert(len(servers), servers.pop(servers.index(failed_ip)))
    new_ip = servers[0]
    if debug:
        send_email("[DEBUG] Active IP for {} will be {}".format(failover_ip, new_ip))
    else:
        r = requests.post(base_url + failover_ip, auth=(username, password),
                          params={'active_server_ip': new_ip})
        if r.status_code != 200:
            send_email("ERROR: Couldn't set new active ip for {}. New ip: {}".format(failover_ip, new_ip))
        else:
            send_email("CHANGED: Active IP for {} has been changed to {}".format(failover_ip, new_ip))
    # Hezter takes up to 20 seconds to propagate, so we have to wait
    time.sleep(25)


def do_ping():
    """Run the ping process for the failover ip.

    This is the main function that will do the work. It will continuously ping
    the failover ip at the specified interval with the configured options, if
    the return code of the process if different than 0 we assume that the
    current active ip that the failover ip has is down (either dead or
    with network problems) and we trigger the mechanism to fin the current
    ip and set a new one.
    """
    FNULL = open(os.devnull, 'w')
    ping = subprocess.Popen(["fping", "-c", count, "-t", timeout, "-r",
                             tries, failover_ip],
                            stdout=FNULL, stderr=subprocess.STDOUT)
    # This just empties the buffer so we can get the return code.
    streamdata = ping.communicate()[0]

    if debug:
        print("Ping returns: {}".format(ping.returncode))
    if ping.returncode != 0:
        failed_ip = check_current_ip(failover_ip)
        set_new_ip(failed_ip)
    time.sleep(interval)

while True:
    do_ping()
