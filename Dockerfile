FROM centos:latest
MAINTAINER Jose Moreno <jose.moreno@microsoft.com>

# Install apache, PHP, and supplimentary programs. openssh-server, curl, and lynx-cur are for debugging the container.
RUN yum update -y
RUN yum install -y httpd
RUN yum install -y php curl wget

# To allow running scripts in root
RUN chmod 777 /root

# Expose apache.
EXPOSE 80

# Copy PHP page and delete index.html
COPY index.php /var/www/html/index.php
COPY styles.css /var/www/html/styles.css
COPY favicon.ico /var/www/html/favicon.ico

#RUN rm /var/www/html/index.html
#RUN if [-n $INDEXFILE]; then wget $INDEXFILE -P /var/www/html ; fi 

# By default start up apache in the foreground, override with /bin/bash for interative.
CMD /usr/sbin/httpd -D FOREGROUND
