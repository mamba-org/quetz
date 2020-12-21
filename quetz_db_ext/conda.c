/*
 * Copyright (c) 2019, SUSE LLC
 *
 * This program is licensed under the BSD license, read LIBSOLV_LICENSE.txt
 * for further information
 */

/*
 * conda.c
 *
 * evr comparison and package matching for conda
 *
 * THIS IS A MODIFIED VERSION FOR USE IN quetz_db_ext
 */

#include <regex.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>

#define REL_GT 1
#define REL_EQ 2
#define REL_LT 4

#define REL_AND 16
#define REL_OR 17
#define REL_WITH 18
#define REL_NAMESPACE 19
#define REL_ARCH 20
#define REL_FILECONFLICT 21
#define REL_COND 22 /* OR_NOT */
#define REL_COMPAT 23
#define REL_KIND 24 /* for filters only */
#define REL_MULTIARCH 25 /* debian multiarch annotation */
#define REL_ELSE 26 /* only as evr part of REL_COND/REL_UNLESS */
#define REL_ERROR 27 /* parse errors and the like */
#define REL_WITHOUT 28
#define REL_UNLESS 29 /* AND_NOT */
#define REL_CONDA 30

#ifdef _WIN32
#include "strfncs.h"
#endif

static const char*
endseg(const char* seg, const char* end)
{
    for (; seg < end; seg++)
        if (*seg == '.' || *seg == '-' || *seg == '_')
            break;
    return seg;
}

static const char*
endpart(const char* seg, const char* end)
{
    if (seg == end)
        return seg;
    if (*seg >= '0' && *seg <= '9') {
        for (seg++; seg < end; seg++)
            if (!(*seg >= '0' && *seg <= '9'))
                break;
    } else if (*seg == '*') {
        for (seg++; seg < end; seg++)
            if (*seg != '*')
                break;
    } else {
        for (seg++; seg < end; seg++)
            if ((*seg >= '0' && *seg <= '9') || *seg == '*')
                break;
    }
    return seg;
}

/* C implementation of the version comparison code in conda/models/version.py */
/* startswith == 1 : check if s1 starts with s2 */
static int
solv_vercmp_conda(const char* s1, const char* q1, const char* s2, const char* q2, int startswith)
{
    const char *s1p, *s2p;
    const char *s1e, *s2e;
    int r, isfirst;
    const char* q2end = 0;

    if (startswith) {
        for (q2end = q2; q2end > s2; q2end--)
            if (q2end[-1] != '.' && q2end[-1] != '-' && q2end[-1] != '_')
                break;
    }
    for (;;) {
        while (s1 < q1 && (*s1 == '.' || *s1 == '-' || *s1 == '_'))
            s1++;
        while (s2 < q2 && (*s2 == '.' || *s2 == '-' || *s2 == '_'))
            s2++;
        if (s1 == q1 && s2 == q2)
            return 0;
        if (startswith && s2 == q2)
            return 0;
        /* find end of component */
        s1e = endseg(s1, q1);
        s2e = endseg(s2, q2);

        for (isfirst = 1;; isfirst = 0) {
            if (s1 == s1e && s2 == s2e)
                break;
            if (s2 == q2end)
                return 0;
            s1p = endpart(s1, s1e);
            s2p = endpart(s2, s2e);
            /* prepend 0 if not numeric */
            if (isfirst) {
                if (s1p != s1 && !(*s1 >= '0' && *s1 <= '9'))
                    s1p = s1;
                if (s2p != s2 && !(*s2 >= '0' && *s2 <= '9'))
                    s2p = s2;
            }
            /* special case "post" */
            if (s1p - s1 == 4 && !strncasecmp(s1, "post", 4)) {
                if (s2p - s2 == 4 && !strncasecmp(s2, "post", 4)) {
                    s1 = s1p;
                    s2 = s2p;
                    continue;
                }
                return 1;
            }
            if (s2p - s2 == 4 && !strncasecmp(s2, "post", 4))
                return -1;

            if (isfirst || ((s1 == s1p || (*s1 >= '0' && *s1 <= '9')) && (s2 == s2p || (*s2 >= '0' && *s2 <= '9')))) {
                /* compare numbers */
                while (s1 < s1p && *s1 == '0')
                    s1++;
                while (s2 < s2p && *s2 == '0')
                    s2++;
                if (s1p - s1 < s2p - s2)
                    return -1;
                if (s1p - s1 > s2p - s2)
                    return 1;
                r = s1p - s1 ? strncmp(s1, s2, s1p - s1) : 0;
                if (r)
                    return r;
            } else if (s1 == s1p || (*s1 >= '0' && *s1 <= '9'))
                return 1;
            else if (s2 == s2p || (*s2 >= '0' && *s2 <= '9'))
                return -1;
            else {
                /* special case "dev" */
                if (*s2 != '*' && s1p - s1 == 3 && !strncasecmp(s1, "dev", 3)) {
                    if (s2p - s2 == 3 && !strncasecmp(s2, "dev", 3)) {
                        s1 = s1p;
                        s2 = s2p;
                        continue;
                    }
                    return -1;
                }
                if (*s1 != '*' && s2p - s2 == 3 && !strncasecmp(s2, "dev", 3))
                    return 1;
                /* compare strings */
                r = s2p - s2 > s1p - s1 ? s1p - s1 : s2p - s2;
                if (r)
                    r = strncasecmp(s1, s2, r);
                if (r)
                    return r;
                if (s1p - s1 < s2p - s2)
                    return -1;
                if (s1p - s1 > s2p - s2)
                    return 1;
            }
            s1 = s1p;
            s2 = s2p;
        }
    }
}

