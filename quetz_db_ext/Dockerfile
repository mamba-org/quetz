FROM postgres:13

RUN apt-get update && \
	apt-get install postgresql-server-dev-13 -y

RUN apt-get install build-essential -y
ADD . /quetz_db_ext/

RUN	cd /quetz_db_ext/ && \
	/usr/bin/cc -fPIC -c conda.c && \
	/usr/bin/cc -fPIC -I /usr/include/postgresql/13/server/ -c quetz_pg.c && \
	/usr/bin/cc -shared -o quetz_pg.so conda.o quetz_pg.o