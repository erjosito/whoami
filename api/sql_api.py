import pyodbc
import os
import socket, struct
import sys
import time
import warnings
import requests
import pymysql

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

def get_sqlsrcip(cx):
    cursor = cx.cursor()
    cursor.execute('SELECT CONNECTIONPROPERTY("client_net_address")')
    return cursor.fetchall()

def get_sqlquery(cx, query):
    cursor = cx.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    app.logger.info('Query "' + query + '" has returned ' + str(len(rows)) + ' rows')
    app.logger.info('Variable type for first row: ' + str(type(rows[0])))
    if len(rows) > 0:
        return rows[0][0]
    else:
        return None

def get_variable_value(variable_name):
    variable_value = os.environ.get(variable_name)
    basis_path='/secrets'
    variable_path = os.path.join(basis_path, variable_name)
    if variable_value == None and os.path.isfile(variable_path):
        with open(variable_path, 'r') as file:
            variable_value = file.read().replace('\n', '')
    return variable_value

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

# To add to SQL cx to handle output
def handle_sql_variant_as_string(value):
    # return value.decode('utf-16le')
    return value.decode('utf-8')


def send_sql_query(sql_server_fqdn = None, sql_server_db = None, sql_query = 'SELECT @@VERSION'):
    # Get variables
    sql_server_username = get_variable_value('SQL_SERVER_USERNAME')
    sql_server_password = get_variable_value('SQL_SERVER_PASSWORD')
    # Only set the sql_server_fqdn and db variable if not supplied as argument
    if sql_server_fqdn == None:
        sql_server_fqdn = get_variable_value('SQL_SERVER_FQDN')
    if sql_server_db == None:
        sql_server_db = get_variable_value('SQL_SERVER_DB')
    # Check we have the right variables (note that SQL_SERVER_DB is optional)
    if sql_server_username == None or sql_server_password == None or sql_server_fqdn == None:
        print('DEBUG - Required environment variables not present')
        return 'Required environment variables not present'
    # Build connection string
    cx_string=''
    drivers = pyodbc.drivers()
    # print('Available ODBC drivers:', drivers)   # DEBUG
    if len(drivers) == 0:
        app.logger.error('Oh oh, it looks like you have no ODBC drivers installed :(')
        return "No ODBC drivers installed"
    else:
        # Take first driver, for our basic stuff any should do
        driver = drivers[0]
        if sql_server_db == None:
            app.logger.info("Building connection string with no Database")
            cx_string = "Driver={{{0}}};Server=tcp:{1},1433;Uid={2};Pwd={3};Encrypt=yes;TrustServerCertificate=yes;Connection Timeut=30;".format(driver, sql_server_fqdn, sql_server_username, sql_server_password)
        else:
            app.logger.info("Building connection string with Database")
            cx_string = "Driver={{{0}}};Server=tcp:{1},1433;Database={2};Uid={3};Pwd={4};Encrypt=yes;TrustServerCertificate=yes;Connection Timeut=30;".format(driver, sql_server_fqdn, sql_server_db, sql_server_username, sql_server_password)
        app.logger.info('connection string: ' + cx_string)
    # Connect to DB
    app.logger.info('Connecting to database server ' + sql_server_fqdn + ' - ' + get_ip(sql_server_fqdn) + '...')
    try:
        cx = init_odbc(cx_string)
        cx.add_output_converter(-150, handle_sql_variant_as_string)

    except Exception as e:
        if is_valid_ipv4_address(sql_server_fqdn):
            error_msg = 'SQL Server FQDN should not be an IP address when targeting Azure SQL Databse, maybe this is a problem?'
        else:
            error_msg = 'Connection to server ' + sql_server_fqdn + ' failed, you might have to update the firewall rules?'
        app.logger.info(error_msg)
        app.logger.error(e)
        return error_msg

    # Send SQL query
    app.logger.info('Sending SQL query ' + sql_query + '...')
    try:
        # sql_output = get_sqlversion(cx)
        # sql_output = get_sqlsrcip(cx)
        sql_output = get_sqlquery(cx, sql_query)
        return str(sql_output)
    except Exception as e:
        # app.logger.error('Error sending query to the database')
        app.logger.error(e)
        return None

# Get IP for a DNS name
def get_ip(d):
    try:
        return socket.gethostbyname(d)
    except Exception:
        return False

app = Flask(__name__)


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
@app.route("/api/healthcheck", methods=['GET'])
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
@app.route("/api/sql", methods=['GET'])
def sql():
    if request.method == 'GET':
        try:
            sql_server_fqdn = request.args.get('SQL_SERVER_FQDN')
            sql_server_db = request.args.get('SQL_SERVER_DB')
            sql_output = send_sql_query(sql_server_fqdn=sql_server_fqdn, sql_server_db=sql_server_db)
            msg = {
            'sql_output': sql_output
            }          
            return jsonify(msg)
        except Exception as e:
          return jsonify(str(e))