int
pool_evrcmp_conda_int(const char* evr1, const char* evr1e, const char* evr2, const char* evr2e, int startswith)
{
    static char zero[2] = { '0', 0 };
    const char *s1, *s2;
    const char *r1, *r2;
    int r;

    /* split and compare epoch */
    for (s1 = evr1; s1 < evr1e && *s1 >= '0' && *s1 <= '9'; s1++)
        ;
    for (s2 = evr2; s2 < evr2e && *s2 >= '0' && *s2 <= '9'; s2++)
        ;
    if (s1 == evr1 || s1 == evr1e || *s1 != '!')
        s1 = 0;
    if (s2 == evr1 || s2 == evr2e || *s2 != '!')
        s2 = 0;
    if (s1 || s2) {
        r = solv_vercmp_conda(s1 ? evr1 : zero, s1 ? s1 : zero + 1,
            s2 ? evr2 : zero, s2 ? s2 : zero + 1, 0);
        if (r)
            return r;
        if (s1)
            evr1 = s1 + 1;
        if (s2)
            evr2 = s2 + 1;
    }
    /* split into version/localversion */
    for (s1 = evr1, r1 = 0; s1 < evr1e; s1++)
        if (*s1 == '+')
            r1 = s1;
    for (s2 = evr2, r2 = 0; s2 < evr2e; s2++)
        if (*s2 == '+')
            r2 = s2;
    r = solv_vercmp_conda(evr1, r1 ? r1 : s1, evr2, r2 ? r2 : s2, r2 ? 0 : startswith);
    if (r)
        return r;
    if ((!r2 && startswith) || (!r1 && !r2))
        return 0;
    if (!r1 && r2)
        return -1;
    if (r1 && !r2)
        return 1;
    return solv_vercmp_conda(r1 + 1, s1, r2 + 1, s2, startswith);
}

static int
regexmatch(const char* evr, const char* version, size_t versionlen, int icase)
{
    regex_t reg;
    char* buf = malloc(versionlen + 1);
    int r;

    memcpy(buf, version, versionlen);
    buf[versionlen] = 0;
    if (regcomp(&reg, buf, REG_EXTENDED | REG_NOSUB | (icase ? REG_ICASE : 0))) {
        free(buf);
        return 0;
    }
    r = regexec(&reg, evr, 0, NULL, 0);
    regfree(&reg);
    free(buf);
    return r == 0;
}

