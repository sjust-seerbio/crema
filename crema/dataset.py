"""The :py:class:`PsmDataset` class is used to define a collection of
peptide-spectrum matches.
"""
import logging

from .confidence import TdcConfidence
from .qvalues import tdc
from .utils import listify

LOGGER = logging.getLogger(__name__)


class PsmDataset:
    """Store a collection of peptide-spectrum matches (PSMs).

    Parameters
    ----------
    psms : pandas.DataFrame
        A :py:class:`pandas.DataFrame` of PSMs.
    target_column : str
        The column that indicates whether a PSM is a target or a decoy. This
        column should be boolean, where :code:`True` indicates a target and
        :code:`False` indicates a decoy.
    spectrum_columns : str or tuple of str
        One or more columns that together define a unique mass spectrum.
    score_columns : str or tuple of str, optional
        One or more columns that indicate scores by which crema can rank PSMs.
    peptide_column : str
        The column that defines a unique peptide. Modifications should be
        indicated either in square brackets :code:`[]` or parentheses
        :code:`()`. The exact modification format within these entities does
        not matter, so long as it is consistent.
    peptide_pairing: dict
        A map of target and decoy peptide sequence pairings to be used for TDC.
        This should be in the form {key=target_sequence:value=decoy_sequence}
        where decoy sequences are shuffled versions of target sequences.
    copy_data : bool, optional
        If true, a deep copy of the data is created. This uses more memory, but
        is safer because it prevents accidental modification of the underlying
        data. This argument only has an effect when `pin_files` is a
        :py:class:`pandas.DataFrame`

    Attributes
    ----------
    data : pandas.DataFrame
    spectrum_columns : list of str
    score_columns : list of str
    target_column : str
    peptide_column : str
    peptide_pairing : dict
    """

    def __init__(
        self,
        psms,
        target_column,
        spectrum_columns,
        score_columns,
        peptide_column,
        peptide_pairing=None,
        copy_data=True,
    ):
        """Initialize a PsmDataset object."""
        self.spectrum_columns = listify(spectrum_columns)
        self.score_columns = listify(score_columns)
        self.target_column = target_column
        self.peptide_column = peptide_column
        self.peptide_pairing = peptide_pairing

        fields = sum(
            [
                self.spectrum_columns,
                self.score_columns,
                [self.target_column],
                [self.peptide_column],
            ],
            [],
        )
        self._data = psms.copy(deep=copy_data).loc[:, fields]
        self._data[target_column] = self._data[target_column].astype(bool)
        self._num_targets = self.targets.sum()
        self._num_decoys = (~self.targets).sum()

        if self.data.empty:
            raise ValueError("No PSMs were detected.")

        if not self._num_decoys:
            raise ValueError("No decoy PSMs were detected.")

        if not self._num_targets:
            raise ValueError("No target PSMs were detected.")

    @property
    def data(self):
        """The collection of PSMs as a :py:class:`pandas.DataFrame`."""
        return self._data

    @property
    def scores(self):
        """The scores for each PSM as a :py:class:`pandas.DataFrame`."""
        return self[self.score_columns]

    @property
    def targets(self):
        """An array indicating whether each PSM is a target"""
        return self[self.target_column].values

    def __getitem__(self, column):
        """Return the specified column"""
        return self._data.loc[:, column]

    def add_peptide_pairing(self, pairing):
        """Adds a target/decoy peptide pairing to this collection of PSMs

        Parameters
        ----------
        pairing : dict
            A dictionary containing the target/decoy mapping to be used
            during TDC

        """
        if pairing is None:
            return
        if isinstance(pairing, dict):
            self.peptide_pairing = pairing
        else:
            raise ValueError(
                "The provided peptide pairing is not in the form of a "
                "Python Dict"
            )

    def assign_confidence(
        self,
        score_column=None,
        desc=None,
        eval_fdr=0.01,
        method="tdc",
    ):
        """Assign confidences estimates to this collection of PSMs."""
        methods = {
            "tdc": TdcConfidence,
        }

        conf = methods[method](
            psms=self,
            score_column=score_column,
            desc=desc,
            eval_fdr=eval_fdr,
        )

        return conf

    def find_best_score(self, eval_fdr=0.01):
        """Find the best score for this collection of PSMs

        Try each of the available score columns, determining how many PSMs
        are detected below the provided false discovery rate threshold. The
        best score is the one that returns the most.

        Parameters
        ----------
        eval fdr : float
            The false discovery rate threshold used to find the best score.

        Returns
        -------
        best_score : str
            The best score.
        n_passing : int
            The number of PSMs that meet the specified FDR threshold.
        desc : bool
            True if higher scores better, False if lower scares are better.
        """
        best_score = None
        best_passing = 0
        for desc in (True, False):
            qvals = self.scores.apply(tdc, target=self.targets, desc=desc)
            num_passing = (qvals <= eval_fdr).sum()
            feat_idx = num_passing.idxmax()
            num_passing = num_passing[feat_idx]
            if num_passing > best_passing:
                best_passing = num_passing
                best_score = feat_idx
                best_desc = desc

        if best_score is None:
            raise RuntimeError("No PSMs were found below the 'eval_fdr'.")

        return best_score, best_passing, best_desc
