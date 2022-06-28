"""The :py:class:`Confidence` class is used to define a collection of
peptide-spectrum matches with calculated false discovery rates (FDR) and q-values.
"""
import logging
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod

from . import qvalues
from . import utils
from .writers.txt import to_txt

np.random.seed(0)

LOGGER = logging.getLogger(__name__)


def assign_confidence(
    psms,
    score_column=None,
    desc=None,
    eval_fdr=0.01,
    method="tdc",
    pep_fdr_type="classic",
):
    """Assign confidence estimates to a collection of peptide-spectrum matches.

    Parameters
    ----------
    psms : PsmDataset or list of PsmDataset objects
        The collections of PSMs
    score_column : str, optional
        The score by which to rank the PSMs for confidence estimation. If
        :code:`None`, the score that yields the most PSMs at the specified
        false discovery rate threshold (`eval_fdr`), will be used.
    desc : bool, optional
        True if higher scores better, False if lower scores are better.
        If None, crema will try both and use the
        choice that yields the most PSMs at the specified false discovery
        rate threshold (`eval_fdr`). If `score_column` is :code:`None`,
        this parameter is ignored.
    eval_fdr : float, optional
        The false discovery rate threshold used to evaluate the best
        `score_column` and `desc` to choose. This should range from 0 to 1.
    method : {"tdc"}, optional
        The method for crema to use when calculating the confidence estimates.
    pep_fdr_type : {"classic","peptide-only",psm-peptide"}, optional
        The method for crema to use when calculating peptide level confidence
        estimates.

    Returns
    -------
    Confidence object or List of Confidence objects
        The confidence estimates for each PsmDataset.
    """
    psms = utils.listify(psms)
    confs = []
    for dset in psms:
        conf = dset.assign_confidence(
            score_column=score_column,
            desc=desc,
            eval_fdr=eval_fdr,
            method=method,
            pep_fdr_type=pep_fdr_type,
        )
        confs.append(conf)

    if len(confs) == 1:
        return confs[0]

    return confs


