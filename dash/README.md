# SQL application dashboard

This project uses Python dash to create a visual showing different aspects of an underlying database used by the SQL API in this project, including a real-time chart showing logs of the application access to the database.

## Using the SQL app dashboard

The dashboard connects to the database used by the [API](../api/) in this repository, and shows a sample architecture with a real-time chart reflecting the connections to the database from each IP address, like in the following example where a single private IP (`192.168.2.5`) is accessing the database:

![Dashboard screenshot](./assets/dashboard.png)

## Running container locally

The dashboard needs to connect to the same SQL database as the [API](../api/). If it is not accessing the database via a private endpoint, the database firewall rules need to be updated.

```bash
docker run -d -p 8050:8050 -e "SQL_SERVER_FQDN=yoursqlserver.database.windows.net" -e "SQL_SERVER_USERNAME=azure" -e "SQL_SERVER_PASSWORD=yoursupersecretpassword" -e "SQL_SERVER_DB=yourdbname" --name dash erjosito/sqldash:1.0
```

## Simulating load

If you have the SQL API app component running somewhere else, you can generate load just by using its `sqlsrciplog` endpoint. For example, from a linux shell:

```bash
api_url=http://api_url:8080
curl ${api_url}/api/sqlsrcipinit
while true
do
  curl ${api_url}/api/sqlsrciplog
  sleep 1
done
```

While the previous script is running, the chart in the dashboard should dynamically reflect the increase in database traffic.
