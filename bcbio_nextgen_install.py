#coding:utf8
from __future__ import print_function  ###如果是python 2.x 使用print 依然需要加上（）
import os,sys
import contextlib
import shutil
import platform
import subprocess
import datetime
try:
    import urllib2 as urllib_request
except ImportError:
    import urllib.request as urllib_request


REMOTES = {
    "requirements": "https://raw.githubusercontent.com/bcbio/bcbio-nextgen/master/requirements-conda.txt",
    "gitrepo": "https://github.com/bcbio/bcbio-nextgen.git",
    "system_config": "https://raw.github.com/bcbio/bcbio-nextgen/master/config/bcbio_system.yaml",
    "anaconda": "https://repo.continuum.io/miniconda/Miniconda3-latest-%s-x86_64.sh"}


TARGETPY = ""

def main(args, sys_argv):
    with bcbio_tmpdir():
        setup_data_dir(args)
        print("Installing isolated base python installation")
        anaconda = install_anaconda_python(args)
        print("Installing bcbio-nextgen")
        bcbio = install_conda_pkgs(anaconda, args)

    print("Installing data and third party dependencies")
    system_config = write_system_config(REMOTES["system_config"], args.datadir,args.tooldir)

    subprocess.check_call([bcbio, "upgrade"] + _clean_args(sys_argv, args))

def _clean_args(sys_argv, args):
    """Remove data directory from arguments to pass to upgrade function.
    """
    # print(args.datadir)
    # print( os.path.abspath(os.path.expanduser(sys_argv[0])))
    # if sys_argv[0].startswith("_") or not args.datadir == os.path.abspath(os.path.expanduser(sys_argv[0])):
    #     print("aa")
    base = [x for x in sys_argv if
            x.startswith("-") or not args.datadir == os.path.abspath(os.path.expanduser(x))]
    # Remove installer only options we don't pass on
    base = [x for x in base if x not in set(["--minimize-disk"])]
    if "--nodata" in base:
        base.remove("--nodata")
    else:
        base.append("--data")
    return base

def write_system_config(base_url , datadir, tooldir):
    out_file = os.path.join(datadir, "galaxy", os.path.basename(base_url))
    if not os.path.exists(os.path.dirname(out_file)):
        os.makedirs(os.path.dirname(out_file))

    if os.path.exists(out_file):
        if tooldir is None:
            return out_file
        else:
            bak_file = out_file + ".bak%"(datetime.datetime.now().strftime("%Y%M%d_%H%M"))
            shutil.copy(out_file, bak_file)
    if tooldir:
        java_basedir = os.path.join(tooldir, "share", "java")

    rewrite_ignore = ("log",)
    with contextlib.closing(urllib_request.urlopen(base_url)) as in_handle:
        with open(out_file, "w") as out_handle:
            in_resources = False
            in_prog = None
            for line in (l.decode("utf-8") for l in in_handle):
                if line[0] != " ":
                    in_resources = line.startswith("resources")
                    in_prog = None
                elif (in_resources and line[:2] == "  " and line[2] != " "
                    and not line.strip().startswith(rewrite_ignore)):
                    in_prog = line.split(":")[0].strip()

                elif line.strip().startswith("dir:") and in_prog and in_prog not in ["log", "tmp"]:
                    final_dir = os.path.basename(line.split()[-1])
                    if tooldir:
                        line = "%s: %s\n" % (line.split(":")[0],
                                             os.path.join(java_basedir, final_dir))
                    in_prog = None
                elif line.startswith("galaxy"):
                    line = "# %s" % line
                out_handle.write(line)

        return out_file
def install_anaconda_python(args):
    anaconda_dir = os.path.join(args.datadir, "anaconda")
    bindir = os.path.join(anaconda_dir, "bin")
    conda = os.path.join(bindir, "conda")
    if not os.path.exists(anaconda_dir) or not os.path.exists(conda):
        if os.path.exists(anaconda_dir): shutil.rmtree(anaconda_dir)
        dist = _guess_distribution()
        url = REMOTES['anaconda'] %("MacOSX" if dist.lower() == "macosx" else "Linux")
        if not os.path.exists(os.path.basename(url)):
            subprocess.check_call(['wget', "--progress=dot:mega", "--no-check-certificate", url])
        subprocess.check_call("bash %s -b -p %s"%(os.path.basename(url), anaconda_dir), shell=True )
    return  {"conda": conda,
            "pip": os.path.join(bindir, "pip"),
            "dir": anaconda_dir}