class Confidence(ABC):
    """Estimate statistical confidence estimates for a collection of PSMs.

    This should be a good base class for most of the methods, but not one
    directly called by a user.

    Parameters
    ----------
    psms : a PsmDataset object
        A collection of PSMs
    score_column : str, optional
        The score by which to rank the PSMs for confidence estimation. If
        :code:`None`, the score that yields the most PSMs at the specified
        false discovery rate threshold (`eval_fdr`), will be used.
    desc : bool, optional
        True if higher scores better, False if lower scores are better.
        If None, crema will try both and use the
        choice that yields the most PSMs at the specified false discovery
        rate threshold (`eval_fdr`). If `score_column` is :code:`None`,
        this parameter is ignored.
    eval_fdr : float, optional
        The false discovery rate threshold used to evaluate the best
        `score_column` and `desc` to choose. This should range from 0 to 1.

    Attributes
    ----------
    data : pandas.DataFrame
    dataset : crema.PsmDataset
    levels : list of str
    confidence_estimates : Dict
        A dictionary containing the confidence estimates at each level, each
        as a :py:class:`pandas.DataFrame`.
    decoy_confidence_estimates : Dict
        A dictionary containing the confidence estimates for the decoy hits at
        each level, each as a :py:class:`pandas.DataFrame`

    :meta private:

    """

    _level_labs = {
        "psms": "PSMs",
        "peptides": "Peptides",
        "proteins": "Proteins",
    }

    @abstractmethod
    def _assign_confidence(self):
        """How should confidence estimates be assigned?

        Each method will have its own way of doing this. The results
        should be saved in the `confidence_estimates` and
        `decoy_confidence_estimates` attributes.
        """
        pass

    def __init__(
        self,
        psms,
        score_column,
        desc=None,
        eval_fdr=0.01,
        pep_fdr_type="classic",
    ):
        """Initialize a Confidence object."""
        if eval_fdr < 0 or eval_fdr > 1:
            raise ValueError("'eval_fdr' should be between 0 and 1.")

        if desc is None:
            scores, targ = psms[score_column], psms.targets
            t_pass = (qvalues.tdc(scores, targ, desc=True) <= eval_fdr).sum()
            f_pass = (qvalues.tdc(scores, targ, desc=False) <= eval_fdr).sum()
            desc = t_pass > f_pass

        self._dataset = psms
        self._data = psms.data
        self._score_column = score_column
        self._desc = desc
        self._eval_fdr = eval_fdr
        self._levels = ("psms", "peptides", "proteins")
        self._level_columns = (
            self.dataset._spectrum_columns,
            self.dataset._peptide_column,
            self.dataset._protein_column,
        )
        self._pep_fdr_type = pep_fdr_type
        self.confidence_estimates = {}
        self.decoy_confidence_estimates = {}

        # Assign confidence estimates
        self._assign_confidence()

        # Clean up tables
        self._prettify_tables()

    @property
    def data(self):
        """The collection of PSMs as a :py:class:`pandas.DataFrame`."""
        return self._data

    @property
    def dataset(self):
        """The underlying :py:class:`~crema.dataset.PsmDataset`"""
        return self._dataset

    @property
    def levels(self):
        """The available levels of confidence estimates"""
        return self._levels

    def _prettify_tables(self):
        """Reorder the columns of the result tables for consistency"""
        cols = [
            *self.dataset._spectrum_columns,
            self.dataset._peptide_column,
            self._score_column,
            "crema q-value",
        ]
        prot_cols = [ 
            self.dataset._protein_column,
            self._score_column,
            "crema q-value",
        ]

        for level, df in self.confidence_estimates.items():
            if level != 'proteins':
                self.confidence_estimates[level] = df.loc[:, cols]
            elif level == 'proteins':
                self.confidence_estimates[level] = df.loc[:, prot_cols]

        for level, df in self.decoy_confidence_estimates.items():
            if level != 'proteins':
                self.decoy_confidence_estimates[level] = df.loc[:, cols]
            elif level == 'proteins':
                self.decoy_confidence_estimates[level] = df.loc[:, prot_cols]

    def _compete(self, df, group_columns):
        """Perform target-decoy competition

        For each group defined by `group_columns`, keep only the element
        with the highest score.

        Parameters
        ----------
        df : panda.DataFrame
            The DataFrame on which to perform the competition.
        group_columns: str or list of str
            The columns that define a group. The best score is retained
            within the group.

        Returns
        -------
        pandas.DataFrame
            A :py:class:`pandas.DataFrame` containing only rows that won the
            competition.
        """
        if self._desc:
            keep = "last"
        else:
            keep = "first"

        group_columns = utils.listify(group_columns)
        # Shuffle dataframe so ties are broken randomly.
        out_df = (
            df.sample(frac=1)
            .sort_values([self._score_column] + group_columns)
            .drop_duplicates(group_columns, keep=keep)
        )
        return out_df

    def __getitem__(self, column):
        """Return the specified column"""
        return self._data.loc[:, column]

    def __iter__(self):
        """...but we don't want this class to be an iterable (see PEP234)"""
        raise TypeError

    def to_txt(self, output_dir=None, file_root=None, sep="\t", decoys=False):
        """Save confidence estimates to delimited text files.

        Parameters
        ----------
        output_dir : str or None, optional
            The directory in which to save the files. `None` will use the
            current working directory.
        file_root : str or None, optional
            An optional prefix for the confidence estimate files. The suffix
            will always be "crema.{level}.txt", where "{level}" indicates the
            level at which confidence estimation was performed (i.e. PSMs,
            peptides, proteins).
        sep : str, optional
            The delimiter to use.
        decoys : bool, optional
            Save decoys confidence estimates as well?

        Returns
        -------
        list of str
            The paths to the saved files.

        """
        return to_txt(
            self,
            output_dir=output_dir,
            file_root=file_root,
            sep=sep,
            decoys=decoys,
        )


