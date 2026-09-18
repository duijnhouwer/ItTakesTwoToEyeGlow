"""The packaged smoke test must cover NumPy imports stored in fit files."""
from eyeglow_egobody.smoke import check_fit_pickle_loading


def test_fit_pickle_numpy_namespaces():
    check_fit_pickle_loading()
