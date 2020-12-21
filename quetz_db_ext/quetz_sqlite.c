#include "sqlite3ext.h"
SQLITE_EXTENSION_INIT1
#include <assert.h>
#include <string.h>

#include "conda.h"

static void version_match_func(
    sqlite3_context* context,
    int argc,
    sqlite3_value** argv)
{
    const unsigned char* zIn1;
    const unsigned char* zIn2;
    assert(argc == 2);
    if (sqlite3_value_type(argv[0]) == SQLITE_NULL || sqlite3_value_type(argv[1]) == SQLITE_NULL)
        return;

    zIn1 = (const unsigned char*)sqlite3_value_text(argv[0]);
    zIn2 = (const unsigned char*)sqlite3_value_text(argv[1]);
    int res = solvable_conda_matchversion(zIn1, zIn2);
    sqlite3_result_int(context, res);
}

#ifdef _WIN32
__declspec(dllexport)
#endif
    int sqlite3_quetzsqlite_init(
        sqlite3* db,
        char** pzErrMsg,
        const sqlite3_api_routines* pApi)
{
    int rc = SQLITE_OK;
    SQLITE_EXTENSION_INIT2(pApi);
    (void)pzErrMsg; /* Unused parameter */
    rc = sqlite3_create_function(db, "version_match", 2,
        SQLITE_UTF8 | SQLITE_INNOCUOUS | SQLITE_DETERMINISTIC,
        0, version_match_func, 0, 0);
    return rc;
}