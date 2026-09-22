"""
tests/host/conftest.py — the run-time half of the skip ledger (GitHub Issue #29).

Under pytest (the runner `make test-python` prefers), every skip that actually
fires is classified against `skip_ledger.py`, and a skip whose reason is not
registered FAILS THE SESSION at the end with the reason printed. "2 skipped"
becoming "7 skipped" with nothing failing is the thing this exists to stop.

Under `python -m unittest discover` — the fallback when pytest is absent — a
conftest is not loaded and this check does not run. That is stated rather than
hidden: the STATIC half (`test_guard_shape.py`, which reads the skip reasons
out of the sources) runs under both runners and is what makes a new,
unregistered skip fail anywhere.
"""
import skip_ledger

_unregistered = []


def pytest_runtest_logreport(report):
    if report.skipped:
        reason = ""
        if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
            reason = report.longrepr[2]
        reason = reason.replace("Skipped: ", "").strip()
        if skip_ledger.classify(reason) is None:
            _unregistered.append((report.nodeid, reason))


def pytest_sessionfinish(session, exitstatus):
    if _unregistered:
        lines = "\n".join("    %s\n        %s" % (n, r) for n, r in _unregistered)
        session.config.stash  # no-op, keeps linters quiet about the unused arg
        print("\nISSUE #29: %d skip(s) fired with a reason that is not in tests/host/skip_ledger.py.\n"
              "A skip is indistinguishable from a pass, so a new kind of silence must be registered\n"
              "with its class and with what covers the risk instead:\n%s\n" % (len(_unregistered), lines))
        session.exitstatus = 1
