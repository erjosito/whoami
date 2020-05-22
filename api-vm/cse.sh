#!/bin/bash
apt-get update -y && apt-get install -y python3-pip python3-dev build-essential curl libssl1.0.0 libssl-dev
# See about installing ODBC drivers here: https://docs.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server?view=sql-server-2017
# Note that the driver version installed needs to match the version used in the code

# Ubuntu 18.04 (ODBC SQL driver 17.0)
cd
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/18.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update -y --fix-missing
ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev mssql-tools

wget https://raw.githubusercontent.com/erjosito/whoami/master/api/sql_api.py
wget https://raw.githubusercontent.com/erjosito/whoami/master/api/requirements.txt
pip3 install -r requirements.txt
python3 sql_api.py