class TdcConfidence(Confidence):
    """Assign confidence estimates using target decoy competition.

    Estimates q-values using the target decoy competition method. For set of
    target and decoy PSMs meeting a specified score threshold, the false
    discovery rate (FDR) is estimated as:

    .. math::
        FDR = \\frac{Decoys + 1}{Targets}

    More formally, let the scores of target and decoy PSMs be indicated as
    :math:`f_1, f_2, ..., f_{m_f}` and :math:`d_1, d_2, ..., d_{m_d}`,
    respectively. For a score threshold :math:`t`, the false discovery
    rate is estimated as:

    .. math::
        E\\{FDR(t)\\} = \\frac{|\\{d_i > t; i=1, ..., m_d\\}| + 1}
        {\\{|f_i > t; i=1, ..., m_f|\\}}

    The reported q-value for each PSM is the minimum FDR at which that
    PSM would be accepted.

    Parameters
    ----------
    psms : a PsmDataset object
        A collection of PSMs
    score_column : str, optional
        The score by which to rank the PSMs for confidence estimation. If
        :code:`None`, the score that yields the most PSMs at the specified
        false discovery rate threshold (`eval_fdr`), will be used.
    desc : bool, optional
        True if higher scores better, False if lower scores are better.
        If None, crema will try both and use the
        choice that yields the most PSMs at the specified false discovery
        rate threshold (`eval_fdr`). If `score_column` is :code:`None`,
        this parameter is ignored.
    eval_fdr : float, optional
        The false discovery rate threshold used to evaluate the best
        `score_column` and `desc` to choose. This should range from 0 to 1.
    pep_fdr_type : {"classic","peptide-only",psm-peptide"}, optional
        The method for crema to use when calculating peptide level confidence
        estimates.

    Attributes
    ----------
    data : pandas.DataFrame
    dataset : crema.PsmDataset
    levels : list of str
    confidence_estimates : Dict
        A dictionary containing the confidence estimates at each level, each
        as a :py:class:`pandas.DataFrame`.
    decoy_confidence_estimates : Dict
        A dictionary containing the confidence estimates for the decoy hits at
        each level, each as a :py:class:`pandas.DataFrame`
    """

    def __init__(
        self,
        psms,
        score_column=None,
        desc=None,
        eval_fdr=0.01,
        pep_fdr_type="classic",
    ):
        """Initialize a TdcConfidence object."""
        LOGGER.info(
            "Assigning confidence estimates using target-decoy competition..."
        )

        super().__init__(
            psms=psms,
            score_column=score_column,
            desc=desc,
            eval_fdr=eval_fdr,
            pep_fdr_type=pep_fdr_type,
        )

    def _assign_confidence(self):
        """Assign confidence estimates using target-decoy competition"""
        pairing = self.dataset.peptide_pairing

        if pairing == None and self._pep_fdr_type != "classic":
            raise ValueError(
                "Must provide paired target decoy peptide infomation"
            )

        for level, group_cols in zip(self.levels, self._level_columns):
            df = self.data #TODO this can be removed if classic and Pepides only methods are removed
            pair_col = utils.new_column("pairing", df)

            if level == "peptides":
                if self._pep_fdr_type == "classic":
                    group_cols = utils.listify(group_cols)
                elif (
                    self._pep_fdr_type == "peptide-only" or
                    self._pep_fdr_type == "psm-peptide"
                ):
                    if self._pep_fdr_type == "psm-peptide":
                        df = self._compete(df, self.dataset._spectrum_columns)
                        group_cols = utils.listify(group_cols)

                    # replace sequence with pairing
                    pair_col = utils.new_column("pairing", df)
                    df[pair_col] = df[self.dataset._peptide_column].map(
                        lambda x: pairing.get(x, x)
                    )
                    group_cols = utils.listify(group_cols) + [pair_col]
                    group_cols.remove(self.dataset._peptide_column)
                else:
                    raise ValueError(
                        f"'{self._pep_fdr_type}' is not a valid value for "
                        "pep_fdr_type "
                    )
            elif level == 'proteins':
                # Perform PSM level FDR
                df = self._compete(df, self.dataset._spectrum_columns)

                # Remove peptides found in multiple proteins
                # TODO need to account for other protein delimiters
                df = df[~df[self.dataset._protein_column].str.contains(",")]

                #print(df)
                #print(df.columns)
                #print(df['protein id'])
                #for tar,prot in zip(df['target/decoy'],df['protein id']):
                #    print(tar,prot)

                df.to_csv("file1.txt",sep='\t',index=False)
                # Sum scores of all unique peptides in a protein
                # TODO how to aggregate p-value scores?
                df2 = df.groupby([self.dataset._protein_column, self.dataset._target_column]).agg({self._score_column: ['sum']})
                df2 = df2.reset_index()
                df2.columns = [self.dataset._protein_column, self.dataset._target_column, self._score_column]
                df = df2
                df.to_csv("file2.txt",sep='\t',index=False)

            df = self._compete(df, group_cols)
            targets = df[self.dataset._target_column]

            # Now calculate q-values:
            df["crema q-value"] = qvalues.tdc(
                scores=df[self._score_column],
                target=targets,
                desc=self._desc,
            )

            LOGGER.info(
                "  - Found %i %s at q<=%g.",
                (df[targets]["crema q-value"] <= self._eval_fdr).sum(),
                self._level_labs[level],
                self._eval_fdr,
            )

            self.confidence_estimates[level] = df.loc[targets, :]
            self.decoy_confidence_estimates[level] = df.loc[~targets, :]