static int
globmatch(const char* evr, const char* version, size_t versionlen, int icase)
{
    regex_t reg;
    char* buf = malloc(2 * versionlen + 3);
    size_t i, j;
    int r;

    buf[0] = '^';
    j = 1;
    for (i = 0, j = 1; i < versionlen; i++) {
        if (version[i] == '.' || version[i] == '+' || version[i] == '*')
            buf[j++] = version[i] == '*' ? '.' : '\\';
        buf[j++] = version[i];
    }
    buf[j++] = '$';
    buf[j] = 0;
    if (regcomp(&reg, buf, REG_EXTENDED | REG_NOSUB | (icase ? REG_ICASE : 0))) {
        free(buf);
        return 0;
    }
    r = regexec(&reg, evr, 0, NULL, 0);
    regfree(&reg);
    free(buf);
    return r == 0;
}

int
solvable_conda_matchversion_single(const char* evr, const char* version, size_t versionlen)
{
    size_t i;
    int r;

    if (versionlen == 0 || (versionlen == 1 && *version == '*'))
        return 1; /* matches every version */
    if (versionlen >= 2 && version[0] == '^' && version[versionlen - 1] == '$')
        return regexmatch(evr, version, versionlen, 0);
    if (version[0] == '=' || version[0] == '<' || version[0] == '>' || version[0] == '!' || version[0] == '~') {
        int flags = 0;
        int oplen;
        if (version[0] == '=')
            flags = version[1] == '=' ? REL_EQ : 8;
        else if (version[0] == '!' || version[0] == '~') {
            if (version[1] != '=')
                return 0;
            flags = version[0] == '!' ? REL_LT | REL_GT : 9;
        } else if (version[0] == '<' || version[0] == '>') {
            flags = version[0] == '<' ? REL_LT : REL_GT;
            if (version[1] == '=')
                flags |= REL_EQ;
        } else
            return 0;
        oplen = flags == 8 || flags == REL_LT || flags == REL_GT ? 1 : 2;
        if (versionlen < oplen + 1)
            return 0;
        version += oplen;
        versionlen -= oplen;
        if (version[0] == '=' || version[0] == '<' || version[0] == '>' || version[0] == '!' || version[0] == '~')
            return 0; /* bad chars after op */
        if (versionlen >= 2 && version[versionlen - 2] == '.' && version[versionlen - 1] == '*') {
            if (flags == 8 || flags == (REL_GT | REL_EQ))
                versionlen -= 2;
            else if (flags == (REL_LT | REL_GT)) {
                versionlen -= 2;
                flags = 10;
            } else
                return 0;
        }
        if (flags < 8) {
            /* we now have an op and a version */
            r = pool_evrcmp_conda_int(evr, evr + strlen(evr), version, version + versionlen, 0);
            if (r < 0)
                return (flags & REL_LT) ? 1 : 0;
            if (r == 0)
                return (flags & REL_EQ) ? 1 : 0;
            if (r > 0)
                return (flags & REL_GT) ? 1 : 0;
            return 0;
        }
        if (flags == 8 || flags == 10) /* startswith, not-startswith */
        {
            r = pool_evrcmp_conda_int(evr, evr + strlen(evr), version, version + versionlen, 1);
            return flags == 8 ? r == 0 : r != 0;
        } else if (flags == 9) /* compatible release op */
        {
            r = pool_evrcmp_conda_int(evr, evr + strlen(evr), version, version + versionlen, 0);
            if (r < 0)
                return 0;
            /* split off last component */
            while (versionlen > 0 && version[versionlen - 1] != '.')
                versionlen--;
            if (versionlen < 2)
                return 0;
            versionlen--;
            r = pool_evrcmp_conda_int(evr, evr + strlen(evr), version, version + versionlen, 1);
            return r == 0 ? 1 : 0;
        }
        return 0;
    }

    /* do we have a '*' in the version */
    for (i = 0; i < versionlen; i++)
        if (version[i] == '*') {
            for (i++; i < versionlen; i++)
                if (version[i] != '*')
                    break;
            if (i < versionlen)
                return globmatch(evr, version, versionlen, 1);
        }

    if (versionlen > 1 && version[versionlen - 1] == '*') {
        /* startswith */
        while (versionlen > 0 && version[versionlen - 1] == '*')
            versionlen--;
        while (versionlen > 0 && version[versionlen - 1] == '.')
            versionlen--;
        r = pool_evrcmp_conda_int(evr, evr + strlen(evr), version, version + versionlen, 1);
        return r == 0 ? 1 : 0;
    }
    /* do we have a '@' in the version? */
    for (i = 0; i < versionlen; i++)
        if (version[i] == '@')
            return strncmp(evr, version, versionlen) == 0 && evr[versionlen] == 0;
    r = pool_evrcmp_conda_int(evr, evr + strlen(evr), version, version + versionlen, 0);
    return r == 0 ? 1 : 0;
}

