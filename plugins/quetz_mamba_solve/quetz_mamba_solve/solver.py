import tempfile

import libmambapy
from conda.base.context import context
from conda.common.serialize import json_dump
from conda.core.index import _supplement_index_with_system
from conda_build.conda_interface import pkgs_dirs
from mamba.utils import load_channels


def get_virtual_packages():
    result = {"packages": {}}

    # add virtual packages as installed packages
    # they are packages installed on the system that conda can do nothing
    # about (e.g. glibc)
    # if another version is needed, installation just fails
    # they don't exist anywhere (they start with __)
    installed = dict()
    _supplement_index_with_system(installed)
    installed = list(installed)

    for prec in installed:
        json_rec = prec.dist_fields_dump()
        json_rec["depends"] = prec.depends
        json_rec["build"] = prec.build
        result["packages"][prec.fn] = json_rec

    installed_json_f = tempfile.NamedTemporaryFile("w", delete=False)
    installed_json_f.write(json_dump(result))
    installed_json_f.flush()
    return installed_json_f


class MambaSolver:
    def __init__(self, channels, platform, output_folder=None):
        self.channels = channels
        self.platform = platform
        self.output_folder = output_folder or "local"
        self.pool = libmambapy.Pool()
        self.repos = []
        self.index = load_channels(
            self.pool, self.channels, self.repos, platform=platform
        )

        # TODO this is wrong...
        if platform == context.subdir:
            installed_json_f = get_virtual_packages()
            repo = libmambapy.Repo(self.pool, "installed", installed_json_f.name, "")
            repo.set_installed()
            self.repos.append(repo)

    def solve(self, specs, pkg_cache_path=pkgs_dirs):
        """Solve given a set of specs.
        Parameters
        ----------
        specs : list of str
            A list of package specs. You can use `conda.models.match_spec.MatchSpec`
            to get them to the right form by calling
            `MatchSpec(mypec).conda_build_form()`
        Returns
        -------
        solvable : bool
            True if the set of specs has a solution, False otherwise.
        """
        solver_options = [(libmambapy.SOLVER_FLAG_ALLOW_DOWNGRADE, 1)]
        api_solver = libmambapy.Solver(self.pool, solver_options)
        _specs = specs

        api_solver.add_jobs(_specs, libmambapy.SOLVER_INSTALL)
        success = api_solver.solve()

        if not success:
            error_string = "Mamba failed to solve:\n"
            for s in _specs:
                error_string += f" - {s}\n"
            error_string += "\nwith channels:\n"
            for c in self.channels:
                error_string += f" - {c}\n"
            pstring = api_solver.problems_to_str()
            pstring = "\n".join(["   " + el for el in pstring.split("\n")])
            error_string += f"\nThe reported errors are:\n{pstring}"
            print(error_string)
            exit(1)

        package_cache = libmambapy.MultiPackageCache(pkg_cache_path)
        t = libmambapy.Transaction(api_solver, package_cache)

        return t
