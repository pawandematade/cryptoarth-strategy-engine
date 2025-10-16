FROM python:3.11

WORKDIR /code
#RUN apt-get update && apt-get install python3-dev build-essential -y
# Allows docker to cache installed dependencies between builds
COPY requirements.txt /code/requirements.txt

# COPY certificates/tradearth/fullchain.pem /etc/ssl/certs/tradearth.pem
# COPY certificates/tradearth/privkey.pem /etc/ssl/certs/tradearth.key

#RUN pip3 install --upgrade pip
RUN pip3 install \
    boto3==1.33.2 uvicorn[standard]==0.20.0 
    # "git+https://github.com/Kotak-Neo/kotak-neo-api.git#egg=neo_api_client"
RUN pip3 install -r requirements.txt
#RUN apt-get install python3-dev default-libmysqlclient-dev build-essential pkg-config && export MYSQLCLIENT_CFLAGS=`pkg-config mysqlclient --cflags` &&  export MYSQLCLIENT_LDFLAGS=`pkg-config mysqlclient --libs`
# Mounts the application code to the image
COPY . /code
#RUN python manage.py migrate
RUN chmod +x ./entrypoint.sh
CMD ["./entrypoint.sh"]
#CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]