int
solvable_conda_matchversion_rec(const char* evr, const char** versionp, const char* versionend)
{
    const char* version = *versionp;
    int v, vor = 0, vand = -1; /* -1: doing OR, 0,1: doing AND */

    if (version == versionend)
        return -1;
    for (;;) {
        if (*version == '(') {
            version++;
            v = solvable_conda_matchversion_rec(evr, &version, versionend);
            if (v == -1 || version == versionend || *version != ')')
                return -1;
            version++;
        } else if (*version == ')' || *version == '|' || *version == ',')
            return -1;
        else {
            const char* vstart = version;
            while (version < versionend && *version != '(' && *version != ')' && *version != '|' && *version != ',')
                version++;
            if (vand >= 0 ? !vand : vor)
                v = 0; /* no need to call expensive matchversion if the result does not matter */
            else
                v = solvable_conda_matchversion_single(evr, vstart, version - vstart) ? 1 : 0;
        }
        if (version == versionend || *version == ')') {
            *versionp = version;
            return vor | (vand >= 0 ? (vand & v) : v);
        }
        if (*version == ',')
            vand = vand >= 0 ? (vand & v) : v;
        else if (*version == '|') {
            vor |= vand >= 0 ? (vand & v) : v;
            vand = -1;
        } else
            return -1;
        version++;
    }
}

// static int
// solvable_conda_matchbuild(const char *s, const char *build, const char *buildend)
// {
//   const char *bp;
//   const char *flavor = solvable_lookup_str(s, SOLVABLE_BUILDFLAVOR);

//   if (!flavor)
//     flavor = "";
//   if (build == buildend)
//     return *flavor ? 0 : 1;
//   if (build + 1 == buildend && *build == '*')
//     return 1;
//   if (*build == '^' && buildend[-1] == '$')
//     return regexmatch(flavor, build, buildend - build, 0);
//   for (bp = build; bp < buildend; bp++)
//     if (*bp == '*')
//       return globmatch(flavor, build, buildend - build, 0);
//   return strncmp(flavor, build, buildend - build) == 0 && flavor[buildend - build] == 0 ? 1 : 0;
// }

/* return true if solvable s matches the version */
/* see conda/models/match_spec.py */
int solvable_conda_matchversion(const char* evr, const char* version)
{
    const char *build, *versionend;
    int r;
    /* split off build */
    // if ((build = strchr(version, ' ')) != 0) {
    //     versionend = build++;
    //     while (*build == ' ')
    //         build++;
    // } else
    //     versionend = version + strlen(version);

    versionend = version + strlen(version);
    r = solvable_conda_matchversion_rec(evr, &version, versionend);
    if (r != 1 || version != versionend)
        return 0;
    // if (build && !solvable_conda_matchbuild(evr, build, build + strlen(build)))
    //     return 0;
    return r;
}