# Docker

In these lab guides you will get familiar with the container images and instantiate them in your local machine with Docker. This guide contains the following labs:

* [Lab 1: Docker running locally](#lab1)

## Lab 1: Docker running locally<a name="lab1"></a>

Start locally a SQL Server container:

```shell
# Run database
sql_password="yoursupersecretpassword"  # Change this!
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=$sql_password" -p 1433:1433 --name sql -d mcr.microsoft.com/mssql/server:2019-GA-ubuntu-16.04
```

You can try some other interesting docker commands, like the following:

```shell
docker ps
docker stop
docker system prune
```

Now you can start the SQL API container and refer it to the SQL server (assuming here that the SQL server container got the 172.17.0.2 IP address), and start the Web container and refer it to the SQL API (assuming here the SQL container got the 172.17.0.3 IP address). If you dont know which IP address the container got, you can find it out with `docker inspect sql` (and yes, you can install `jq` on Windows with [chocolatey](https://chocolatey.org/), in case you are using docker under Windows):

```shell
# Run API container
sql_ip=$(docker inspect sql | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
docker run -d -p 8080:8080 -e "SQL_SERVER_FQDN=${sql_ip}" -e "SQL_SERVER_USERNAME=sa" -e "SQL_SERVER_PASSWORD=${sql_password}" --name api erjosito/sqlapi:0.1
```

Now you can start the web interface, and refer to the IP address of the API (which you can find out from the `docker inspect` command)

```shell
# Run Web frontend
api_ip=$(docker inspect api | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
docker run -d -p 8081:80 -e "API_URL=http://${api_api}:8080" --name web erjosito/whoami:0.1
# web_ip=$(docker inspect web | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
echo "You can point your browser to http://127.0.0.1:8081 to verify the app"
```

Please note that there are two links in the Web frontend that will only work if used with an ingress controller in Kubernetes (see the AKS sections further in this document).
