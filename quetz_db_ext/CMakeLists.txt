cmake_minimum_required(VERSION 3.2)

project(quetz-db-ext)

find_package(SQLite3)

add_library(quetz_sqlite SHARED conda.c extension.c)
target_link_libraries(quetz_sqlite SQLite::SQLite3)