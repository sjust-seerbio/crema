"""Initialize the crema package."""
try:
    from importlib.metadata import version, PackageNotFoundError

    try:
        __version__ = version("crema-ms")
    except PackageNotFoundError:
        pass

except ImportError:
    from pkg_resources import get_distribution, DistributionNotFound

    try:
        __version__ = get_distribution("crema-ms").version
    except DistributionNotFound:
        pass

# Here is where we can export public functions and classes.
from crema.dataset import PsmDataset
from crema.parsers.crux import read_crux
from crema.parsers.msgf import read_msgf
from crema.parsers.msamanda import read_msamanda
from crema.parsers.msfragger import read_msfragger
from crema.parsers.txt import read_txt
from crema.parsers.pepxml import read_pepxml
from crema.parsers.mztab import read_mztab
from crema.parsers.mzid import read_mzid
from crema.parsers.pepxml import read_pepxml
from crema.confidence import TdcConfidence, assign_confidence
from crema.writers.txt import to_txt
