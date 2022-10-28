import tarfile
import pandas as pd
from glob import glob
import os

def read_stats_in_log(model_tarfile):
    """ read fms.out in tarfile and format stats nicely in pandas dataframe """
    # log file is YYYY0101.fms.out
    log_filename = os.path.basename(model_tarfile).replace("ascii_out.tar", "fms.out")
    year = int(os.path.basename(model_tarfile).replace("0101.ascii_out.tar", ""))

    if not log_filename.startswith('./'):
        log_filename = './' + log_filename

    with tarfile.open(model_tarfile, "r:") as f:
        logdump = f.extractfile(log_filename).read().decode('utf-8')

    lines = logdump.split(sep='\n')

    linestart_stats = [lines.index(line) for line in lines if line.find('Total runtime') != -1 ][-1]
    lineend_stats = [lines.index(line) for line in lines if line.find('high water mark') != -1 ][-1]

    raw_stats = lines[linestart_stats-1:lineend_stats]

    # infer the number of data columns
    columns = raw_stats[0].split()
    
    ncol_data = len(columns)
    # add a column for model component
    columns = ['model'] + columns
    formatted_lines = []
    for line in raw_stats[1:]:
        data = line.split()[-ncol_data:]
        nitems = len(line.split())
        nondata = line.split()[0:nitems-ncol_data]
        space= " "
        modelname = space.join(nondata)
        data_num = []
        for item in data:
            data_num.append(float(item))

        formatted_line = [modelname] + data_num
        formatted_lines.append(formatted_line)

    df = pd.DataFrame(formatted_lines, columns = columns)
    df['year'] = year

    return df


def build_stats_run(dirrun):
    """ loop over tar files and call read_stats_in_log """
    tarfiles = glob(dirrun + 'ascii/*.ascii_out.tar')
    df = read_stats_in_log(tarfiles[0])
    for f in tarfiles[1:]:
        df = pd.concat([df, read_stats_in_log(f)])

    return df.sort_values('year')