def install_conda_pkgs(anaconda, args):
    env = dict(os.environ)
    # Try to avoid user specific pkgs and envs directories
    # https://github.com/conda/conda/issues/6748
    env['CONDA_PKGS_DIRS'] = os.path.join(anaconda['dir'], "pkgs")
    env['CONDA_ENVS_DIRS'] = os.path.join(anaconda['dir'], 'envs')

    if not os.path.exists((os.path.basename(REMOTES['requirements']))):
        subprocess.check_call(['wget', '--no-check-certificate', REMOTES['requirements']])


    channels = _get_conda_channels(anaconda['conda'])
    subprocess.check_call([anaconda['conda'], "install", "--yes"] + channels +
                          ['--only-deps', "bcbio-nextgen", TARGETPY], env= env)

    subprocess.check_call([anaconda["conda"], "install", "--yes"] + channels +
                          ["--file", os.path.basename(REMOTES["requirements"]), TARGETPY], env=env)
    return os.path.join(anaconda["dir"], "bin", "bcbio_nextgen.py")


def _get_conda_channels(conda_bin):
    channels = ['bioconda', 'conda-forge']
    out = []
    try:
        import yaml
        config = yaml.safe_load(subprocess.check_output([conda_bin, 'config', '--show']))

    except ImportError:
        config = {}

    for c in channels:
        present = False
        for orig_c in config.get("channels") or []:
            if orig_c.endswith((c, "%s/"%c )):
                present = True
                break
        if not present:
            out += ["-c", c]
    return out

def _guess_distribution():
    if platform.mac_ver()[0]:
        return "macosx"
    else:
        return "linux"

def setup_data_dir(args):
    if not os.path.exists(args.datadir):
        os.makedirs(args.datadir)


def check_dependencies():
    print("Check requires dependencies")

@contextlib.contextmanager
def bcbio_tmpdir():
    orig_dir = os.getcwd()
    work_dir = os.path.join(orig_dir, "tmpbcbio-install")
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)

    os.chdir(work_dir)
    yield work_dir
    os.chdir(orig_dir)
    shutil.rmtree(work_dir)

if __name__ == '__main__':
    try:
        import argparse

    except ImportError:
        raise ImportError("bcbio-nextgen installer requires `argparse`, included in Python 2.7.\n"
                          "Install for earlier versions with `pip install argparse` or "
                          "`easy_install argparse`.")

    parser = argparse.ArgumentParser(description= "Automatic installation for bcbio-nextgen pipelines")
    parser.add_argument("datadir", help = "Directory to install genome data", type = lambda x: (os.path.expanduser(x)))
    parser.add_argument("--cores", default=1, help="Number of cores to use if local indexing is necessary.")
    parser.add_argument("--tooldir", help= "Directory to install 3rd party software tools. Leave unspecified for no tools",
                        type = lambda x: (os.path.abspath(os.path.expanduser(x))) , default= None)


    parser.add_argument("--genomes", help= "Genomes to download",
                        action="append", default=[] ,
                        choices=["GRCh37", "hg19", "hg38", "hg38-noalt", "mm10", "mm9", "rn6", "rn5",
                                 "canFam3", "dm3", "galGal4", "phix", "pseudomonas_aeruginosa_ucbpp_pa14",
                                 "sacCer3", "TAIR10", "WBcel235", "xenTro3", "GRCz10", "GRCz11",
                                 "Sscrofa11.1", "BDGP6"]
                        )
    parser.add_argument("--aligners", help="Aligner indexes to download",
                        action="append", default=[],
                        choices=["bbmap", "bowtie", "bowtie2", "bwa", "minimap2", "novoalign", "rtg", "snap",
                                 "star", "ucsc", "hisat2"]
                        )

    from django.core.management import execute_from_command_line
    # sys.argv.extend(["/usr/local/share/bcbio","--tooldir", "/usr/local", "--genomes", "GRCh37", "--aligners", "bwa", "--aligners", "bowtie2"])
    sys.argv.extend(["/usr/local/share/bcbio"])

    args = parser.parse_args()

    base = _clean_args(sys.argv[1:], args)
    print (base)
