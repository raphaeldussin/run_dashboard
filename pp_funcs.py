import os
import re
import subprocess
from datetime import datetime
from glob import glob, iglob

import ipywidgets as widgets
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import display


def datestr2date(datestring):
    """create datetime object from model output date convention

    Args:
        datestring (str): Model output date to decode

    Returns:
        datetime.datetime: model date decoded
    """
    if len(datestring) == 4:
        out = datetime.strptime(datestring, "%Y")
    elif len(datestring) == 6:
        out = datetime.strptime(datestring, "%Y%m")
    elif len(datestring) == 8:
        out = datetime.strptime(datestring, "%Y%m%d")
    elif len(datestring) == 10:
        out = datetime.strptime(datestring, "%Y%m%d%H")
    else:
        raise NotImplementedError("")
    return out


def create_pp_series(ppsubdir, startyear=None, endyear=None):
    """create a serie of files per year for a given model component sub directory

    Args:
        ppsubdir (str): full path to subdirectory to inspect
        startyear (int, optional): override for first year to inspect. Defaults to None.
        endyear (int, optional): override for last year to inspect. Defaults to None.

    Returns:
        pandas.Series: number of files per year
    """
    # build a pandas series with number of files
    allfiles_fullpath = glob(f"{ppsubdir}/*.nc")
    allfiles = [os.path.basename(f) for f in allfiles_fullpath]
    fields = list(set([f.replace(".", " ").split()[2] for f in allfiles]))
    dates = list(set([f.replace(".", " ").split()[1] for f in allfiles]))
    nfiles = {}
    indexes = []
    for date in dates:
        nfiles_raw = len(glob(f"{ppsubdir}/*{date}*.nc"))
        datebeg = datestr2date(date.replace("-", " ").split()[0])
        dateend = datestr2date(date.replace("-", " ").split()[1])
        indexes.append(dateend.year)
        nfiles.update({dateend.year: nfiles_raw})
    # fill in missing dates
    enddates = np.sort(np.array(indexes))
    segment_duration = np.diff(enddates).min()
    start = enddates[0] if startyear is None else startyear
    end = enddates[-1] if endyear is None else endyear
    expected_enddates = np.arange(start, end + segment_duration, segment_duration)
    for date in expected_enddates:
        if date not in list(enddates):
            indexes.append(date)
            nfiles.update({date: np.nan})
            print(f"expected files for year {date} but none found")
    return pd.Series(data=nfiles, index=indexes).sort_index()


def all_dirs_model(ppdir, model="ocean", ftype="ts"):
    """return all directories under ppdir for a given model (e.g. ocean, land,...)

    Args:
        ppdir (str): full path to run post-processing directory
        model (str, optional): Component of Climate/Earth system model. Defaults to "ocean".
        ftype (str, optional): timeseries (ts) or averages (av). Defaults to "ts".

    Returns:
        dict of str: paths to all directories for each period (key)
    """
    # find all files for the desired model
    all_files = glob(f"{ppdir}/{model}*/{ftype}/**/*.nc", recursive=True)
    # infer all the directories containing these files
    all_dirs = list(set([os.path.dirname(f) for f in all_files]))
    # infer the periods (e.g. 10yr, 5yr) since they are the parent directory
    if ftype == "av":
        periods = list(set([os.path.basename(d).replace('_',' ').split()[-1] for d in all_dirs]))
    else:
        periods = list(set([os.path.basename(d) for d in all_dirs]))
    # build a dictionary with period:directories
    dict_dirs = {}
    for p in periods:
        dict_dirs.update({p: []})
        for d in all_dirs:
            if d.find(p) != -1:
                dict_dirs[p].append(d)
    return dict_dirs


def pp_to_dataframe(all_dirs, segment="10yr", startyear=None, endyear=None):
    """Build dataframe containing number of files for each pp component for a given segment length

    Args:
        all_dirs (dict): period:list_of_directories as produced by all_dirs_model
        segment (str, optional): segment to analyze. Defaults to '10yr'.
        startyear (int, optional): override for first year of pp. Defaults to None.
        endyear (int, optional): override for last year of pp. Defaults to None.

    Returns:
        pandas.DataFrame: contains number of pp files sorted by year and pp component
    """
    # take a list of pp sub dirs and build dataframe for pp files
    df = pd.DataFrame()
    for subdir in all_dirs[segment]:
        lim = subdir.find("pp")
        if lim == -1:
            raise ValueError(
                f"directory {subdir} does not appear to be a valid pp directory"
            )
        subdir_short = subdir[lim:]
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    {
                        subdir_short: create_pp_series(
                            subdir, startyear=startyear, endyear=endyear
                        )
                    }
                ),
            ],
            axis=1,
        )
    return df