class MixmaxConfidence(Confidence):
    """Assign confidence estimates using mix-max competition.

    #TODO. Maybe just cite paper
    Estimates qvalues using the mix-max competition method. For a set
    of ..., the false discover rate (FDR) is estimated.

    Parameters
    ----------
    psms : a PsmDataset object
        A collection of PSMs
    score_column : str, optional
        The score by which to rank the PSMs for confidence estimation. If
        :code:`None`, the score that yields the most PSMs at the specified
        false discovery rate threshold (`eval_fdr`), will be used.
    desc : bool, optional
        True if higher scores better, False if lower scores are better.
        If None, crema will try both and use the
        choice that yields the most PSMs at the specified false discovery
        rate threshold (`eval_fdr`). If `score_column` is :code:`None`,
        this parameter is ignored.
    eval_fdr : float, optional
        The false discovery rate threshold used to evaluate the best
        `score_column` and `desc` to choose. This should range from 0 to 1.
    pep_fdr_type : {"classic","peptide-only",psm-peptide"}, optional
        The method for crema to use when calculating peptide level confidence
        estimates.

    Attributes
    ----------
    data : pandas.DataFrame
    dataset : crema.PsmDataset
    levels : list of str
    confidence_estimates : Dict
        A dictionary containing the confidence estimates at each level, each
        as a :py:class:`pandas.DataFrame`.
    decoy_confidence_estimates : Dict
        A dictionary containing the confidence estimates for the decoy hits at
        each level, each as a :py:class:`pandas.DataFrame`
    """

    def __init__(
        self,
        psms,
        score_column=None,
        desc=None,
        eval_fdr=0.01,
        pep_fdr_type="classic",
    ):
        """Initialize a TdcConfidence object."""
        LOGGER.info(
            "Assigning confidence estimates using mix-max competition..."
        )

        # TODO maybe better way to do this
        # can not infer desc value as the wrong value will
        # result in a divide by zero error
        if desc == None:
            raise ValueError("'desc' has to be set for mix-max.")

        super().__init__(
            psms=psms,
            score_column=score_column,
            desc=desc,
            eval_fdr=eval_fdr,
            pep_fdr_type=pep_fdr_type,
        )

    def _assign_confidence(self):
        """Assign confidence estimates using target-decoy competition"""

        # TODO check if separate target-decoy search is done
        for level, group_cols in zip(self.levels, self._level_columns):
            if level == "peptides":
                continue

            df = self.data
            group_cols = utils.listify(group_cols)
            print(group_cols)

            targets = df[df[self.dataset._target_column]]
            decoys = df[~df[self.dataset._target_column]]

            # TOOO add following warning ""The mix-max procedure is not well behaved when # targets (%d) != # of decoys (%d).","

            if self._desc:
                keep = "last"
            else:
                keep = "first"

            # sort targets by score column and keep top rank
            targets_sorted = (
                targets.sample(frac=1)
                .sort_values([self._score_column] + group_cols)
                .drop_duplicates(group_cols, keep=keep, ignore_index=True)
            )

            # sort decoys by score column and keep top rank
            decoys_sorted = (
                decoys.sample(frac=1)
                .sort_values([self._score_column] + group_cols)
                .drop_duplicates(group_cols, keep=keep, ignore_index=True)
            )

            # combine top ranked target and decoy into one dataframe
            combined = pd.concat([targets_sorted, decoys_sorted])
            combined_sorted = combined.sample(frac=1).sort_values(
                [self._score_column], ascending=~self._desc, ignore_index=True
            )

            # qvalues.py::calculate_mixmax_qval expects target scores
            # and decoy scores to be sorted from worst to best
            # qvalues.py::mixmax expected combined_sorted scores
            # to be sorted from best to worst
            if self._desc:  # larger score is better
                combined_sorted = combined_sorted[::-1]
            else:  # smaller score is better
                targets_sorted[self._score_column] = (
                    targets_sorted[self._score_column] * -1.0
                )
                decoys_sorted[self._score_column] = (
                    decoys_sorted[self._score_column] * -1.0
                )
                targets_sorted = targets_sorted[::-1]
                decoys_sorted = decoys_sorted[::-1]

            # Now calculate q-values:
            pi0, targets_sorted["crema q-value"] = qvalues.mixmax(
                target_scores=targets_sorted[self._score_column],
                decoy_scores=decoys_sorted[self._score_column],
                combined_score=combined_sorted[self._score_column],
                combined_score_target=combined_sorted[
                    self.dataset._target_column
                ],
            )

            LOGGER.info("  - Estimated pi_zero = %f.", pi0)

            LOGGER.info(
                "  - Found %i %s at q<=%g.",
                (targets_sorted["crema q-value"] <= self._eval_fdr).sum(),
                self._level_labs[level],
                self._eval_fdr,
            )

            # reverse rows so that best score is at top
            targets_sorted = targets_sorted[::-1]

            # undo previous multipliation by -1.0
            if self._desc == False:
                targets_sorted[self._score_column] = (
                    targets_sorted[self._score_column] * -1.0
                )
            self.confidence_estimates[level] = targets_sorted
