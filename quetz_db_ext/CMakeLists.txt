cmake_minimum_required(VERSION 3.2)

project(quetz-db-ext)

find_package(SQLite3)
find_package(PostgreSQL)

option(POSTGRES_13_DOCKER OFF)

if (SQLite3_FOUND)
	add_library(quetz_sqlite SHARED conda.c quetz_sqlite.c)
	target_link_libraries(quetz_sqlite SQLite::SQLite3)
endif()

if (PostgreSQL_FOUND)
	add_library(quetz_pg SHARED conda.c quetz_pg.c)
	target_link_libraries(quetz_pg PostgreSQL::PostgreSQL)
endif()

if (POSTGRES_13_DOCKER)
	include_directories(/usr/include/postgresql/13/server/)
	add_library(quetz_pg SHARED conda.c quetz_pg.c)
	target_link_libraries(quetz_pg pq)
endif()