"""
This module contains the parsers for reading in PSMs
"""

import pandas as pd
import numpy as np
from .dataset import PsmDataset


def read_file(
    input_files,
    spectrum_col="scan",
    score_col="combined p-value",
    target_col="target/decoy",
    delimiter="," or "\t",
):
    """
    Read tab-delimited files.

    Parameters
    ----------
    input_files : tuple of str
        one or more tab-delimited file(s) to read
    spectrum_col : str
        name of the column that identifies the psm
    score_col : str
        name of the column that defines the scores (p-values) of the psms
    target_col : str
        name of the column that indicates if a psm is a target/decoy
    delimiter : str
        string character equal to what is used to separate columns
        within the tab-delimited file

    Returns
    -------
    PsmDataset
        A :py:class:`~crema.dataset.PsmDataset` object
        containing the PSM data from the given tab-delimited file.
    """
    # Store column names in a list to be used by read_csv method
    fields = [spectrum_col, score_col, target_col]
    # Create empty Pandas dataframe
    data = pd.DataFrame()
    # Loop through all given files
    for file in input_files:
        data = data.append(
            pd.read_csv(file, sep=delimiter, usecols=fields), ignore_index=True
        )
    data = convert_target_col(data, target_col)
    return PsmDataset(data, spectrum_col, score_col, target_col)


def convert_target_col(data, target_col):
    """
    Convert values in target column to boolean True/False.

    Parameters
    ----------
    data : pandas.DataFrame
        A pandas.DataFrame of the data before the target/decoy column has been converted to boolean
    target_col : str
        name of the column that indicates if a psm is a target/decoy

    Returns
    -------
    data : pandas.DataFrame
        A pandas.DataFrame of the data after the target/decoy column has been converted to boolean
    """
    # Grab the first value in the target column
    identifier = data.iloc[0][target_col]
    # If the first value is already a boolean, return the data without manipulating anything
    if isinstance(identifier, bool):
        return data
    # If the first value is a numeric value, convert to boolean
    elif isinstance(identifier, (float, int, np.int64)):
        targets = {
            not (0 and 0.0 and -1 and -1.0): True,
            0 or 0.0: False,
            -1 or -1.0: False,
        }
        data[target_col] = data[target_col].map(targets)
    # If the first value is a string, convert to boolean
    elif isinstance(identifier, str):
        targets = {
            "target": True,
            "t": True,
            "decoy": False,
            "d": False,
            "f": False,
        }
        data[target_col] = data[target_col].map(targets)
    return data