# Flask route to ping the SQL server with a basic SQL query
@app.route("/api/sqlversion", methods=['GET'])
def sqlversion():
    if request.method == 'GET':
        sql_query = 'SELECT @@VERSION'
        try:
            sql_server_fqdn = request.args.get('SQL_SERVER_FQDN')
            sql_server_db = request.args.get('SQL_SERVER_DB')
            sql_output = send_sql_query(sql_server_fqdn=sql_server_fqdn, sql_server_db=sql_server_db, sql_query=sql_query)
            msg = {
            'sql_output': sql_output
            }          
            return jsonify(msg)
        except Exception as e:
          return jsonify(str(e))

@app.route("/api/sqlsrcip", methods=['GET'])
def sqlsrcip():
    if request.method == 'GET':
        sql_query = 'SELECT CONNECTIONPROPERTY(\'client_net_address\')'
        try:
            sql_server_fqdn = request.args.get('SQL_SERVER_FQDN')
            sql_server_db = request.args.get('SQL_SERVER_DB')
            sql_output = send_sql_query(sql_server_fqdn=sql_server_fqdn, sql_server_db=sql_server_db, sql_query=sql_query)
            msg = {
            'sql_output': sql_output
            }          
            return jsonify(msg)
        except Exception as e:
          return jsonify(str(e))


# Flask route to provide the container's IP address
@app.route("/api/dns", methods=['GET'])
def dns():
    try:
        fqdn = request.args.get('fqdn')
        ip = get_ip(fqdn)
        msg = {
                'fqdn': fqdn,
                'ip': ip
        }          
        return jsonify(msg)
    except Exception as e:
        return jsonify(str(e))
        

# Flask route to provide the container's IP address
@app.route("/api/ip", methods=['GET'])
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
            sql_server_fqdn = get_variable_value('SQL_SERVER_FQDN')
            sql_server_ip = get_ip(sql_server_fqdn)
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

# Flask route to provide the container's environment variables
@app.route("/api/printenv", methods=['GET'])
def printenv():
    if request.method == 'GET':
        try:
            return jsonify(dict(os.environ))
        except Exception as e:
            return jsonify(str(e))

# Flask route to run a HTTP GET to a target URL and return the answer
@app.route("/api/curl", methods=['GET'])
def curl():
    if request.method == 'GET':
        try:
            url = request.args.get('url')
            if url == None:
                url='http://jsonip.com'
            http_answer = requests.get(url).text
            msg = {
                'url': url,
                'method': 'GET',
                'answer': http_answer
            }          
            return jsonify(msg)
        except Exception as e:
            return jsonify(str(e))

# Flask route to connect to MySQL
@app.route("/api/mysql", methods=['GET'])
def mysql():
    if request.method == 'GET':
        sql_query = 'SELECT @@VERSION'
        try:
            # Get variables
            mysql_fqdn = request.args.get('SQL_SERVER_FQDN') or get_variable_value('SQL_SERVER_FQDN')
            mysql_user = request.args.get('SQL_SERVER_USERNAME') or get_variable_value('SQL_SERVER)USERNAME')
            mysql_pswd = request.args.get('SQL_SERVER_PASSWORD') or get_variable_value('SQL_SERVER_PASSWORD')
            mysql_db = request.args.get('SQL_SERVER_DB') or get_variable_value('SQL_SERVER_DB')
            app.logger.info('Values to connect to MySQL:')
            app.logger.info(mysql_fqdn)
            app.logger.info(mysql_db)
            app.logger.info(mysql_user)
            app.logger.info(mysql_pswd)
            # The user must be in the format user@server
            mysql_name = mysql_fqdn.split('.')[0]
            if mysql_name:
                mysql_user = mysql_user + '@' + mysql_name
            else:
                return "MySql server name could not be retrieved out of FQDN"
            # Different connection strings if using a database or not
            if mysql_db == None:
                app.logger.info('Connecting to mysql server ' + str(mysql_fqdn) + ', username ' + str(mysql_user) + ', password ' + str(mysql_pswd))
                db = pymysql.connect(mysql_fqdn, mysql_user, mysql_pswd)
            else:
                app.logger.info('Connecting to mysql server ' + str(mysql_fqdn) + ', database ' + str(mysql_db) + ', username ' + str(mysql_user) + ', password ' + str(mysql_pswd))
                db = pymysql.connect(mysql_fqdn, mysql_user, mysql_pswd, mysql_db)
            # Send query and extract data
            cursor = db.cursor()
            cursor.execute("SELECT VERSION()")
            data = cursor.fetchone()
            db.close()
            msg = {
                'sql_output': str(data)
            }          
            return jsonify(msg)
        except Exception as e:
            return jsonify(str(e))

# Gets the web port out of an environment variable, or defaults to 8080
def get_web_port():
    web_port=os.environ.get('PORT')
    if web_port==None or not web_port.isnumeric():
        print("Using default port 8080")
        web_port=8080
    else:
        print("Port supplied as environment variable:", web_port)
    return web_port

# Ignore warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")

# Set web port
web_port=get_web_port()

app.run(host='0.0.0.0', port=web_port, debug=True, use_reloader=False)
