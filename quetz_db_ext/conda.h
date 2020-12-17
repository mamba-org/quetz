/*
 * Copyright (c) 2019, SUSE LLC
 *
 * This program is licensed under the BSD license, read LIBSOLV_LICENSE.txt
 * for further information
 */

int pool_evrcmp_conda_int(const char *evr1, const char *evr1e, const char *evr2, const char *evr2e, int startswith);
int solvable_conda_matchversion_single(const char* evr, const char* version, size_t versionlen);
int solvable_conda_matchversion_rec(const char* evr, const char** versionpp, char* versionend);
int solvable_conda_matchversion(const char* evr, const char* version);
