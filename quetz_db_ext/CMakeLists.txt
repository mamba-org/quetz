cmake_minimum_required(VERSION 3.2)

project(quetz-db-ext)

find_package(SQLite3)
find_package(PostgreSQL)

add_library(quetz_sqlite SHARED conda.c quetz_sqlite.c)
target_link_libraries(quetz_sqlite SQLite::SQLite3)

add_library(quetz_pg SHARED conda.c quetz_pg.c)
target_link_libraries(quetz_pg PostgreSQL::PostgreSQL)