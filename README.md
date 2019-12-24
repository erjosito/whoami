# Sample containers

This repository contains two sample containers to test microservices applications in Docker and Kubernetes:

* sql api
* web

## SQL API

sql-api (available in docker hub in [here](https://hub.docker.com/repository/docker/erjosito/sqlapi)), it offers the following endpoints:

* `/healthcheck`: returns a basic JSON code
* `/sql`: returns the results of a SQL query (`SELECT @@VERSION`) against a SQL database
* `/ip`: returns IP information

Environment variables can be also injected via files in the `/secrets` directory:

* `SQL_SERVER_FQDN`: FQDN of the SQL server
* `SQL_SERVER_USERNAME`: username for the SQL server
* `SQL_SERVER_PASSWORD`: password for the SQL server

## Web

Simple PHP web page that can access the previous API.

Environment variables:

* `API_URL`: URL where the SQL API can be found

## Usage example in Docker

Start locally a SQL Server container:

```
password="yoursupersecretpassword"
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=$password" -p 1433:1433 --name sql1 -d mcr.microsoft.com/mssql/server:2019-GA-ubuntu-16.04
```

Now you can start the SQL API container and refer it to the SQL server (assuming here that the SQL server container got the 172.17.0.2 IP address), and start the Web container and refer it to the SQL API (assuming here the SQL container got the 172.17.0.3 IP address). If you dont know which IP address the container got, you can find it out with `docker inspect sql1`:

```
docker run -d -p 8080:8080 -e SQL_SERVER_FQDN=172.17.0.2 -e SQL_SERVER_USERNAME=sa -e SQL_SERVER_PASSWORD=$password --name sqlapi sqlapi:0.1
docker run -d -p 8081:80 -e API_URL=http://172.17.0.3:8080 --name web erjosito/whoami:0.1
```