def pp_verif(
    ppdir,
    xmlpath,
    freversion,
    model="ocean",
    ftype="ts",
    startyear=None,
    endyear=None,
    dfout=False,
):
    """verify the number of pp files and disply bar chart

    Args:
        ppdir (str): full path to pp directory
        xmlpath (str): full path to run xml
        freversion (str): i.e. bronx whatever
        model (str, optional): model to use. Defaults to "ocean".
        ftype (str, optional): [description]. Defaults to 'ts'.
        startyear (int, optional): override for first year of pp to check. Defaults to None.
        endyear (int, optional): override for last year of pp to check. Defaults to None.
        dfout (bool, optional): return dataframe as output. Defaults to False.

    Returns:
        pd.DataFrame or None
    """
    # populate dict with immutable parameters
    freppdict = infer_properties_from_ppdir(ppdir)
    freppdict["xmlpath"] = xmlpath
    freppdict["freversion"] = freversion
    # find all timeseries directories for a model
    all_dirs = all_dirs_model(ppdir, model=model, ftype=ftype)
    # build a dataframe with number of files for each segment
    for seg in list(all_dirs.keys()):
        df = pp_to_dataframe(
            all_dirs, segment=seg, startyear=startyear, endyear=endyear
        )
        # bar plot
        plot_files_as_bars(df, seg)
        # check for missing files
        check_for_missing(df, freppdict)
    return df if dfout else None


def plot_files_as_bars(df, segment):
    """do a bar plot of number of files per year

    Args:
        df (pandas.DataFrame): number of files per component per year
        segment (str): segment lenth, e.g. 10yr
    """
    width = int(segment.replace("yr", "")) - 1
    plt.figure()
    ax = plt.axes()
    df.plot.bar(ax=ax, width=width, stacked=True, figsize=[10, 10])
    ax.legend(bbox_to_anchor=(1.8, 1.0))
    return None


def infer_properties_from_ppdir(ppdir):
    """infer some parameters from full path to pp dir

    Args:
        ppdir (str): full path to pp dir

    Returns:
        dict: immutable parameters of experiment
    """
    freppdict = dict()
    # find split between platform and run type (second hyphen)
    platform_runtype = ppdir.replace("/", " ").split()[4]
    cut = [_.start() for _ in re.finditer("-", platform_runtype)][1]
    # build into dict
    freppdict["runname"] = ppdir.replace("/", " ").split()[3]
    freppdict["platform"] = platform_runtype[:cut]
    freppdict["runtype"] = platform_runtype[cut + 1 :]
    return freppdict


def check_for_missing(df, freppdict):
    """check for missing files (i.e. nan) in dataframe and
    create button to fix pp

    Args:
        df (pandas.DataFrame): number of files per component per year
        freppdict (dict): immutable parameters of experiment
    """
    # check for missing files in a dataframe
    # the obvious case is all files missing for a segment (i.e. Nan)
    for col in list(df.keys()):
        missing = df[col].loc[df[col].isnull()]
        if len(list(missing.index)) > 0:
            print(f"files missing for {col} at years {list(missing.index)}")
            comp = col.replace("pp", "").replace("/", " ").split()[0]
            for year in list(missing.index):
                create_pp_fix_button(comp, year, freppdict)

    return None


def run_frepp_command(comp, year, freppdict):
    """build and execute sub-shell command to fix pp

    Args:
        comp (str): model component to process
        year (int): last year of segment to process
        freppdict (dict): immutable parameters of experiment

    Returns:
        int : error code
    """
    # build a frepp command from a dict of parameters
    import subprocess

    cyear = str(year).zfill(4)
    frepp_cmd = f"module load fre/{freppdict['freversion']} ; frepp -t {cyear}0101 -R -Y {cyear} -Z {cyear} -s -x {freppdict['xmlpath']} -P {freppdict['platform']} -T {freppdict['runtype']} -c {comp} {freppdict['runname']}"
    print(frepp_cmd)
    output = subprocess.check_call(frepp_cmd, shell=True)
    return output


def create_pp_fix_button(comp, year, freppdict):
    """create widget button to run pp fix

    Args:
        comp (str): model component to process
        year (int): last year of segment to process
        freppdict (dict): immutable parameters of experiment
    """
    # create a widget to resubmit pp
    button = widgets.Button(
        description=f"Fix {comp} for year {year}",
        layout=widgets.Layout(width="300px", height="40px"),
    )
    output = widgets.Output()
    display(button, output)

    def on_button_clicked(b):
        with output:
            out = run_frepp_command(comp, year, freppdict)
            message = (
                "pp job submitted successfully" if out == 0 else "problem submitting"
            )
            print(message)

    button.on_click(on_button_clicked)
    return None
