"""Small filters for noisy Linux tc output emitted through Mininet.

The kernel warning below is common with the small HTB classes used by this
testbed. It is not actionable for the experiment, and Mininet prints it through
``error()``, which floods both the terminal and ``tee`` logs.
"""

HTB_QUANTUM_WARNING = 'sch_htb: quantum of class'


def strip_htb_quantum_warning(text):
    """Return text with only the noisy HTB quantum warning lines removed."""
    if HTB_QUANTUM_WARNING not in str(text):
        return text
    kept = [
        line for line in str(text).splitlines(keepends=True)
        if HTB_QUANTUM_WARNING not in line
    ]
    return ''.join(kept)


def _filtered_error(original):
    def wrapper(*args, **kwargs):
        text = ''.join(str(arg) for arg in args)
        filtered = strip_htb_quantum_warning(text)
        if not filtered.strip():
            return None
        return original(filtered, **kwargs)

    wrapper._dt4n_htb_filter = True
    wrapper._dt4n_original = original
    return wrapper


def install_tc_warning_filter():
    """Patch Mininet's error printer so the known HTB warning is silent."""
    try:
        import mininet.log as mnlog
        import mininet.link as mnlink
    except Exception:
        return False

    for module in (mnlog, mnlink):
        current = getattr(module, 'error', None)
        if current is None or getattr(current, '_dt4n_htb_filter', False):
            continue
        module.error = _filtered_error(current)
    return True
