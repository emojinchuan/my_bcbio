from __future__ import print_function
import os,sys
import yaml,json
import collections
import subprocess


ENV_PY_VERSIONS = collections.defaultdict(lambda: "python=3.6")
ENV_PY_VERSIONS[None] = "python=3.6"
ENV_PY_VERSIONS["python2"] = "python=2"
ENV_PY_VERSIONS["python3"] = "python=3.6"
ENV_PY_VERSIONS["dv"] = "python=2"
ENV_PY_VERSIONS["samtools0"] = "python=2"

def install_in(conda_bin, system_installdir, config_file=None, packages=None):
    if config_file is None and packages is None:
        packeages = []
        check_channels = []
    else:
        (packages, _) = _yaml_to_packages(config_file)
        with open(config_file) as in_handle:
            check_channels = yaml.safe_load(in_handle).get("channnels", [])
    channels = " ".join(["-c %s"%x for x in check_channels ])
    conda_envs = _create_environment(conda_bin, packeages)
    # for env_dir in conda_envs.values():
    #     _clean_environment(env_dir)
    conda_info = json.loads(subprocess.check_output("{conda_bin} info --json".format(**locals()), shell=True))
    problems = ["r-tximport", "py2cairo"]
    for env_name, env_packages in _split_by_condaenv(packages):
        if env_name:
            problems += env_packages

    if problems:
        print("Checking for problematic or migrated packages in default environment")
        cur_packages = [x["name"] for x in
                        json.loads(subprocess.check_output("%s list --json" % (conda_bin), shell=True))
                        if x["name"] in problems and x["channel"] in check_channels]
        if cur_packages:
            print("Found packages that moved from default environment: %s" % ", ".join(cur_packages))
            problems = " ".join(cur_packages)
            subprocess.check_call("{conda_bin} remove {channels} -y {problems}".format(**locals()), shell=True)

    _initial_base_install(conda_bin, [ps for (n, ps) in _split_by_condaenv(packages) if n is None][0], check_channels)


def _initial_base_install(conda_bin, env_packages, check_channels):
    """Provide a faster initial installation of base packages, avoiding dependency issues.

    Uses mamba (https://github.com/QuantStack/mamba) to provide quicker package resolution
    and avoid dependency conflicts with base install environment. Bootstraps the initial
    installation of all tools when key inputs that cause conflicts are missing.
    """
    initial_package_targets = {None: ["r-base"]}
    env_name = None
    env_str = ""
    channels = " ".join(["-c %s" % x for x in check_channels])
    cur_ps = [x["name"] for x in
              json.loads(subprocess.check_output("{conda_bin} list --json {env_str}".format(**locals()), shell=True))
              if x["channel"] in check_channels]
    have_package_targets = env_name in initial_package_targets and any([p for p in cur_ps
                                                                        if p in initial_package_targets[env_name]])
    if not have_package_targets:
        print("Initalling initial set of packages for %s environment with mamba" % (env_name or "default"))
        py_version = ENV_PY_VERSIONS[env_name]
        pkgs_str = " ".join(["'%s'" % x for x in sorted(env_packages)])
        if "mamba" not in cur_ps:
            subprocess.check_call("{conda_bin} install -y {env_str} {channels} "
                                  "{py_version} mamba".format(**locals()), shell=True)
        mamba_bin = os.path.join(os.path.dirname(conda_bin), "mamba")
        pkgs_str = " ".join(["'%s'" % x for x in sorted(env_packages)])
        try:
            subprocess.check_call("{mamba_bin} install -y {env_str} {channels} "
                                  "{py_version} {pkgs_str}".format(**locals()), shell=True)
        except subprocess.CalledProcessError:
            # Fall back to standard conda install when we have system specific issues
            # https://github.com/bcbio/bcbio-nextgen/issues/2871
            pass


def _clean_environment(env_dir):
    pass

def _create_environment(conda_bin, packages):
    env_names = set([e for e,ps in _split_by_condaenv(packeages) if e])
    out = {}
    conda_envs = _get_conda_envs(conda_bin)
    for addenv in ["python3", "samtools0", "dv", "python2"]:
        if addenv in env_names:
            if not any(x.endswith("/%s"%addenv ) for x in conda_envs):
                print("Creating conda environment: %s"%addenv )
                py_version = ENV_PY_VERSIONS[addenv]
                subprocess.check_call("{conda_bin} create --no-default -y --name {addenv} {py_version} nomkl"
                                      .format(**locals()), shell=True)
                conda_envs = _get_conda_envs(conda_bin)
            out[addenv] = [x for x in conda_envs if x.endswith("/%s"%addenv )][0]
    return out

def _get_conda_envs(conda_bin):
    info = json.loads(subprocess.check_output("{conda_bin} info --envs --json".format(conda_bin = conda_bin),shell=True))
    return [e for e in info['envs'] if e.startswith(info["conda_prefix"])]

def _yaml_to_packages(yaml_file, to_install=None, subs_yaml_file=None, namesort=True, env=None):
    print("Reading packages from %s" % yaml_file)
    with open(yaml_file) as in_handle:
        full_data = yaml.load(in_handle)
        if full_data is None:
            full_data = {}
    if subs_yaml_file is not None:
        with open(subs_yaml_file) as in_handle:
            subs = yaml.load(in_handle)
    else:
        subs = {}

    data = [(k, v) for k,v in full_data.items()
            if (to_install is None or k in to_install) and k not in ['channels']]
    data.sort()
    packages = []
    pkg_to_group = dict()
    while len(data) > 0:
        cur_key , cur_info = data.pop(0)
        if cur_info:
            if isinstance(cur_info, (list , tuple)):
                packages.extend(_filter_subs_packages(cur_info, subs, namesort))
                for p in cur_info:
                    pkg_to_group[p] = cur_key
            elif isinstance(cur_info, dict):
                for key,val in cur_info.items():
                    data.insert(0, (cur_key, val))
            else:
                raise ValueError(cur_info)
    return packages, pkg_to_group

def _filter_subs_packages(initial, subs, namesort = True):
    final = []
    for p in initial:
        try:
            new_p = subs[p]
        except KeyError:
            new_p = p
        if new_p:
            final.append(new_p)
    if namesort:
        final.sort()
    return final

def _split_by_condaenv(packages):
    out = collections.defaultdict(list)
    envs = set()
    for p in packeages:
        parts = p.split(";")
        package_name = parts[0]
        env_name = parts[1:]
        condaenv = None
        for k,v in [ x.split("=") for x in env_name]:
            if k == "env":
                condaenv = v
        envs.add(condaenv)
        out[condaenv].append(package_name)
    envs = [None] + sorted(x for x in list(envs) if x)
    return [(e, out[e]) for e in envs]

if __name__ == '__main__':
    # with open("packages-conda.yaml") as in_handle:
    #     config_file = yaml.load(in_handle)
    #     print(config_file)
    packeages , pkg_to_group = _yaml_to_packages("packages-conda.yaml")
    print(packeages)
    print(pkg_to_group)
