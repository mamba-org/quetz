#include "postgres.h"
#include "utils/builtins.h"
#include "conda.h"

#ifdef PG_MODULE_MAGIC
PG_MODULE_MAGIC;
#endif

/*

Insert into postgres with
    CREATE FUNCTION version_compare(varchar, varchar)
    RETURNS boolean
    AS '/home/wolfv/Programs/quetz/quetz_db_ext/build/libquetz_pg.so'
    LANGUAGE 'c'
    \g

Delete with

	DROP FUNCTION version_compare(varchar, varchar)

*/
PG_FUNCTION_INFO_V1(version_compare);

Datum version_compare(PG_FUNCTION_ARGS)
{
    const char* lhs = text_to_cstring(PG_GETARG_VARCHAR_P(0));
    const char* rhs = text_to_cstring(PG_GETARG_VARCHAR_P(1));
    PG_RETURN_BOOL(solvable_conda_matchversion(lhs, rhs));
}

