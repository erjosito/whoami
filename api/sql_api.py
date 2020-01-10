import pyodbc
import os
import socket, struct
import sys
import time
import warnings
import requests
from flask import Flask
from flask import request
from flask import jsonify

def init_odbc(cx_string):
    cnxn = pyodbc.connect(cx_string)
    return cnxn

def get_sqlversion(cx):
    cursor = cx.cursor()
    cursor.execute('SELECT @@VERSION')
    return cursor.fetchall()

def send_sql_query():

    # Get environment variables
    sql_server_username=os.environ.get('SQL_SERVER_USERNAME')
    sql_server_password=os.environ.get('SQL_SERVER_PASSWORD')
    sql_server_fqdn=os.environ.get('SQL_SERVER_FQDN')

    # If any variable was not provided, check for configuration files
    basis_path='/secrets'
    # SQL_SERVER_USERNAME:
    if sql_server_username == None and os.path.isfile(variable_path):
        variable_path = os.path.join(basis_path,'SQL_SERVER_USERNAME')
        with open(variable_path, 'r') as file:
            sql_server_username = file.read().replace('\n', '')
    # SQL_SERVER_PASSWORD:
    if sql_server_password == None and os.path.isfile(variable_path):
        variable_path = os.path.join(basis_path,'SQL_SERVER_PASSWORD')
        with open(variable_path, 'r') as file:
            sql_server_password = file.read().replace('\n', '')
    # SQL_SERVER_FQDN:
    if sql_server_fqdn == None and os.path.isfile(variable_path):
        variable_path = os.path.join(basis_path,'SQL_SERVER_FQDN')
        with open(variable_path, 'r') as file:
            sql_server_fqdn = file.read().replace('\n', '')

    # Check we have the right variables
    if sql_server_username == None or sql_server_password == None or sql_server_fqdn == None:
        print('Required environment variables not present')
        return 'Required environment variables not present'

    # Build connection string
    cx_string=''
    drivers = pyodbc.drivers()
    # print('Available ODBC drivers:', drivers)   # DEBUG
    if len(drivers) == 0:
        print('Oh oh, it looks like you have no ODBC drivers installed :(')
        return "No ODBC drivers installed"
    else:
        # Take first driver, for our basic stuff any should do
        driver = drivers[0]
        # cx_string = "Driver={{{0}}};Server=tcp:{1},1433;Database={2};Uid={3};Pwd={4};Encrypt=yes;TrustServerCertificate=yes;Connection Timeut=30;".format(driver, sql_server_fqdn, sql_server_db, sql_server_username, sql_server_password)
        cx_string = "Driver={{{0}}};Server=tcp:{1},1433;Uid={2};Pwd={3};Encrypt=yes;TrustServerCertificate=yes;Connection Timeut=30;".format(driver, sql_server_fqdn, sql_server_username, sql_server_password)
        # print('DEBUG - conn string:', cx_string)

    # Connect to DB
    print('Connecting to database server', sql_server_fqdn, '-', get_ip(sql_server_fqdn), '...')
    try:
        cx = init_odbc(cx_string)
    except Exception as e:
        print('Connection to the database failed, you might have to update the firewall rules?')
        print(e)
        return "Connection to the database failed, you might have to update the firewall rules?"

    # Send SQL query
    print('Sending SQL query to find out database version...')
    try:
        sql_output = get_sqlversion(cx)
        return str(sql_output)
    except:
        print('Error sending query to the database')
        return None

# Get IP for a DNS name
def get_ip(d):
    try:
        return socket.gethostbyname(d)
    except Exception:
        return False

app = Flask(__name__)

# Return True if IP address is valid
def is_valid_ipv4_address(address):
    try:
        socket.inet_pton(socket.AF_INET, address)
    except AttributeError:  # no inet_pton here, sorry
        try:
            socket.inet_aton(address)
        except socket.error:
            return False
        return address.count('.') == 3
    except socket.error:  # not a valid address
        return False
    return True

# Get IP addresses of DNS servers
def get_dns_ips():
    dns_ips = []
    with open('/etc/resolv.conf') as fp:
        for cnt, line in enumerate(fp):
            columns = line.split()
            if columns[0] == 'nameserver':
                ip = columns[1:][0]
                if is_valid_ipv4_address(ip):
                    dns_ips.append(ip)
    return dns_ips

# Get default gateway
def get_default_gateway():
    """Read the default gateway directly from /proc."""
    with open("/proc/net/route") as fh:
        for line in fh:
            fields = line.strip().split()
            if fields[1] != '00000000' or not int(fields[3], 16) & 2:
                continue

            return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))

# Flask route for healthchecks
@app.route("/healthcheck", methods=['GET'])
def healthcheck():
    if request.method == 'GET':
        try:
          msg = {
            'health': 'OK'
          }          
          return jsonify(msg)
        except Exception as e:
          return jsonify(str(e))

# Flask route to ping the SQL server with a basic SQL query
@app.route("/sql", methods=['GET'])
def sql():
    if request.method == 'GET':
        try:
          sql_output = send_sql_query()
          msg = {
            'sql_output': sql_output
          }          
          return jsonify(msg)
        except Exception as e:
          return jsonify(str(e))

# Flask route to provide the container's IP address
@app.route("/ip", methods=['GET'])
def ip():
    if request.method == 'GET':
        try:
            # url = 'http://ifconfig.co/json'
            url = 'http://jsonip.com'
            mypip_json = requests.get(url).json()
            mypip = mypip_json['ip']
            if request.headers.getlist("X-Forwarded-For"):
                forwarded_for = request.headers.getlist("X-Forwarded-For")[0]
            else:
                forwarded_for = None
            if os.environ.get('SQL_SERVER_FQDN'):
                sql_server_fqdn = os.environ.get('SQL_SERVER_FQDN')
                sql_server_ip = get_ip(sql_server_fqdn)
            else:
                root_path = '/secrets'
                file_name = 'SQL_SERVER_FQDN'
                variable_path = os.path.join(root_path, file_name)
                if os.path.isfile(variable_path):
                    with open(variable_path, 'r') as file:
                        sql_server_fqdn = file.read().replace('\n', '')
                        sql_server_ip = get_ip(sql_server_fqdn)
                else:
                    sql_server_fqdn = None
                    sql_server_ip = None
            msg = {
                'my_private_ip': get_ip(socket.gethostname()),
                'my_public_ip': mypip,
                'my_dns_servers': get_dns_ips(),
                'my_default_gateway': get_default_gateway(),
                'your_address': str(request.environ.get('REMOTE_ADDR', '')),
                'x-forwarded-for': forwarded_for,
                'path_accessed': request.environ['HTTP_HOST'] + request.environ['PATH_INFO'],
                'your_platform': str(request.user_agent.platform),
                'your_browser': str(request.user_agent.browser),
                'sql_server_fqdn': str(sql_server_fqdn),
                'sql_server_ip': str(sql_server_ip)
            }          
            return jsonify(msg)
        except Exception as e:
            return jsonify(str(e))

# Flask route to provide the container's IP address
@app.route("/printenv", methods=['GET'])
def printenv():
    if request.method == 'GET':
        try:
            return jsonify(dict(os.environ))
        except Exception as e:
            return jsonify(str(e))

with warnings.catch_warnings():
    warnings.simplefilter("ignore")

app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)
